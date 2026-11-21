from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.text import normalize_search
from app.db.models import AnalysisReport, AnalysisScore, DataSource, PriceAlert, Sector, Stock


def _stock(db, symbol, name, instrument_type="equity", sector=None):
    s = Stock(symbol=symbol, name=name, search_name=normalize_search(f"{symbol} {name}"),
              instrument_type=instrument_type, sector=sector)
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def sample(db):
    air = Sector(name="Ulaştırma", analysis_profile="general")
    bank = Sector(name="Bankacılık", analysis_profile="bank")
    db.add_all([air, bank])
    _stock(db, "THYAO", "TÜRK HAVA YOLLARI A.O.", sector=air)
    _stock(db, "PGSUS", "PEGASUS HAVA TAŞIMACILIĞI A.Ş.", sector=air)
    _stock(db, "ISCTR", "TÜRKİYE İŞ BANKASI A.Ş.", sector=bank)
    _stock(db, "XU100", "BIST 100", instrument_type="index")
    db.flush()


# ---------------------------------------------------------------- migration / seed

def test_data_sources_seeded(db):
    codes = {s.code: s for s in db.scalars(select(DataSource))}
    assert {"isyatirim", "kap", "evds", "tcmb_fx", "rss", "yahoo"} <= codes.keys()
    assert codes["yahoo"].enabled is False  # koşullar otomatik toplamayı yasaklıyor
    assert codes["isyatirim"].freshness == "end_of_day"


def test_score_range_enforced(db, sample):
    stock = db.scalar(select(Stock).where(Stock.symbol == "THYAO"))
    rep = AnalysisReport(stock_id=stock.id, status="pending")
    db.add(rep)
    db.flush()
    db.add(AnalysisScore(report_id=rep.id, module="technical", score=Decimal("101"), reliability=Decimal("0.5")))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_price_alert_rejects_non_positive_target(db, sample):
    stock = db.scalar(select(Stock).where(Stock.symbol == "THYAO"))
    db.add(PriceAlert(stock_id=stock.id, condition="above", target_price=Decimal("0")))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ---------------------------------------------------------------- API

def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert any(s["code"] == "kap" for s in body["sources"])


def test_list_stocks_and_filter(client, sample):
    r = client.get("/api/stocks")
    assert r.status_code == 200
    assert r.json()["total"] == 4
    r = client.get("/api/stocks", params={"instrument_type": "index"})
    assert [s["symbol"] for s in r.json()["items"]] == ["XU100"]


@pytest.mark.parametrize(
    ("q", "first"),
    [
        ("THYAO", "THYAO"),
        ("thy", "THYAO"),
        ("türk hava", "THYAO"),
        ("TURK HAVA", "THYAO"),
        ("iş bankası", "ISCTR"),
        ("pegasus", "PGSUS"),
    ],
)
def test_search(client, sample, q, first):
    r = client.get("/api/stocks/search", params={"q": q})
    assert r.status_code == 200
    assert r.json()[0]["symbol"] == first


def test_search_exact_symbol_ranks_first(client, sample):
    r = client.get("/api/stocks/search", params={"q": "hava"})
    assert {s["symbol"] for s in r.json()} == {"THYAO", "PGSUS"}


def test_search_special_chars_are_literal(client, sample):
    r = client.get("/api/stocks/search", params={"q": "%"})
    assert r.status_code == 200 and r.json() == []


def test_search_requires_query(client):
    r = client.get("/api/stocks/search")
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_request"


def test_get_stock_with_sector(client, sample):
    r = client.get("/api/stocks/thyao")
    assert r.status_code == 200
    assert r.json() == {"symbol": "THYAO", "name": "TÜRK HAVA YOLLARI A.O.", "instrument_type": "equity",
                        "sector": "Ulaştırma", "is_active": True}


def test_unknown_stock_404_message(client):
    r = client.get("/api/stocks/YOKBOYLE")
    assert r.status_code == 404
    assert "bulunamadı" in r.json()["message"]


def test_cors_allows_local_frontend_only(client):
    ok = client.options("/api/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
