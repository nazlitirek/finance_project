"""Veri işleri: sahte adapterlerle (internet yok) veritabanına yazma testleri."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models import (
    DataSource,
    DataUpdateLog,
    FinancialStatement,
    KapDisclosure,
    MacroObservation,
    News,
    NewsStock,
    Sector,
    Stock,
    StockPrice,
)
from app.ingest import jobs
from app.ingest.runner import JobOutcome, run_job
from app.sources.base import TR_TZ, SourceError
from app.sources.evds import SeriesDef
from app.sources.isyatirim import DailyBar, PriceBatch, StatementValue
from app.sources.kap import KapCompany, KapDisclosureRow, KapSectorMembership
from app.sources.rss import NewsItem

TODAY = date(2026, 11, 21)


class FakeKap:
    def __init__(self, companies=None, sectors=None, disclosures=None):
        self._c = companies if companies is not None else [
            KapCompany("o1", "TÜRK HAVA YOLLARI A.O.", ("THYAO",), "İSTANBUL"),
            KapCompany("o2", "TÜRKİYE İŞ BANKASI A.Ş.", ("ISCTR", "ISATR"), "İSTANBUL"),
        ]
        self._s = sectors if sectors is not None else [
            KapSectorMembership("ULAŞTIRMA VE DEPOLAMA", "m1", "007000.", "ULAŞTIRMA VE DEPOLAMA", "s1",
                                "007000.001000.", "o1", "THYAO"),
            KapSectorMembership("MALİ KURULUŞLAR", "m2", "008000.", "BANKALAR", "s2", "008000.001000.", "o2", "ISCTR"),
            KapSectorMembership("MALİ KURULUŞLAR", "m2", "008000.", "BANKALAR", "s2", "008000.001000.", "o2", "ISATR"),
        ]
        self._d = disclosures or []

    def companies(self):
        return self._c

    def sectors(self):
        return self._s

    def disclosures(self, start, end):
        return [d for d in self._d if start <= d.published_at.date() <= end]


def bar(day, close, adjusted=True):
    c = Decimal(str(close))
    return DailyBar("THYAO", day, adjusted, c, c + 1, c - 1, c, Decimal("1000000"))


class FakeIsy:
    def __init__(self):
        self.price_calls = []
        self.adjusted_close = {date(2026, 11, 19): 320, date(2026, 11, 20): 329}
        self.statement_values = []
        self.fail = set()

    def daily_prices(self, symbol, start, end):
        self.price_calls.append((symbol, start, end))
        if symbol in self.fail:
            raise SourceError("isyatirim", "HTTP 500")
        bars = []
        for d, c in self.adjusted_close.items():
            if start <= d <= end:
                bars += [bar(d, c, True), bar(d, c, False)]
        return PriceBatch(bars, [(d, Decimal("11000")) for d in self.adjusted_close if start <= d <= end],
                          (max(self.adjusted_close), Decimal("1380000000")))

    def statements(self, symbol, group, periods):
        return self.statement_values if group in ("XI_29", "UFRS") else []


@pytest.fixture
def companies(db):
    out = jobs.sync_companies(db, FakeKap())
    db.flush()
    return out


# ---------------------------------------------------------------- şirketler

def test_companies_and_sectors(db, companies):
    stocks = {s.symbol: s for s in db.scalars(select(Stock))}
    assert {"THYAO", "ISCTR", "ISATR", "XU100"} <= set(stocks)
    assert stocks["XU100"].instrument_type == "index"
    assert stocks["ISATR"].sector.name == "BANKALAR" and stocks["ISATR"].sector.analysis_profile == "bank"
    assert stocks["ISATR"].sector.parent.name == "MALİ KURULUŞLAR"
    assert stocks["THYAO"].sector.name == "ULAŞTIRMA VE DEPOLAMA"  # alt = ana → ana sektör
    assert stocks["THYAO"].search_name == "thyao turk hava yollari a.o."


def test_companies_deactivates_missing_but_guards_short_lists(db, companies):
    # Liste biraz kısaldı (3/3 → 2/3 ≈ %67 < %80) → kimse pasif yapılmaz
    jobs.sync_companies(db, FakeKap(companies=[KapCompany("o1", "TÜRK HAVA YOLLARI A.O.", ("THYAO",), None),
                                               KapCompany("o2", "İŞ BANKASI", ("ISCTR",), None)]))
    assert db.scalar(select(Stock.is_active).where(Stock.symbol == "ISATR")) is True


# ---------------------------------------------------------------- fiyatlar

def _count(db, model, *where):
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_prices_write_both_series_index_and_capital(db, companies):
    isy = FakeIsy()
    out = jobs.sync_prices(db, isy, ["THYAO"], TODAY)
    assert out.rows == 4 + 2 and not out.partial
    thy = db.scalar(select(Stock).where(Stock.symbol == "THYAO"))
    assert _count(db, StockPrice, StockPrice.stock_id == thy.id) == 4
    assert thy.paid_in_capital == Decimal("1380000000")
    xu = db.scalar(select(Stock).where(Stock.symbol == "XU100"))
    assert _count(db, StockPrice, StockPrice.stock_id == xu.id) == 2
    assert db.scalar(select(StockPrice.open).where(StockPrice.stock_id == thy.id).limit(1)) is None
    assert isy.price_calls[0][1] < date(2024, 1, 1)  # ilk çekim 3 yıl geriye


def test_prices_incremental_and_idempotent(db, companies):
    isy = FakeIsy()
    jobs.sync_prices(db, isy, ["THYAO"], TODAY)
    jobs.sync_prices(db, isy, ["THYAO"], TODAY)
    thy = db.scalar(select(Stock.id).where(Stock.symbol == "THYAO"))
    assert _count(db, StockPrice, StockPrice.stock_id == thy) == 4
    assert isy.price_calls[1][1] == date(2026, 11, 13)  # son kayıt − 7 gün


def test_prices_refetch_history_when_adjustment_changes(db, companies):
    isy = FakeIsy()
    jobs.sync_prices(db, isy, ["THYAO"], TODAY)
    isy.adjusted_close = {date(2026, 11, 19): 160, date(2026, 11, 20): 164.5}  # 2:1 bölünme sonrası düzeltme
    jobs.sync_prices(db, isy, ["THYAO"], TODAY)
    assert len(isy.price_calls) == 3 and isy.price_calls[2][1] < date(2024, 1, 1)
    thy = db.scalar(select(Stock.id).where(Stock.symbol == "THYAO"))
    closes = db.scalars(select(StockPrice.close).where(
        StockPrice.stock_id == thy, StockPrice.is_adjusted.is_(True)).order_by(StockPrice.ts)).all()
    assert closes == [Decimal("160"), Decimal("164.5")]


def test_prices_one_failure_makes_job_partial(db, companies):
    isy = FakeIsy()
    isy.fail = {"ISCTR"}
    out = jobs.sync_prices(db, isy, ["THYAO", "ISCTR", "NOPE"], TODAY)
    assert out.partial and "1/3" in out.message
    assert _count(db, StockPrice) > 0


def test_prices_all_failed_raises(db, companies):
    isy = FakeIsy()
    isy.fail = {"THYAO"}
    with pytest.raises(SourceError):
        jobs.sync_prices(db, isy, ["THYAO"], TODAY)


# ---------------------------------------------------------------- finansal tablolar

def test_financials_flags_and_skips_unreported_periods(db, companies):
    isy = FakeIsy()
    isy.statement_values = [
        StatementValue("3C", "Satış Gelirleri", "Revenue", 2026, 9, Decimal("981")),
        StatementValue("1A", "Dönen Varlıklar", "Current assets", 2026, 9, Decimal("500")),
        StatementValue("3C", "Satış Gelirleri", "Revenue", 2023, 9, Decimal("100")),
        StatementValue("3C", "Satış Gelirleri", "Revenue", 2026, 12, Decimal("0")),  # açıklanmamış dönem
        StatementValue("9Z", "Bilinmeyen", None, 2026, 9, Decimal("1")),
    ]
    jobs.sync_financials(db, isy, ["THYAO", "ISCTR"], quarters=4, today=TODAY)
    rows = db.execute(select(Stock.symbol, FinancialStatement.item_code, FinancialStatement.fiscal_year,
                             FinancialStatement.statement_type, FinancialStatement.is_cumulative,
                             FinancialStatement.inflation_adjusted)
                      .join(Stock).order_by(Stock.symbol, FinancialStatement.fiscal_year,
                                            FinancialStatement.item_code)).all()
    assert ("THYAO", "3C", 2026, "income", True, True) in rows
    assert ("THYAO", "1A", 2026, "balance", False, True) in rows
    assert ("THYAO", "3C", 2023, "income", True, False) in rows
    assert ("ISCTR", "3C", 2026, "income", True, None) in rows  # banka → bilinmiyor
    assert not any(r[2] == 2026 and r[1] == "3C" and r[0] == "THYAO" and r[3] != "income" for r in rows)
    assert all(code != "9Z" for _, code, *_ in rows)
    assert _count(db, FinancialStatement, FinancialStatement.fiscal_period == 12) == 0
    # tekrar çalıştırınca satır sayısı değişmez (NULL içeren benzersizlik dahil)
    before = _count(db, FinancialStatement)
    jobs.sync_financials(db, isy, ["THYAO", "ISCTR"], quarters=4, today=TODAY)
    assert _count(db, FinancialStatement) == before


# ---------------------------------------------------------------- KAP bildirimleri

def test_disclosures_linked_and_idempotent(db, companies):
    d = KapDisclosureRow(1700896, datetime(2026, 11, 20, 23, 51, tzinfo=TR_TZ), "TÜRK HAVA YOLLARI A.O.",
                         ("THYAO",), "ODA", "CA", "STT", "Özel Durum", "özet", 0)
    other = KapDisclosureRow(1700897, datetime(2026, 11, 20, 12, 0, tzinfo=TR_TZ), "BİLİNMEYEN A.Ş.",
                             ("YOKK",), "DG", None, None, None, None, 0)
    kap = FakeKap(disclosures=[d, other])
    assert jobs.sync_disclosures(db, kap, days=3, today=TODAY).rows == 2
    assert jobs.sync_disclosures(db, kap, days=3, today=TODAY).rows == 0
    thy = db.scalar(select(Stock.id).where(Stock.symbol == "THYAO"))
    assert db.scalar(select(KapDisclosure.stock_id).where(KapDisclosure.kap_index == 1700896)) == thy
    assert db.scalar(select(KapDisclosure.stock_id).where(KapDisclosure.kap_index == 1700897)) is None


# ---------------------------------------------------------------- makro

class FakeEvds:
    def series(self, s, start, end):
        if s.code == "BAD":
            raise SourceError("evds", "HTTP 400")
        return [(date(2026, 11, 20), Decimal("50.37"))] if s.frequency == "daily" else [(date(2026, 1, 1), Decimal("3683"))]


def test_evds_partial_and_stale_note(db, monkeypatch):
    monkeypatch.setattr(jobs, "SERIES", [SeriesDef("TP.DK.USD.A", "USD", "daily", "TL"),
                                         SeriesDef("TP.FG.J0", "TÜFE", "monthly", "endeks"),
                                         SeriesDef("BAD", "bozuk", "daily", "%")])
    out = jobs.sync_evds(db, FakeEvds(), today=TODAY)
    assert out.partial and out.rows == 2
    assert "TP.FG.J0 eski" in out.message and "BAD" in out.message
    assert _count(db, MacroObservation) == 2


# ---------------------------------------------------------------- haberler

class FakeRss:
    def __init__(self, feeds):
        self.feeds = feeds

    def fetch(self, url, publisher):
        if publisher not in self.feeds:
            raise SourceError("rss", "HTTP 503")
        return self.feeds[publisher]


def test_news_match_duplicates_and_partial(db, companies, monkeypatch):
    t = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(jobs, "FEEDS", {"A": "https://a.test", "B": "https://b.test", "C": "https://c.test"})
    rss = FakeRss({
        "A": [NewsItem("https://a.test/1", "THYAO rekor kırdı", None, "A", t)],
        "B": [NewsItem("https://b.test/1", "THYAO rekor kırdı - Hisse.net", None, "B", t),
              NewsItem("https://b.test/2", "Hava durumu", None, "B", t)],
    })
    out = jobs.sync_news(db, rss)
    assert out.partial and out.rows == 3
    first = db.scalar(select(News).where(News.url == "https://a.test/1"))
    copy = db.scalar(select(News).where(News.url == "https://b.test/1"))
    assert copy.duplicate_of_id == first.id
    thy = db.scalar(select(Stock.id).where(Stock.symbol == "THYAO"))
    assert _count(db, NewsStock, NewsStock.stock_id == thy) == 2
    assert jobs.sync_news(db, rss).rows == 0  # aynı URL'ler tekrar eklenmez


# ---------------------------------------------------------------- çalıştırıcı

def test_run_job_records_failure_without_raising(sm):
    def boom(s):
        raise SourceError("kap", "HTTP 503")

    res = run_job(sm, "kap", "companies", boom)
    assert res.status == "failed" and "HTTP 503" in res.message
    with sm() as s:
        log = s.scalar(select(DataUpdateLog).order_by(DataUpdateLog.id.desc()))
        assert log.status == "failed" and log.finished_at is not None
        src = s.scalar(select(DataSource).where(DataSource.code == "kap"))
        assert src.last_error_at is not None and "HTTP 503" in src.last_error


def test_run_job_success_and_disabled_source(sm):
    res = run_job(sm, "kap", "x", lambda s: JobOutcome(rows=5, message="tamam"))
    assert res.status == "success" and res.rows == 5
    assert run_job(sm, "yahoo", "prices", lambda s: JobOutcome()).status == "skipped"


def test_run_job_failure_keeps_previous_data(sm):
    with sm() as s:
        s.add(Sector(name="ESKİ VERİ"))
        s.commit()

    def half_then_fail(s):
        s.add(Sector(name="YARIM KALAN"))
        s.flush()
        raise RuntimeError("bozuldu")

    assert run_job(sm, "kap", "x", half_then_fail).status == "failed"
    with sm() as s:
        names = set(s.scalars(select(Sector.name)))
        assert "ESKİ VERİ" in names and "YARIM KALAN" not in names
