"""Veri toplama işleri. Her fonksiyon bir oturum ve adapter alır, JobOutcome döner.

Kurallar: eksik veri doldurulmaz; her satır kaynağını ve çekilme zamanını taşır;
bir hissede hata olursa diğer hisselere devam edilir (iş "partial" olur).
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.text import normalize_search
from app.db.models import (
    DataSource,
    FinancialStatement,
    KapDisclosure,
    MacroObservation,
    News,
    NewsStock,
    Sector,
    Stock,
    StockPrice,
)
from app.ingest.runner import JobOutcome
from app.normalize.financials import (
    financial_groups,
    inflation_status,
    is_cumulative,
    sector_profile,
    statement_type,
)
from app.normalize.news_match import build_keys, match
from app.sources.base import SourceError
from app.sources.evds import SERIES, EvdsSource
from app.sources.isyatirim import IsYatirimSource, bar_time, period_end, recent_quarters
from app.sources.kap import KapSource
from app.sources.rss import FEEDS, RssSource, google_news_url
from app.sources.tcmb_fx import TcmbFxSource

log = logging.getLogger(__name__)

PRICE_HISTORY_DAYS = 3 * 365 + 10
ADJUSTMENT_DRIFT = Decimal("0.005")  # düzeltilmiş kapanışta %0,5'ten büyük fark → geçmişi yeniden çek
INDEX_STOCKS = {"XU100": "BIST 100"}


def _source_id(s: Session, code: str) -> int:
    sid = s.scalar(select(DataSource.id).where(DataSource.code == code))
    if sid is None:
        raise RuntimeError(f"data_sources içinde '{code}' yok")
    return sid


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- şirketler ve sektörler

def sync_companies(s: Session, kap: KapSource) -> JobOutcome:
    companies = kap.companies()
    memberships = kap.sectors()
    src = _source_id(s, "kap")

    # Sektörler: ana sektör + alt sektör (KAP oid ile)
    sectors_by_oid = {x.kap_oid: x for x in s.scalars(select(Sector)) if x.kap_oid}
    sectors_by_name = {x.name: x for x in s.scalars(select(Sector))}

    def upsert_sector(oid: str, name: str, no: str, profile: str, parent: Sector | None) -> Sector:
        sec = sectors_by_oid.get(oid) or sectors_by_name.get(name)
        if sec is None:
            sec = Sector(name=name)
            s.add(sec)
        sec.kap_oid, sec.sector_no, sec.analysis_profile = oid, no, profile
        sec.parent = parent if parent is not sec else None
        sectors_by_oid[oid], sectors_by_name[name] = sec, sec
        return sec

    sector_for_symbol: dict[str, Sector] = {}
    for m in memberships:
        main = upsert_sector(m.main_oid, m.main_name, m.main_no, sector_profile(m.main_name, m.main_name), None)
        if m.sub_name == m.main_name:
            sector_for_symbol[m.symbol] = main  # alt sektör adı ana sektörle aynıysa ana sektör kullanılır
            continue
        sub = upsert_sector(m.sub_oid, m.sub_name, m.sub_no, sector_profile(m.sub_name, m.main_name), main)
        sector_for_symbol[m.symbol] = sub
    s.flush()

    existing = {x.symbol: x for x in s.scalars(select(Stock))}
    seen: set[str] = set()
    for c in companies:
        for sym in c.symbols:
            seen.add(sym)
            st = existing.get(sym)
            if st is None:
                st = Stock(symbol=sym, instrument_type="equity")
                s.add(st)
                existing[sym] = st
            st.name = c.title
            st.search_name = normalize_search(f"{sym} {c.title}")
            st.kap_member_oid = c.mkk_oid
            st.is_active = True
            st.source_id = src
            sec = sector_for_symbol.get(sym)
            st.sector_id = sec.id if sec else st.sector_id

    for sym, name in INDEX_STOCKS.items():
        if sym not in existing:
            s.add(Stock(symbol=sym, name=name, search_name=normalize_search(f"{sym} {name}"), instrument_type="index"))

    # KAP listesinde artık olmayan hisseler pasif yapılır. Liste şüpheli derecede kısaysa dokunulmaz.
    active_before = [x for x in existing.values() if x.instrument_type == "equity" and x.is_active]
    deactivated = 0
    if len(seen) >= 0.8 * len(active_before):
        for x in active_before:
            if x.symbol not in seen:
                x.is_active = False
                deactivated += 1
    s.flush()
    return JobOutcome(
        rows=len(seen),
        message=f"{len(companies)} şirket, {len(seen)} hisse kodu, {len(sector_for_symbol)} sektör eşleşmesi, "
                f"{deactivated} hisse pasif yapıldı",
    )


# ---------------------------------------------------------------- fiyatlar

def _upsert_bars(s: Session, stock_id: int, source_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    for r in rows:
        r.update(stock_id=stock_id, source_id=source_id, interval="1d", freshness="end_of_day", fetched_at=_now())
    stmt = pg_insert(StockPrice).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_stock_prices_bar",
        set_={k: stmt.excluded[k] for k in ("open", "high", "low", "close", "avg_price", "turnover", "fetched_at")},
    )
    s.execute(stmt)
    return len(rows)


def sync_prices_for(s: Session, isy: IsYatirimSource, symbol: str, today: date, index_done: set[str]) -> int:
    stock = s.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        raise SourceError("isyatirim", f"{symbol} hisse listesinde yok")
    src = _source_id(s, "isyatirim")
    full_start = today - timedelta(days=PRICE_HISTORY_DAYS)

    last = s.scalar(select(func.max(StockPrice.ts)).where(
        StockPrice.stock_id == stock.id, StockPrice.source_id == src, StockPrice.is_adjusted.is_(True)))
    start = (last.date() - timedelta(days=7)) if last else full_start
    batch = isy.daily_prices(symbol, start, today)

    # Bölünme/temettü sonrası kaynak düzeltilmiş geçmişi yeniden hesaplar → farkı fark edince tümünü yenile
    if last and batch.bars:
        stored = dict(s.execute(select(StockPrice.ts, StockPrice.close).where(
            StockPrice.stock_id == stock.id, StockPrice.source_id == src, StockPrice.is_adjusted.is_(True),
            StockPrice.ts >= bar_time(start))).all())
        for b in batch.bars:
            old = stored.get(bar_time(b.day))
            if b.adjusted and old and b.close and abs(b.close - old) / old > ADJUSTMENT_DRIFT:
                log.info("%s: düzeltilmiş fiyat geçmişi değişmiş, 3 yıl yeniden çekiliyor", symbol)
                batch = isy.daily_prices(symbol, full_start, today)
                s.execute(delete(StockPrice).where(
                    StockPrice.stock_id == stock.id, StockPrice.source_id == src, StockPrice.is_adjusted.is_(True)))
                break

    rows = [dict(ts=bar_time(b.day), is_adjusted=b.adjusted, open=None, high=b.high, low=b.low, close=b.close,
                 avg_price=b.avg_price, turnover=b.turnover) for b in batch.bars]
    written = 0
    for i in range(0, len(rows), 1000):
        written += _upsert_bars(s, stock.id, src, rows[i:i + 1000])

    if batch.xu100 and "XU100" not in index_done:
        idx = s.scalar(select(Stock).where(Stock.symbol == "XU100"))
        if idx is not None:
            idx_rows = [dict(ts=bar_time(d), is_adjusted=False, open=None, high=None, low=None, close=v,
                             avg_price=None, turnover=None) for d, v in batch.xu100]
            written += _upsert_bars(s, idx.id, src, idx_rows)
            index_done.add("XU100")

    if batch.paid_in_capital:
        stock.paid_in_capital_as_of, stock.paid_in_capital = batch.paid_in_capital
    return written


def sync_prices(s: Session, isy: IsYatirimSource, symbols: list[str], today: date | None = None) -> JobOutcome:
    today = today or date.today()
    total, failed, index_done = 0, [], set()
    for sym in symbols:
        try:
            with s.begin_nested():
                total += sync_prices_for(s, isy, sym, today, index_done)
        except SourceError as exc:
            failed.append(f"{sym}: {exc.message}")
    msg = f"{len(symbols) - len(failed)}/{len(symbols)} hisse güncellendi"
    if failed:
        msg += "; hatalar: " + "; ".join(failed[:20])
    if failed and len(failed) == len(symbols):
        raise SourceError("isyatirim", msg)
    return JobOutcome(rows=total, message=msg, partial=bool(failed))


# ---------------------------------------------------------------- finansal tablolar

def sync_financials_for(s: Session, isy: IsYatirimSource, symbol: str, quarters: int, today: date) -> int:
    stock = s.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None or stock.instrument_type != "equity":
        raise SourceError("isyatirim", f"{symbol} hisse listesinde yok")
    profile = stock.sector.analysis_profile if stock.sector else "general"
    periods = recent_quarters(today, quarters)

    values = []
    for group in financial_groups(profile):
        values = isy.statements(symbol, group, periods)
        if values:
            break
    if not values:
        return 0

    # Henüz açıklanmamış dönemler bütün kalemleri boş/sıfır gelebilir → o dönem atlanır
    nonzero = defaultdict(bool)
    for v in values:
        if v.value not in (None, 0):
            nonzero[(v.fiscal_year, v.fiscal_period)] = True

    src = _source_id(s, "isyatirim")
    rows = []
    for v in values:
        st_type = statement_type(v.item_code)
        if st_type is None or not nonzero[(v.fiscal_year, v.fiscal_period)]:
            continue
        pe = period_end(v.fiscal_year, v.fiscal_period)
        adjusted, basis = inflation_status(pe, profile)
        rows.append(dict(
            stock_id=stock.id, source_id=src, statement_type=st_type, fiscal_year=v.fiscal_year,
            fiscal_period=v.fiscal_period, period_end=pe, is_cumulative=is_cumulative(st_type),
            consolidation="unknown", inflation_adjusted=adjusted, inflation_basis=basis, currency="TRY",
            item_code=v.item_code, item_name_tr=v.name_tr, item_name_en=v.name_en, value=v.value, fetched_at=_now(),
        ))
    for i in range(0, len(rows), 1000):
        stmt = pg_insert(FinancialStatement).values(rows[i:i + 1000])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_financial_statements_item",
            set_={k: stmt.excluded[k] for k in ("value", "item_name_tr", "item_name_en", "inflation_basis", "fetched_at")},
        )
        s.execute(stmt)
    return len(rows)


def sync_financials(s: Session, isy: IsYatirimSource, symbols: list[str], quarters: int = 16,
                    today: date | None = None) -> JobOutcome:
    today = today or date.today()
    total, failed, empty = 0, [], []
    for sym in symbols:
        try:
            with s.begin_nested():
                n = sync_financials_for(s, isy, sym, quarters, today)
                total += n
                if n == 0:
                    empty.append(sym)
        except SourceError as exc:
            failed.append(f"{sym}: {exc.message}")
    msg = f"{len(symbols) - len(failed)}/{len(symbols)} hisse işlendi"
    if empty:
        msg += "; tablo bulunamayan: " + ", ".join(empty[:20])
    if failed:
        msg += "; hatalar: " + "; ".join(failed[:20])
    if failed and len(failed) == len(symbols):
        raise SourceError("isyatirim", msg)
    return JobOutcome(rows=total, message=msg, partial=bool(failed))


# ---------------------------------------------------------------- KAP bildirimleri

def sync_disclosures(s: Session, kap: KapSource, days: int = 3, today: date | None = None) -> JobOutcome:
    today = today or date.today()
    src = _source_id(s, "kap")
    last = s.scalar(select(func.max(KapDisclosure.published_at)))
    start = max(last.date() - timedelta(days=1), today - timedelta(days=30)) if last else today - timedelta(days=days)
    symbol_to_id = dict(s.execute(select(Stock.symbol, Stock.id)).all())

    inserted = 0
    cursor = start
    while cursor <= today:
        end = min(cursor + timedelta(days=6), today)
        rows = kap.disclosures(cursor, end)
        values = []
        for d in rows:
            stock_id = next((symbol_to_id[x] for x in d.symbols if x in symbol_to_id), None)
            values.append(dict(
                source_id=src, kap_index=d.index, stock_id=stock_id, company_title=d.company_title[:300],
                published_at=d.published_at, disclosure_class=d.disclosure_class, disclosure_type=d.disclosure_type,
                subject=(d.subject or "")[:500] or None, summary=d.summary, url=d.url,
                attachment_count=d.attachment_count, fetched_at=_now(),
            ))
        for i in range(0, len(values), 1000):
            res = s.execute(pg_insert(KapDisclosure).values(values[i:i + 1000])
                            .on_conflict_do_nothing(index_elements=["kap_index"]).returning(KapDisclosure.id))
            inserted += len(res.all())
        cursor = end + timedelta(days=1)
    return JobOutcome(rows=inserted, message=f"{start} – {today}: {inserted} yeni bildirim")


# ---------------------------------------------------------------- makro

def _upsert_macro(s: Session, src: int, series_code: str, name: str, freq: str, unit: str,
                  points: list[tuple[date, Decimal]]) -> int:
    if not points:
        return 0
    rows = [dict(source_id=src, series_code=series_code, series_name=name, frequency=freq, obs_date=d, value=v,
                 unit=unit, fetched_at=_now()) for d, v in points]
    stmt = pg_insert(MacroObservation).values(rows)
    stmt = stmt.on_conflict_do_update(constraint="uq_macro_observations",
                                      set_={"value": stmt.excluded.value, "fetched_at": stmt.excluded.fetched_at})
    s.execute(stmt)
    return len(rows)


STALE_AFTER = {"daily": 10, "weekly": 21, "monthly": 95}


def sync_evds(s: Session, evds: EvdsSource, today: date | None = None, years: int = 5) -> JobOutcome:
    today = today or date.today()
    src = _source_id(s, "evds")
    total, notes, failed = 0, [], []
    for sd in SERIES:
        last = s.scalar(select(func.max(MacroObservation.obs_date)).where(
            MacroObservation.source_id == src, MacroObservation.series_code == sd.code))
        start = (last - timedelta(days=40)) if last else today.replace(year=today.year - years)
        try:
            points = evds.series(sd, start, today)
        except SourceError as exc:
            failed.append(f"{sd.code}: {exc.message}")
            continue
        total += _upsert_macro(s, src, sd.code, sd.name, sd.frequency, sd.unit, points)
        newest = max((d for d, _ in points), default=last)
        if newest is None or (today - newest).days > STALE_AFTER[sd.frequency]:
            notes.append(f"{sd.code} eski: son değer {newest}")
    if failed and len(failed) == len(SERIES):
        raise SourceError("evds", "; ".join(failed))
    msg = "; ".join(notes + failed) or None
    return JobOutcome(rows=total, message=msg, partial=bool(failed))


def sync_tcmb_fx(s: Session, fx: TcmbFxSource) -> JobOutcome:
    src = _source_id(s, "tcmb_fx")
    day, rates = fx.today()
    total = 0
    for cur, value in rates.items():
        total += _upsert_macro(s, src, f"TCMB.{cur}.FOREX_BUYING", f"{cur}/TRY döviz alış (TCMB gösterge)",
                               "daily", "TL", [(day, value)])
    return JobOutcome(rows=total, message=f"{day}: {', '.join(rates)}")


# ---------------------------------------------------------------- haberler

DUPLICATE_WINDOW = timedelta(days=3)


def sync_news(s: Session, rss: RssSource, query_symbols: list[str] | None = None) -> JobOutcome:
    src = _source_id(s, "rss")
    equities = s.execute(select(Stock.id, Stock.symbol, Stock.name).where(
        Stock.instrument_type == "equity", Stock.is_active.is_(True))).all()
    keys = build_keys([(i, sym, name) for i, sym, name in equities])
    symbol_to_id = {sym: i for i, sym, _ in equities}

    feeds = [(url, pub, None) for pub, url in FEEDS.items()]
    feeds += [(google_news_url(f'"{sym}" hisse'), "Google Haberler", sym) for sym in (query_symbols or [])]

    inserted, links, failed = 0, 0, []
    for url, publisher, query_symbol in feeds:
        try:
            items = rss.fetch(url, publisher)
        except SourceError as exc:
            failed.append(f"{publisher}{' ' + query_symbol if query_symbol else ''}: {exc.message}")
            continue
        for it in items:
            if s.scalar(select(News.id).where(News.url == it.url)):
                continue
            ref_time = it.published_at or _now()
            dup = s.scalar(select(News.id).where(
                News.content_hash == it.content_hash, News.duplicate_of_id.is_(None),
                News.published_at.between(ref_time - DUPLICATE_WINDOW, ref_time + DUPLICATE_WINDOW)).limit(1))
            n = News(source_id=src, url=it.url, title=it.title, summary=it.summary, publisher=it.publisher,
                     published_at=it.published_at, content_hash=it.content_hash, duplicate_of_id=dup)
            s.add(n)
            s.flush()
            inserted += 1
            matched = match(f"{it.title} {it.summary or ''}", keys)
            if query_symbol and symbol_to_id.get(query_symbol) not in matched:
                matched.setdefault(symbol_to_id[query_symbol], "query")
            for stock_id, mtype in matched.items():
                s.add(NewsStock(news_id=n.id, stock_id=stock_id, match_type=mtype))
                links += 1
    if failed and len(failed) == len(feeds):
        raise SourceError("rss", "; ".join(failed))
    msg = f"{inserted} yeni haber, {links} hisse eşleşmesi"
    if failed:
        msg += "; hatalar: " + "; ".join(failed)
    return JobOutcome(rows=inserted, message=msg, partial=bool(failed))


def rematch_news(s: Session) -> JobOutcome:
    """Eşleştirme kuralları değişince bütün haberleri yeniden eşleştirir ("query" eşleşmeleri korunur)."""
    equities = s.execute(select(Stock.id, Stock.symbol, Stock.name).where(
        Stock.instrument_type == "equity", Stock.is_active.is_(True))).all()
    keys = build_keys([(i, sym, name) for i, sym, name in equities])
    s.execute(delete(NewsStock).where(NewsStock.match_type.in_(("symbol", "name"))))
    existing = {(a, b) for a, b in s.execute(select(NewsStock.news_id, NewsStock.stock_id))}
    links = 0
    for nid, title, summary in s.execute(select(News.id, News.title, News.summary)).all():
        for stock_id, mtype in match(f"{title} {summary or ''}", keys).items():
            if (nid, stock_id) not in existing:
                s.add(NewsStock(news_id=nid, stock_id=stock_id, match_type=mtype))
                links += 1
    return JobOutcome(rows=links, message=f"{links} hisse eşleşmesi")
