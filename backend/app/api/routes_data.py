"""Toplanan verileri sunan uç noktalar. Her yanıt kaynağı, tazeliği ve güncelleme zamanını taşır."""

from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    DataSource,
    DataUpdateLog,
    FinancialStatement,
    KapDisclosure,
    MacroObservation,
    News,
    NewsStock,
    Stock,
    StockPrice,
)
from app.db.session import get_db
from app.ingest import service
from app.ingest.jobs import STALE_AFTER
from app.sources.evds import SERIES

router = APIRouter(prefix="", tags=["veri"])

RANGES = {"1w": 7, "1m": 31, "3m": 92, "6m": 183, "1y": 366, "3y": 3 * 366}
PRICE_NOTE = ("Gün sonu verisi (İş Yatırım). Gerçek zamanlı değildir. "
              "Kaynak açılış fiyatı vermediği için açılış alanı boştur. Hacim TL cinsindendir.")


def _stock(db: Session, symbol: str) -> Stock:
    s = db.scalar(select(Stock).where(Stock.symbol == symbol.upper()))
    if s is None:
        raise HTTPException(404, f"'{symbol.upper()}' kodlu hisse bulunamadı.")
    return s


def _f(v):
    return float(v) if v is not None else None


# ---------------------------------------------------------------- fiyatlar

@router.get("/stocks/{symbol}/prices")
def prices(symbol: str, range: str = Query("1y", pattern="^(1w|1m|3m|6m|1y|3y)$"),  # noqa: A002
           adjusted: bool = True, db: Session = Depends(get_db)):
    st = _stock(db, symbol)
    adj = adjusted and st.instrument_type == "equity"  # endeks satırları düzeltilmemiş olarak saklanır
    q = (select(StockPrice).join(DataSource).where(
        StockPrice.stock_id == st.id, StockPrice.interval == "1d", StockPrice.is_adjusted.is_(adj))
        .order_by(StockPrice.ts))
    last = db.scalar(select(func.max(StockPrice.ts)).where(StockPrice.stock_id == st.id))
    if last is None:
        return {"symbol": st.symbol, "bars": [], "message": "Bu hisse için henüz fiyat verisi yok.",
                "note": PRICE_NOTE}
    start = last - timedelta(days=RANGES[range])
    rows = db.scalars(q.where(StockPrice.ts >= start)).all()
    return {
        "symbol": st.symbol, "interval": "1d", "adjusted": adj, "range": range,
        "source": "isyatirim", "freshness": "end_of_day", "note": PRICE_NOTE,
        "last_bar": last.date().isoformat(),
        "fetched_at": max((r.fetched_at for r in rows), default=None),
        "bars": [{"date": r.ts.date().isoformat(), "open": _f(r.open), "high": _f(r.high), "low": _f(r.low),
                  "close": _f(r.close), "avg_price": _f(r.avg_price), "turnover": _f(r.turnover)} for r in rows],
    }


@router.get("/stocks/{symbol}/quote")
def quote(symbol: str, db: Session = Depends(get_db)):
    st = _stock(db, symbol)
    rows = db.scalars(select(StockPrice).where(
        StockPrice.stock_id == st.id, StockPrice.interval == "1d", StockPrice.is_adjusted.is_(False))
        .order_by(desc(StockPrice.ts)).limit(2)).all()
    if not rows:
        return {"symbol": st.symbol, "name": st.name, "price": None, "message": "Fiyat verisi yok."}
    cur, prev = rows[0], (rows[1] if len(rows) > 1 else None)
    change = (cur.close - prev.close) if prev and prev.close and cur.close else None
    stale, gap = staleness(cur.ts.date())
    return {
        "symbol": st.symbol, "name": st.name, "price": _f(cur.close), "as_of": cur.ts.date().isoformat(),
        "previous_close": _f(prev.close) if prev else None,
        "change": _f(change), "change_pct": _f(change / prev.close * 100) if change is not None else None,
        "turnover": _f(cur.turnover), "freshness": "end_of_day", "source": "isyatirim",
        "fetched_at": cur.fetched_at, "note": "Son bilinen gün sonu fiyatı. Gerçek zamanlı değildir.",
        "stale": stale, "business_days_old": gap,
        "stale_message": (f"Fiyat {gap} iş günü eski. Hisse işleme kapalı olabilir veya günlük güncelleme "
                          "çalışmamış olabilir.") if stale else None,
    }


STALE_AFTER_BUSINESS_DAYS = 3


def staleness(as_of: date, today: date | None = None) -> tuple[bool, int]:
    """Son kapanıştan bu yana geçen iş günü (hafta sonu hariç; resmî tatiller hesaba katılmaz)."""
    today = today or date.today()
    gap = int(np.busday_count(as_of, today)) - 1 if today > as_of else 0
    gap = max(gap, 0)
    return gap > STALE_AFTER_BUSINESS_DAYS, gap


@router.get("/market/movers")
def movers(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Son işlem gününde en çok yükselen / düşen / en yüksek hacimli hisseler (düzeltilmemiş kapanış)."""
    # Düzeltilmiş (is_adjusted) satırlar sadece hisselerde var → endeksleri ayırmak için birleştirme gerekmez,
    # sorgu ix_stock_prices_day indeksinden okunur.
    day = select(func.max(StockPrice.ts)).where(StockPrice.interval == "1d", StockPrice.is_adjusted.is_(True))
    last_day = db.scalar(day)
    if last_day is None:
        return {"as_of": None, "gainers": [], "losers": [], "turnover": [], "coverage": 0,
                "message": "Henüz fiyat verisi yok."}
    prev_day = db.scalar(day.where(StockPrice.ts < last_day))
    cur = (select(StockPrice.stock_id, StockPrice.close, StockPrice.turnover)
           .where(StockPrice.interval == "1d", StockPrice.ts == last_day, StockPrice.is_adjusted.is_(False))
           .subquery())
    prev = (select(StockPrice.stock_id, StockPrice.close.label("prev_close"))
            .where(StockPrice.interval == "1d", StockPrice.ts == prev_day, StockPrice.is_adjusted.is_(False))
            .subquery())
    rows = db.execute(select(Stock.symbol, Stock.name, cur.c.close, prev.c.prev_close, cur.c.turnover)
                      .join(cur, cur.c.stock_id == Stock.id).join(prev, prev.c.stock_id == Stock.id)
                      .where(Stock.instrument_type == "equity")).all()
    items = [{"symbol": r.symbol, "name": r.name, "close": _f(r.close),
              "change_pct": _f((r.close - r.prev_close) / r.prev_close * 100), "turnover": _f(r.turnover)}
             for r in rows if r.close and r.prev_close]
    total = db.scalar(select(func.count()).select_from(Stock).where(
        Stock.instrument_type == "equity", Stock.is_active.is_(True)))
    return {
        "as_of": last_day.date().isoformat(), "coverage": len(items), "active_stocks": total,
        "note": f"{total} aktif hissenin {len(items)} tanesi için iki günlük veri var." if len(items) < (total or 0)
        else None,
        "gainers": sorted(items, key=lambda x: -x["change_pct"])[:limit],
        "losers": sorted(items, key=lambda x: x["change_pct"])[:limit],
        "turnover": sorted(items, key=lambda x: -(x["turnover"] or 0))[:limit],
        "freshness": "end_of_day", "source": "isyatirim",
    }


# ---------------------------------------------------------------- finansal tablolar

@router.get("/stocks/{symbol}/financials")
def financials(symbol: str, statement: str = Query("income", pattern="^(balance|income|cashflow)$"),
               periods: int = Query(8, ge=1, le=16), db: Session = Depends(get_db)):
    st = _stock(db, symbol)
    keys = db.execute(select(FinancialStatement.fiscal_year, FinancialStatement.fiscal_period).where(
        FinancialStatement.stock_id == st.id, FinancialStatement.statement_type == statement).distinct()
        .order_by(desc(FinancialStatement.fiscal_year), desc(FinancialStatement.fiscal_period)).limit(periods)).all()
    if not keys:
        return {"symbol": st.symbol, "statement": statement, "periods": [], "items": [],
                "message": "Bu tablo için veri yok. Bankalar ve sigorta şirketleri için kaynak nakit akış tablosu vermiyor."
                if statement == "cashflow" else "Bu hisse için finansal tablo henüz çekilmedi."}
    wanted = {(y, p) for y, p in keys}
    rows = db.scalars(select(FinancialStatement).where(
        FinancialStatement.stock_id == st.id, FinancialStatement.statement_type == statement)
        .order_by(FinancialStatement.item_code)).all()
    rows = [r for r in rows if (r.fiscal_year, r.fiscal_period) in wanted]
    meta, items = {}, defaultdict(dict)
    names = {}
    for r in rows:
        k = f"{r.fiscal_year}/{r.fiscal_period:02d}"
        meta[k] = {"key": k, "fiscal_year": r.fiscal_year, "fiscal_period": r.fiscal_period,
                   "period_end": r.period_end.isoformat(), "is_cumulative": r.is_cumulative,
                   "inflation_adjusted": r.inflation_adjusted, "inflation_basis": r.inflation_basis}
        items[r.item_code][k] = _f(r.value)
        names[r.item_code] = r.item_name_tr
    ordered = sorted(meta.values(), key=lambda m: (m["fiscal_year"], m["fiscal_period"]), reverse=True)
    return {
        "symbol": st.symbol, "statement": statement, "currency": "TRY", "unit": "TL",
        "consolidation": "unknown", "source": "isyatirim",
        "fetched_at": max(r.fetched_at for r in rows),
        "note": ("Gelir ve nakit akış kalemleri yıl başından itibaren kümülatiftir. "
                 "Kaynak, tablonun konsolide mi solo mu olduğunu belirtmiyor."),
        "periods": ordered,
        "items": [{"code": c, "name": names[c], "values": items[c]} for c in sorted(items)],
    }


# ---------------------------------------------------------------- KAP ve haberler

def _disclosure_out(d: KapDisclosure, symbol: str | None = None) -> dict:
    return {"kap_index": d.kap_index, "symbol": symbol, "company": d.company_title,
            "published_at": d.published_at, "class": d.disclosure_class, "subject": d.subject,
            "summary": d.summary, "url": d.url, "attachment_count": d.attachment_count, "fetched_at": d.fetched_at}


@router.get("/stocks/{symbol}/disclosures")
def stock_disclosures(symbol: str, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    st = _stock(db, symbol)
    rows = db.scalars(select(KapDisclosure).where(KapDisclosure.stock_id == st.id)
                      .order_by(desc(KapDisclosure.published_at)).limit(limit)).all()
    return {"symbol": st.symbol, "source": "kap", "items": [_disclosure_out(d, st.symbol) for d in rows]}


@router.get("/disclosures")
def latest_disclosures(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.execute(select(KapDisclosure, Stock.symbol).outerjoin(Stock, Stock.id == KapDisclosure.stock_id)
                      .order_by(desc(KapDisclosure.published_at)).limit(limit)).all()
    return {"source": "kap", "items": [_disclosure_out(d, sym) for d, sym in rows]}


def _news_out(n: News, links: list[tuple[str, str]] | None = None) -> dict:
    return {"id": n.id, "title": n.title, "summary": n.summary, "publisher": n.publisher, "url": n.url,
            "published_at": n.published_at, "fetched_at": n.fetched_at,
            "stocks": [{"symbol": s, "match_type": m} for s, m in (links or [])]}


@router.get("/stocks/{symbol}/news")
def stock_news(symbol: str, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    st = _stock(db, symbol)
    rows = db.execute(select(News, NewsStock.match_type).join(NewsStock, NewsStock.news_id == News.id)
                      .where(NewsStock.stock_id == st.id, News.duplicate_of_id.is_(None))
                      .order_by(desc(News.published_at)).limit(limit)).all()
    return {"symbol": st.symbol, "source": "rss",
            "note": "Eşleştirme kural tabanlıdır: 'symbol' kod, 'name' şirket adı, 'query' hisse araması.",
            "items": [_news_out(n, [(st.symbol, m)]) for n, m in rows]}


@router.get("/news")
def latest_news(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.scalars(select(News).where(News.duplicate_of_id.is_(None))
                      .order_by(desc(News.published_at)).limit(limit)).all()
    links = defaultdict(list)
    if rows:
        for nid, sym, m in db.execute(select(NewsStock.news_id, Stock.symbol, NewsStock.match_type)
                                      .join(Stock).where(NewsStock.news_id.in_([n.id for n in rows]))):
            links[nid].append((sym, m))
    return {"source": "rss", "items": [_news_out(n, links[n.id]) for n in rows]}


# ---------------------------------------------------------------- makro

@router.get("/macro")
def macro(db: Session = Depends(get_db)):
    latest = (select(MacroObservation.series_code, func.max(MacroObservation.obs_date).label("d"))
              .group_by(MacroObservation.series_code).subquery())
    rows = db.execute(select(MacroObservation, DataSource.code).join(DataSource).join(latest, and_(
        latest.c.series_code == MacroObservation.series_code, latest.c.d == MacroObservation.obs_date))
        .order_by(MacroObservation.series_code)).all()
    notes = {s.code: s.note for s in SERIES}
    today = date.today()
    return {"items": [{
        "code": m.series_code, "name": m.series_name, "value": _f(m.value), "unit": m.unit,
        "date": m.obs_date.isoformat(), "frequency": m.frequency, "source": src, "fetched_at": m.fetched_at,
        "stale": (today - m.obs_date).days > STALE_AFTER.get(m.frequency, 30),
        "note": notes.get(m.series_code),
    } for m, src in rows]}


# ---------------------------------------------------------------- güncellemeler

@router.get("/updates")
def updates(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.execute(select(DataUpdateLog, DataSource.code).join(DataSource)
                      .order_by(desc(DataUpdateLog.started_at)).limit(limit)).all()
    return {"items": [{"source": src, "job": u.job, "status": u.status, "rows": u.rows_written,
                       "started_at": u.started_at, "finished_at": u.finished_at, "message": u.message}
                      for u, src in rows]}


@router.post("/stocks/{symbol}/refresh")
async def refresh(symbol: str, db: Session = Depends(get_db)):
    st = _stock(db, symbol)
    if st.instrument_type != "equity":
        raise HTTPException(400, "Endeksler tek başına yenilenemez; herhangi bir hisse yenilenince güncellenir.")
    results = await run_in_threadpool(service.refresh_stock, st.symbol)
    return {"symbol": st.symbol, "results": [r.__dict__ for r in results]}
