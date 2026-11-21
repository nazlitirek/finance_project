from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import DataSource, MacroObservation
from app.ingest import jobs
from app.sources.isyatirim import StatementValue
from app.sources.kap import KapDisclosureRow
from app.sources.rss import NewsItem
from app.sources.base import TR_TZ
from tests.test_ingest import TODAY, FakeIsy, FakeKap, FakeRss


@pytest.fixture
def loaded(db, monkeypatch):
    jobs.sync_companies(db, FakeKap())
    isy = FakeIsy()
    jobs.sync_prices(db, isy, ["THYAO"], TODAY)
    isy.statement_values = [
        StatementValue("3C", "Satış Gelirleri", "Revenue", 2026, 9, Decimal("981")),
        StatementValue("3C", "Satış Gelirleri", "Revenue", 2026, 6, Decimal("585")),
        StatementValue("1A", "Dönen Varlıklar", None, 2026, 9, Decimal("500")),
    ]
    jobs.sync_financials(db, isy, ["THYAO"], quarters=4, today=TODAY)
    jobs.sync_disclosures(db, FakeKap(disclosures=[KapDisclosureRow(
        1, datetime(2026, 11, 20, 18, tzinfo=TR_TZ), "THY", ("THYAO",), "ODA", None, None, "Özel Durum", "ö", 0)]),
        today=TODAY)
    monkeypatch.setattr(jobs, "FEEDS", {"A": "https://a.test"})
    t = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    jobs.sync_news(db, FakeRss({"A": [NewsItem("https://a.test/1", "THYAO rekor kırdı", None, "A", t),
                                      NewsItem("https://a.test/2", "THYAO rekor kırdı - Hisse.net", None, "A", t)]}))
    src = db.scalar(select(DataSource.id).where(DataSource.code == "evds"))
    db.add(MacroObservation(source_id=src, series_code="TP.FG.J0", series_name="TÜFE", frequency="monthly",
                            obs_date=date(2026, 1, 1), value=Decimal("3683.83"), unit="endeks"))
    db.flush()


def test_prices_endpoint(client, loaded):
    r = client.get("/api/stocks/THYAO/prices", params={"range": "1m"})
    body = r.json()
    assert r.status_code == 200 and body["freshness"] == "end_of_day" and body["adjusted"] is True
    assert [b["close"] for b in body["bars"]] == [320.0, 329.0]
    assert all(b["open"] is None for b in body["bars"]) and "açılış" in body["note"]


def test_index_prices_are_unadjusted(client, loaded):
    body = client.get("/api/stocks/XU100/prices").json()
    assert body["adjusted"] is False and len(body["bars"]) == 2


def test_prices_empty_stock_message(client, loaded):
    body = client.get("/api/stocks/ISCTR/prices").json()
    assert body["bars"] == [] and "henüz" in body["message"]


def test_quote(client, loaded):
    q = client.get("/api/stocks/THYAO/quote").json()
    assert q["price"] == 329.0 and q["previous_close"] == 320.0 and q["as_of"] == "2026-11-20"
    assert round(q["change_pct"], 3) == round((329 - 320) / 320 * 100, 3)
    assert "Gerçek zamanlı değildir" in q["note"]


def test_movers(client, loaded):
    m = client.get("/api/market/movers").json()
    assert m["as_of"] == "2026-11-20" and m["gainers"][0]["symbol"] == "THYAO"
    assert m["coverage"] == 1 and m["note"]  # 3 aktif hisseden 1'i için veri var


def test_financials_endpoint(client, loaded):
    body = client.get("/api/stocks/THYAO/financials", params={"statement": "income"}).json()
    assert [p["key"] for p in body["periods"]] == ["2026/09", "2026/06"]
    assert body["periods"][0]["inflation_adjusted"] is True and body["consolidation"] == "unknown"
    assert body["items"] == [{"code": "3C", "name": "Satış Gelirleri", "values": {"2026/09": 981.0, "2026/06": 585.0}}]


def test_financials_cashflow_missing_message(client, loaded):
    body = client.get("/api/stocks/THYAO/financials", params={"statement": "cashflow"}).json()
    assert body["items"] == [] and "nakit akış" in body["message"]


def test_disclosures_endpoints(client, loaded):
    assert client.get("/api/stocks/THYAO/disclosures").json()["items"][0]["subject"] == "Özel Durum"
    assert client.get("/api/disclosures").json()["items"][0]["symbol"] == "THYAO"


def test_news_hides_duplicates(client, loaded):
    items = client.get("/api/stocks/THYAO/news").json()["items"]
    assert len(items) == 1 and items[0]["stocks"] == [{"symbol": "THYAO", "match_type": "symbol"}]
    assert len(client.get("/api/news").json()["items"]) == 1


def test_macro_marks_stale_series(client, loaded):
    items = {i["code"]: i for i in client.get("/api/macro").json()["items"]}
    assert items["TP.FG.J0"]["stale"] is True and items["TP.FG.J0"]["note"]


def test_updates_log(client, loaded):
    # loaded fixture işleri doğrudan çağırdı (run_job olmadan) → log boş olabilir; uç nokta yine çalışmalı
    assert client.get("/api/updates").status_code == 200


def test_refresh_rejects_index(client, loaded):
    r = client.post("/api/stocks/XU100/refresh")
    assert r.status_code == 400


def test_unknown_symbol_404(client, loaded):
    assert client.get("/api/stocks/YOKK/prices").status_code == 404
