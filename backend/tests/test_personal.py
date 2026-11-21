from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.analysis import portfolio as pf
from app.ingest import jobs
from tests.test_api_analysis import TrendIsy
from tests.test_ingest import TODAY, FakeKap

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def tx(i, side, qty, price, fee=0, sym="THYAO", days=0):
    return pf.Tx(i, sym, side, D(str(qty)), D(str(price)), D(str(fee)), T0 + timedelta(days=days))


# ---------------------------------------------------------------- portföy hesapları (bilinen değerler)

def test_weighted_average_cost_and_realized_pnl():
    pos = pf.positions([tx(1, "buy", 100, 10, fee=10), tx(2, "buy", 100, 20, days=1),
                        tx(3, "sell", 50, 25, fee=5, days=2)])["THYAO"]
    # ort. maliyet = (1000 + 10 + 2000) / 200 = 15.05
    assert pos.avg_cost == D("15.05") and pos.quantity == 150
    # gerçekleşen = 50 × (25 − 15.05) − 5 = 492.5
    assert pos.realized_pnl == D("492.5")
    assert pos.cost_basis == D("2257.5")


def test_selling_more_than_held_is_rejected():
    with pytest.raises(pf.PortfolioError):
        pf.positions([tx(1, "buy", 10, 10), tx(2, "sell", 11, 12, days=1)])


def test_order_by_date_not_insert_order():
    # satış girişi alıştan önce eklenmiş ama tarihi sonra → geçerli
    pos = pf.positions([tx(2, "sell", 5, 12, days=2), tx(1, "buy", 10, 10)])
    assert pos["THYAO"].quantity == 5


def test_valuation_totals_and_missing_price():
    pos = pf.positions([tx(1, "buy", 10, 100), tx(2, "buy", 5, 40, sym="AKBNK")])
    v = pf.valuation(pos, {"THYAO": (D("120"), "2026-11-20")})
    th = next(p for p in v["positions"] if p["symbol"] == "THYAO")
    assert th["market_value"] == 1200 and th["unrealized_pnl"] == 200 and th["unrealized_pct"] == pytest.approx(20)
    assert v["missing_prices"] == ["AKBNK"] and v["market_value"] == 1200 and v["unrealized_pnl"] == 200
    assert v["total_cost"] == 1200  # 1000 + 200 (fiyatı olmayan dahil maliyet)


def test_closed_position():
    v = pf.valuation(pf.positions([tx(1, "buy", 10, 10), tx(2, "sell", 10, 15, days=1)]), {})
    assert v["positions"][0]["closed"] and v["realized_pnl"] == 50


# ---------------------------------------------------------------- uç noktalar

@pytest.fixture
def market(db):
    jobs.sync_companies(db, FakeKap())
    isy = TrendIsy()
    jobs.sync_prices(db, isy, ["THYAO"], TODAY)
    jobs.sync_financials(db, isy, ["THYAO"], quarters=8, today=TODAY)
    db.flush()


def test_watchlist_crud(client, market):
    assert client.post("/api/watchlist", json={"symbol": "thyao"}).status_code == 201
    assert client.post("/api/watchlist", json={"symbol": "THYAO"}).status_code == 409
    assert client.post("/api/watchlist", json={"symbol": "XU100"}).status_code == 400
    items = client.get("/api/watchlist").json()["items"]
    assert items[0]["symbol"] == "THYAO" and items[0]["price"] is not None
    assert client.delete("/api/watchlist/THYAO").status_code == 204
    assert client.get("/api/watchlist").json()["items"] == []


def test_portfolio_flow(client, market):
    now = datetime.now(timezone.utc)
    r = client.post("/api/portfolio/transactions", json={
        "symbol": "THYAO", "side": "buy", "quantity": 10, "price": 100, "fee": 1, "traded_at": now.isoformat()})
    assert r.status_code == 201
    bad = client.post("/api/portfolio/transactions", json={
        "symbol": "THYAO", "side": "sell", "quantity": 11, "price": 100, "traded_at": now.isoformat()})
    assert bad.status_code == 400 and "lot" in bad.json()["message"]
    future = client.post("/api/portfolio/transactions", json={
        "symbol": "THYAO", "side": "buy", "quantity": 1, "price": 1,
        "traded_at": (now + timedelta(days=3)).isoformat()})
    assert future.status_code == 422
    p = client.get("/api/portfolio").json()
    pos = p["positions"][0]
    assert pos["quantity"] == 10 and pos["avg_cost"] == pytest.approx(100.1) and pos["price"] is not None
    assert pos["market_value"] == pytest.approx(10 * pos["price"])
    assert len(client.get("/api/portfolio/transactions").json()["items"]) == 1
    assert client.delete(f"/api/portfolio/transactions/{r.json()['id']}").status_code == 204


def test_deleting_buy_that_sells_depend_on_is_blocked(client, market):
    now = datetime.now(timezone.utc)
    b = client.post("/api/portfolio/transactions", json={"symbol": "THYAO", "side": "buy", "quantity": 10,
                                                         "price": 100, "traded_at": (now - timedelta(days=2)).isoformat()})
    client.post("/api/portfolio/transactions", json={"symbol": "THYAO", "side": "sell", "quantity": 5,
                                                     "price": 110, "traded_at": now.isoformat()})
    assert client.delete(f"/api/portfolio/transactions/{b.json()['id']}").status_code == 400


def test_alerts_flow(client, market):
    last = client.get("/api/stocks/THYAO/quote").json()["price"]
    above = client.post("/api/alerts", json={"symbol": "THYAO", "condition": "above", "target_price": last * 2})
    below = client.post("/api/alerts", json={"symbol": "THYAO", "condition": "below", "target_price": last + 1})
    assert above.json()["already_met"] is False and below.json()["already_met"] is True
    since = datetime.now(timezone.utc) - timedelta(seconds=5)
    assert client.post("/api/alerts/check").json()["triggered"] == 1
    trig = client.get("/api/alerts/triggered", params={"since": since.isoformat()}).json()["items"]
    assert [t["condition"] for t in trig] == ["below"] and trig[0]["triggered_price"] == pytest.approx(last)
    assert client.post("/api/alerts/check").json()["triggered"] == 0  # tetiklenen alarm pasif
    items = client.get("/api/alerts").json()["items"]
    fired = next(i for i in items if i["condition"] == "below")
    assert fired["is_active"] is False
    assert client.post(f"/api/alerts/{fired['id']}/reactivate").json()["is_active"] is True
    assert client.delete(f"/api/alerts/{fired['id']}").status_code == 204
    assert client.post("/api/alerts", json={"symbol": "THYAO", "condition": "x", "target_price": 1}).status_code == 422


def test_chart_with_overlays(client, market):
    r = client.get("/api/stocks/THYAO/chart", params={"range": "3m", "overlays": "sma_20,sma_200,bb"}).json()
    assert r["bars"] and set(r["overlays"]) == {"sma_20", "sma_200", "bb_upper", "bb_mid", "bb_lower"}
    assert len(r["overlays"]["sma_20"]) == len(r["bars"])  # tüm geçmişten hesaplandığı için başta boşluk yok
    assert client.get("/api/stocks/THYAO/chart", params={"range": "1d"}).json()["bars"] == []
    assert client.get("/api/stocks/THYAO/chart", params={"overlays": "foo"}).status_code == 422


def test_compare_and_dashboard(client, market):
    assert client.get("/api/compare", params={"symbols": "THYAO"}).status_code == 422
    r = client.get("/api/compare", params={"symbols": "THYAO,ISCTR"}).json()
    assert [x["symbol"] for x in r["items"]] == ["THYAO", "ISCTR"]
    assert r["items"][0]["valuation"]["pe"] is not None and r["items"][1]["price"] is None
    d = client.get("/api/dashboard").json()
    assert d["indices"][0]["symbol"] == "XU100" and d["indices"][0]["value"] is not None
    assert d["indices"][1]["value"] is None and d["indices"][1]["message"]
    assert "movers" in d and "sources" in d
