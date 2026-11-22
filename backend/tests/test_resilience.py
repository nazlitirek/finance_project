"""Hata senaryoları ve önceden test edilmemiş katmanlar (Aşama 8).

- Veritabanı bağlantısı kopması → 503 ve anlaşılır mesaj
- Eski fiyat verisi → uyarı
- Adapterlerin gerçek HTTP yolları (sahte sunucuyla): kaynak bozuk yanıt verince SourceError
- Claude istemcisi hata eşlemesi, komut satırı, zamanlayıcı listesi
"""

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.routes_data import staleness
from app.db.session import get_db
from app.sources.base import SourceError
from app.sources.evds import SERIES, EvdsSource
from app.sources.isyatirim import IsYatirimSource
from app.sources.kap import KapSource
from app.sources.tcmb_fx import TcmbFxSource


# ---------------------------------------------------------------- veritabanı kopması

class BrokenSession:
    def execute(self, *a, **k):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    scalar = scalars = execute

    def close(self):
        pass


@pytest.fixture
def broken_client():
    from app.main import app

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_health_reports_db_down(broken_client):
    r = broken_client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["database"] == "unreachable" and "PostgreSQL" in r.json()["message"]


@pytest.mark.parametrize("path", ["/api/stocks/search?q=thy", "/api/stocks/THYAO/quote", "/api/dashboard"])
def test_endpoints_return_503_when_db_down(broken_client, path):
    r = broken_client.get(path)
    assert r.status_code == 503
    assert r.json()["error"] == "database_unavailable" and "ulaşılamıyor" in r.json()["message"]


# ---------------------------------------------------------------- eski veri

@pytest.mark.parametrize(("as_of", "today", "stale", "gap"), [
    (date(2026, 11, 20), date(2026, 11, 22), False, 0),  # cuma → pazar
    (date(2026, 11, 20), date(2026, 11, 23), False, 0),  # cuma → pazartesi sabahı
    (date(2026, 11, 20), date(2026, 11, 24), False, 1),  # pazartesi kapanışı eksik
    (date(2026, 11, 13), date(2026, 11, 23), True, 5),
    (date(2026, 11, 20), date(2026, 11, 20), False, 0),
])
def test_staleness(as_of, today, stale, gap):
    assert staleness(as_of, today) == (stale, gap)


# ---------------------------------------------------------------- adapterler: sahte HTTP sunucusu

def mock(handler, cls, **kw):
    src = cls(client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None, **kw)
    src.min_interval = 0
    return src


def test_kap_page_layout_change_is_detected():
    kap = mock(lambda r: httpx.Response(200, text="<html>yeni tasarım</html>"), KapSource)
    with pytest.raises(SourceError, match="sayfa yapısı"):
        kap.companies()
    with pytest.raises(SourceError, match="sayfa yapısı"):
        kap.sectors()


def test_kap_disclosures_request_and_bad_payload():
    seen = {}

    def ok(req):
        seen["body"] = req.content
        return httpx.Response(200, json=[{"publishDate": "20.11.2026 10:00:00", "disclosureIndex": 1,
                                          "kapTitle": "X", "stockCodes": "THYAO"}])

    rows = mock(ok, KapSource).disclosures(date(2026, 11, 19), date(2026, 11, 20))
    assert rows[0].symbols == ("THYAO",) and b'"fromDate": "2026-11-19"' in seen["body"].replace(b'":"', b'": "')
    with pytest.raises(SourceError):
        mock(lambda r: httpx.Response(200, json={"hata": 1}), KapSource).disclosures(date(2026, 1, 1), date(2026, 1, 2))


def test_isyatirim_error_flag_and_statement_chunks():
    with pytest.raises(SourceError, match="THYAO"):
        mock(lambda r: httpx.Response(200, json={"ok": False, "errorDescription": "Teknik Hata"}),
             IsYatirimSource).daily_prices("THYAO", date(2026, 1, 1), date(2026, 1, 2))
    calls = []

    def stmts(req):
        calls.append(dict(req.url.params))
        return httpx.Response(200, json={"ok": True, "value": [{"itemCode": "3C", "value1": "1", "value2": "2"}]})

    out = mock(stmts, IsYatirimSource).statements("THYAO", "XI_29", [(2026, 9), (2026, 6), (2026, 3), (2025, 12),
                                                                        (2025, 9)])
    assert len(calls) == 2 and calls[1]["year1"] == "2025" and calls[1]["period1"] == "9"  # 4'erli gruplar
    assert len(out) == 3


def test_evds_requires_key_and_sends_header():
    with pytest.raises(SourceError, match="EVDS_API_KEY"):
        mock(lambda r: httpx.Response(200), EvdsSource, api_key=None).series(SERIES[0], date(2026, 1, 1), date(2026, 1, 2))
    seen = {}

    def ok(req):
        seen["key"] = req.headers.get("key")
        return httpx.Response(200, json={"items": [{"Tarih": "02-01-2026", "TP_DK_USD_A": "43.1"}]})

    pts = mock(ok, EvdsSource, api_key="gizli").series(SERIES[0], date(2026, 1, 1), date(2026, 1, 2))
    assert seen["key"] == "gizli" and len(pts) == 1


def test_tcmb_bad_xml():
    with pytest.raises(SourceError):
        mock(lambda r: httpx.Response(200, text="<bozuk"), TcmbFxSource).today()


def test_connection_errors_become_source_error():
    def down(req):
        raise httpx.ConnectError("dns", request=req)

    with pytest.raises(SourceError, match="erişilemedi"):
        mock(down, IsYatirimSource).daily_prices("THYAO", date(2026, 1, 1), date(2026, 1, 2))


# ---------------------------------------------------------------- Claude istemcisi hata eşlemesi

def test_anthropic_error_mapping(monkeypatch):
    import anthropic

    from app.ai import client as c
    from app.ai.schemas import NewsBatch

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def raising(exc):
        return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=lambda **k: (_ for _ in ()).throw(exc))))

    cases = [
        (anthropic.RateLimitError("limit", response=httpx.Response(429, request=req), body=None), "rate_limit"),
        (anthropic.AuthenticationError("bad", response=httpx.Response(401, request=req), body=None), "not_configured"),
        (anthropic.APIConnectionError(request=req), "connection"),
    ]
    for exc, kind in cases:
        monkeypatch.setattr(c, "_client", lambda e=exc: raising(e))
        with pytest.raises(c.AIError) as err:
            c._anthropic_structured("s", "u", NewsBatch, "low", 100)
        assert err.value.kind == kind

    def refused(**k):
        return SimpleNamespace(model="m", stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"),
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1), parsed_output=None)

    monkeypatch.setattr(c, "_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=refused))))
    with pytest.raises(c.AIError) as err:
        c._anthropic_structured("s", "u", NewsBatch, "low", 100)
    assert err.value.kind == "refusal"


# ---------------------------------------------------------------- komut satırı ve zamanlayıcı

def test_cli_dispatch_and_exit_codes(monkeypatch, capsys):
    from app import cli
    from app.ingest.runner import JobResult

    calls = []
    monkeypatch.setattr(cli.service, "update_companies", lambda: calls.append("c") or JobResult("companies", "kap", "success", 3, None))
    monkeypatch.setattr(cli.service, "update_prices", lambda s: calls.append(("p", s)) or JobResult("prices", "isyatirim", "failed", 0, "HTTP 500"))
    assert cli.main(["companies"]) == 0
    assert cli.main(["prices", "THYAO"]) == 1  # başarısız iş → çıkış kodu 1
    assert calls == ["c", ("p", ["THYAO"])]
    with pytest.raises(SystemExit):
        cli.main(["prices"])  # hisse kodu veya --all zorunlu
    assert "HTTP 500" in capsys.readouterr().out


def test_scheduler_jobs_and_times():
    from app.ingest import scheduler

    names = [n for n, *_ in scheduler.SCHEDULE]
    assert names == ["news", "disclosures", "companies", "macro", "prices", "financials"]
    assert all(desc for *_, desc in scheduler.SCHEDULE)
