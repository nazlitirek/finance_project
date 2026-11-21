"""Analiz uç noktaları: gerçek akış (sahte kaynak verisi → veritabanı → analiz → API)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models import DataSource, FinancialRatio, MacroObservation, Stock
from app.ingest import jobs
from app.sources.isyatirim import DailyBar, PriceBatch, StatementValue
from tests.test_ingest import TODAY, FakeKap


class TrendIsy:
    """300 iş günü yükselen fiyat + 8 çeyrek finansal tablo."""

    def __init__(self):
        days, d = [], TODAY
        while len(days) < 300:
            d -= timedelta(days=1)
            if d.weekday() < 5:
                days.append(d)
        self.days = sorted(days)

    def daily_prices(self, symbol, start, end):
        bars, idx = [], []
        for i, d in enumerate(self.days):
            if start <= d <= end:
                c = Decimal(str(round(100 + i * 0.3 + (i % 7) * 0.4, 2)))
                for adj in (True, False):
                    bars.append(DailyBar(symbol, d, adj, c, c + 1, c - 1, c, Decimal("50000000")))
                idx.append((d, Decimal(str(10000 + i * 5 + (i % 5) * 3))))
        return PriceBatch(bars, idx, (self.days[-1], Decimal("1000")))

    def statements(self, symbol, group, periods):
        if group != "XI_29":
            return []
        out = []
        cum = {3: 100, 6: 210, 9: 330, 12: 460}
        for y, p in periods:
            r = cum[p] * (1.3 if y == 2026 else 1.0)
            for code, v in {"1A": 500, "1AA": 100, "1AF": 50, "1BL": 2000, "2A": 300, "2AA": 100, "2B": 500,
                            "2BA": 300, "2N": 1200, "2O": 1100, "3C": r, "3CA": -0.6 * r, "3D": 0.4 * r,
                            "3DF": 0.2 * r, "3HC": -0.03 * r, "3L": 0.12 * r, "3Z": 0.11 * r, "4B": -0.05 * r,
                            "4C": 0.15 * r, "4CAI": -0.06 * r, "4CB": 0.09 * r}.items():
                out.append(StatementValue(code, code, None, y, p, Decimal(str(v))))
        return out


@pytest.fixture
def analyzed(db):
    jobs.sync_companies(db, FakeKap())
    isy = TrendIsy()
    jobs.sync_prices(db, isy, ["THYAO"], TODAY)
    jobs.sync_financials(db, isy, ["THYAO"], quarters=8, today=TODAY)
    src = db.scalar(select(DataSource.id).where(DataSource.code == "evds"))
    for i in range(400):
        db.add(MacroObservation(source_id=src, series_code="TP.APIFON4", series_name="fonlama", frequency="daily",
                                obs_date=TODAY - timedelta(days=i), value=Decimal("36"), unit="%"))
    db.flush()


def test_full_analysis(client, db, analyzed):
    r = client.get("/api/stocks/THYAO/analysis")
    assert r.status_code == 200
    body = r.json()
    mods = body["modules"]
    assert set(mods) == {"technical", "fundamental", "financial_health", "valuation", "sector", "news", "risk"}
    for k in ("technical", "fundamental", "financial_health", "risk"):
        assert mods[k]["score"] is not None and 0 <= mods[k]["score"] <= 100, k
        assert mods[k]["meaning"]
    assert mods["technical"]["assessments"]["trend_direction"] == "up"
    assert mods["news"]["score"] is None
    assert mods["sector"]["score"] is None and "en az 5" in " ".join(mods["sector"]["notes"])
    assert body["financial_period"] == "2026/09"
    assert body["overall"]["score"] is not None and body["overall"]["disclaimer"]
    risk_notes = " ".join(mods["risk"]["notes"])
    assert "%36.00" in risk_notes and "işlem günü" in risk_notes
    # DCF: 8 çeyrek var → hesaplanır, 3 senaryo
    dcf = mods["valuation"]["extra"]["dcf"]
    assert dcf["valid"] and set(dcf["scenarios"]) == {"optimistic", "base", "pessimistic"}
    assert dcf["scenarios"]["optimistic"]["value_per_share"] > dcf["scenarios"]["pessimistic"]["value_per_share"]
    # oranlar kaydedildi ve tekrar çağrıda çoğalmadı
    n = db.scalar(select(func.count()).select_from(FinancialRatio))
    assert n > 0
    client.get("/api/stocks/THYAO/analysis")
    assert db.scalar(select(func.count()).select_from(FinancialRatio)) == n


def test_module_endpoint_and_errors(client, analyzed):
    r = client.get("/api/stocks/THYAO/analysis/risk")
    assert r.status_code == 200 and r.json()["module"] == "risk"
    assert client.get("/api/stocks/THYAO/analysis/foo").status_code == 404
    assert client.get("/api/stocks/XU100/analysis").status_code == 400
    assert client.get("/api/stocks/YOKK/analysis").status_code == 404


def test_analysis_without_financials(client, analyzed):
    body = client.get("/api/stocks/ISCTR/analysis").json()
    assert body["modules"]["fundamental"]["score"] is None
    assert body["modules"]["technical"]["score"] is None  # ISCTR için fiyat da yok
    assert body["overall"]["score"] is None
