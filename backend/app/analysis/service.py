"""Analiz servis katmanı: veritabanından veriyi okur, saf analiz fonksiyonlarını çalıştırır.

Hesaplamalar burada yapılmaz; sadece veri hazırlanır ve sonuçlar birleştirilir.
"""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.analysis import fundamental, risk, sector, technical, valuation
from app.analysis.common import div, num
from app.analysis.scoring import overall
from app.analysis.statements import Financials, build, pkey
from app.db.models import FinancialRatio, FinancialStatement, MacroObservation, Stock, StockPrice

RISK_FREE_SERIES = "TP.APIFON4"
RISK_FREE_LABEL = "TCMB ağırlıklı ortalama fonlama maliyeti (EVDS TP.APIFON4)"


# ---------------------------------------------------------------- veri yükleme

def prices_df(db: Session, stock_id: int, adjusted: bool = True) -> pd.DataFrame:
    rows = db.execute(select(StockPrice.ts, StockPrice.close, StockPrice.high, StockPrice.low, StockPrice.turnover)
                      .where(StockPrice.stock_id == stock_id, StockPrice.interval == "1d",
                             StockPrice.is_adjusted.is_(adjusted)).order_by(StockPrice.ts)).all()
    df = pd.DataFrame(rows, columns=["ts", "close", "high", "low", "turnover"])
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert("Europe/Istanbul").dt.normalize()
    df = df.set_index("ts")
    return df.astype(float)


def index_close(db: Session) -> pd.Series | None:
    idx = db.scalar(select(Stock.id).where(Stock.symbol == "XU100"))
    if idx is None:
        return None
    df = prices_df(db, idx, adjusted=False)
    return None if df.empty else df["close"]


def financials(db: Session, stock: Stock) -> Financials | None:
    rows = db.execute(select(FinancialStatement.fiscal_year, FinancialStatement.fiscal_period,
                             FinancialStatement.item_code, FinancialStatement.value,
                             FinancialStatement.inflation_adjusted)
                      .where(FinancialStatement.stock_id == stock.id)).all()
    return build([(y, p, c, num(v), i) for y, p, c, v, i in rows], profile(stock))


def profile(stock: Stock) -> str:
    return stock.sector.analysis_profile if stock.sector else "general"


def last_price(db: Session, stock_id: int) -> tuple[float | None, str | None]:
    row = db.execute(select(StockPrice.close, StockPrice.ts).where(
        StockPrice.stock_id == stock_id, StockPrice.interval == "1d", StockPrice.is_adjusted.is_(False))
        .order_by(desc(StockPrice.ts)).limit(1)).first()
    return (num(row[0]), row[1].date().isoformat()) if row else (None, None)


def risk_free(db: Session, start: date | None = None, end: date | None = None) -> float | None:
    """Yıllık oran (0.36 = %36). Aralık verilirse ortalaması, yoksa son değer."""
    q = select(MacroObservation.value).where(MacroObservation.series_code == RISK_FREE_SERIES)
    if start and end:
        v = db.scalar(select(func.avg(MacroObservation.value)).where(
            MacroObservation.series_code == RISK_FREE_SERIES, MacroObservation.obs_date.between(start, end)))
    else:
        v = db.scalar(q.order_by(desc(MacroObservation.obs_date)).limit(1))
    return num(v) / 100 if v is not None else None


# ---------------------------------------------------------------- yardımcılar

def _own_history(f: Financials, adj_prices: pd.DataFrame, shares: float | None, prof: str) -> dict[str, list[float]]:
    """Şirketin geçmiş çeyrek sonlarındaki çarpanları. Geçmiş piyasa değeri ≈ düzeltilmiş fiyat × bugünkü pay adedi
    (düzeltilmiş fiyat bölünme/bedelsizleri geriye doğru yansıttığı için)."""
    out: dict[str, list[float]] = {"pe": [], "pb": [], "ev_ebitda": []}
    if adj_prices.empty or not shares:
        return out
    closes = adj_prices["close"]
    for p in f.periods[1:]:
        end = pd.Timestamp(date(p[0], p[1], 28), tz="Europe/Istanbul") + pd.offsets.MonthEnd(0)
        px = closes[closes.index <= end]
        if px.empty or (end - px.index[-1]).days > 10:
            continue
        m = valuation.multiples(f, p, float(px.iloc[-1]) * shares, prof)
        for k in out:
            if m.get(k) is not None:
                out[k].append(m[k])
    return out


def snapshot(db: Session, stock: Stock) -> dict | None:
    """Sektör karşılaştırması için şirketin son dönem göstergeleri."""
    f = financials(db, stock)
    if f is None or f.latest is None:
        return None
    p = f.latest
    price, _ = last_price(db, stock.id)
    mcap = None if price is None or stock.paid_in_capital is None else price * float(stock.paid_in_capital)
    prof = profile(stock)
    m = valuation.multiples(f, p, mcap, prof)
    ms = {x.code: x.value for x in fundamental.ratios(f, p, prof)}
    rev_key = "revenue" if f.template == "industrial" else "net_interest_income"
    return {
        "symbol": stock.symbol, "name": stock.name, "period": pkey(p),
        "pe": m.get("pe"), "pb": m.get("pb"), "ev_ebitda": m.get("ev_ebitda"),
        "roe": ms.get("roe"), "net_margin": ms.get("net_margin"),
        "liabilities_to_equity": ms.get("liabilities_to_equity"), "ebitda_margin": ms.get("ebitda_margin"),
        "revenue_growth": fundamental.growth(f.ttm(rev_key, p), f.ttm(rev_key, f.year_ago(p))),
        "ocf_margin": div(f.ttm("operating_cash_flow", p), f.ttm("revenue", p)) if f.template == "industrial" else None,
    }


def peers(db: Session, stock: Stock) -> list[Stock]:
    if stock.sector_id is None:
        return []
    return list(db.scalars(select(Stock).where(
        Stock.sector_id == stock.sector_id, Stock.instrument_type == "equity", Stock.is_active.is_(True),
        Stock.id != stock.id).order_by(Stock.symbol)))


def save_ratios(db: Session, stock: Stock, f: Financials, health: dict) -> None:
    p = f.latest
    rows = []
    for m in health.get("metrics", []):
        if m.get("formula") is None:
            continue
        rows.append(dict(stock_id=stock.id, fiscal_year=p[0], fiscal_period=p[1], consolidation="unknown",
                         inflation_adjusted=f.inflation.get(p), ratio_code=m["code"],
                         value=Decimal(str(m["value"])) if m["value"] is not None else None,
                         formula=m["formula"], inputs={"period": pkey(p)}, note=m.get("comment")))
    if not rows:
        return
    stmt = pg_insert(FinancialRatio).values(rows)
    stmt = stmt.on_conflict_do_update(constraint="uq_financial_ratios", set_={
        "value": stmt.excluded.value, "formula": stmt.excluded.formula, "note": stmt.excluded.note,
        "computed_at": func.now()})
    db.execute(stmt)


# ---------------------------------------------------------------- ana giriş

def analyze_stock(db: Session, stock: Stock) -> dict:
    prof = profile(stock)
    adj = prices_df(db, stock.id, adjusted=True)
    f = financials(db, stock)
    price, price_date = last_price(db, stock.id)

    tech = technical.analyze(adj) if not adj.empty else technical.ModuleResult(
        "technical", None, 0.0, None, notes=["Fiyat verisi yok."])
    fund = fundamental.analyze_fundamental(f, prof)
    health = fundamental.analyze_health(f, prof)

    end = adj.index[-1].date() if not adj.empty else date.today()
    rf_window = risk_free(db, end - timedelta(days=365), end)
    rsk = risk.analyze(adj, index_close(db), f, rf_window, RISK_FREE_LABEL + ", 1 yıllık ortalama",
                       health.metrics)

    peer_snaps = [s for s in (snapshot(db, p) for p in peers(db, stock)) if s]
    target = snapshot(db, stock) or {"symbol": stock.symbol, "name": stock.name}
    sec = sector.analyze(target, peer_snaps, pkey(f.latest) if f and f.latest else None,
                         stock.sector.name if stock.sector else None)

    market = valuation.Market(price=price, price_date=price_date,
                              shares=float(stock.paid_in_capital) if stock.paid_in_capital else None,
                              risk_free=risk_free(db), risk_free_source=RISK_FREE_LABEL + ", son değer",
                              beta=next((x.value for x in rsk.metrics if x.code == "beta"), None))
    same_period = [s for s in peer_snaps if f and f.latest and s["period"] == pkey(f.latest)]
    val = valuation.analyze(f, market, prof, same_period,
                            _own_history(f, adj, market.shares, prof) if f else None)

    news = technical.ModuleResult("news", None, 0.0, None, notes=["Haber ve KAP puanı AI analiziyle (Aşama 5) gelecek."],
                                  meaning="0-100: haberlerin şirket açısından niteliği ve önemi.")
    results = {"technical": tech, "fundamental": fund, "financial_health": health, "valuation": val,
               "sector": sec, "news": news, "risk": rsk}
    out = {k: v.to_dict() for k, v in results.items()}
    if f is not None and f.latest is not None:
        save_ratios(db, stock, f, out["financial_health"])
    return {
        "symbol": stock.symbol, "name": stock.name, "sector": stock.sector.name if stock.sector else None,
        "profile": prof, "price": price, "price_date": price_date,
        "financial_period": pkey(f.latest) if f and f.latest else None,
        "modules": out, "overall": overall(results),
    }
