"""Grafik, karşılaştırma ve ana sayfa özeti."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.analysis import service as analysis
from app.analysis import technical
from app.analysis.common import num
from app.api.routes_data import RANGES, latest_disclosures, latest_news, movers
from app.db.models import DataSource, DataUpdateLog, Stock, StockPrice, Watchlist
from app.db.session import get_db

router = APIRouter(tags=["piyasa"])

OVERLAYS = {
    "sma_20": lambda c: technical.sma(c, 20), "sma_50": lambda c: technical.sma(c, 50),
    "sma_100": lambda c: technical.sma(c, 100), "sma_200": lambda c: technical.sma(c, 200),
    "ema_9": lambda c: technical.ema(c, 9), "ema_21": lambda c: technical.ema(c, 21),
    "ema_50": lambda c: technical.ema(c, 50), "ema_200": lambda c: technical.ema(c, 200),
}
UNAVAILABLE_INDICES = {"XU030": "BIST 30", "XBANK": "BIST Banka"}


def _series(dates, values) -> list[dict]:
    return [{"date": d, "value": round(v, 4)} for d, v in zip(dates, values) if num(v) is not None]


@router.get("/stocks/{symbol}/chart")
def chart(symbol: str, range: str = Query("1y", pattern="^(1d|1w|1m|3m|6m|1y|3y)$"),  # noqa: A002
          overlays: str = Query("", description="Virgülle: sma_20,sma_50,ema_21,bb"),
          db: Session = Depends(get_db)):
    st = db.scalar(select(Stock).where(Stock.symbol == symbol.upper()))
    if st is None:
        raise HTTPException(404, f"'{symbol.upper()}' kodlu hisse bulunamadı.")
    if range == "1d":
        return {"symbol": st.symbol, "range": range, "bars": [], "overlays": {},
                "message": "Gün içi (1 günlük) grafik için veri yok: kaynak sadece gün sonu fiyatı veriyor."}
    df = analysis.prices_df(db, st.id, adjusted=st.instrument_type == "equity")
    if df.empty:
        return {"symbol": st.symbol, "range": range, "bars": [], "overlays": {}, "message": "Fiyat verisi yok."}
    close = df["close"]
    start = df.index[-1] - timedelta(days=RANGES[range])
    mask = df.index >= start
    dates = [d.date().isoformat() for d in df.index[mask]]
    out_overlays = {}
    for name in [x.strip() for x in overlays.split(",") if x.strip()]:
        if name in OVERLAYS:
            out_overlays[name] = _series(dates, OVERLAYS[name](close)[mask].tolist())
        elif name == "bb":
            bb = technical.bollinger(close)
            for k in ("upper", "mid", "lower"):
                out_overlays[f"bb_{k}"] = _series(dates, bb[k][mask].tolist())
        else:
            raise HTTPException(422, f"Bilinmeyen gösterge: {name}")
    sub = df[mask]
    return {
        "symbol": st.symbol, "range": range, "adjusted": st.instrument_type == "equity",
        "chart_type": "line_hlc",
        "note": "Gün sonu verisi. Kaynak açılış fiyatı vermediği için mum grafik yerine kapanış çizgisi ve "
                "gün içi en yüksek/en düşük aralığı gösterilir. Göstergeler tüm geçmişten hesaplanır.",
        "bars": [{"date": d, "close": num(r.close), "high": num(r.high), "low": num(r.low),
                  "turnover": num(r.turnover)} for d, r in zip(dates, sub.itertuples())],
        "overlays": out_overlays,
    }


@router.get("/compare")
def compare(symbols: str = Query(..., description="Virgülle 2-5 hisse kodu"), db: Session = Depends(get_db)):
    syms = list(dict.fromkeys(s.strip().upper() for s in symbols.split(",") if s.strip()))
    if not 2 <= len(syms) <= 5:
        raise HTTPException(422, "Karşılaştırma için 2 ile 5 arasında hisse seçin.")
    out = []
    for sym in syms:
        st = db.scalar(select(Stock).options(joinedload(Stock.sector)).where(Stock.symbol == sym))
        if st is None or st.instrument_type != "equity":
            raise HTTPException(404, f"'{sym}' kodlu hisse bulunamadı.")
        r = analysis.analyze_stock(db, st)
        m = r["modules"]

        def metric(mod, code):
            return next((x["value"] for x in m[mod]["metrics"] if x["code"] == code), None)

        out.append({
            "symbol": st.symbol, "name": st.name, "sector": r["sector"], "price": r["price"],
            "price_date": r["price_date"], "financial_period": r["financial_period"],
            "overall": {"score": r["overall"]["score"], "label": r["overall"]["label"]},
            "scores": {k: v["score"] for k, v in m.items()},
            "technical": {"trend": m["technical"]["assessments"].get("trend_direction"),
                          "rsi_14": metric("technical", "rsi_14"),
                          "momentum": m["technical"]["assessments"].get("momentum_strength")},
            "valuation": {c: metric("valuation", c) for c in ("pe", "pb", "ev_ebitda", "ev_sales")},
            "ratios": {c: metric("financial_health", c) for c in
                       ("roe", "net_margin", "ebitda_margin", "current_ratio", "net_debt_to_ebitda",
                        "liabilities_to_equity")},
            "risk": {c: metric("risk", c) for c in ("beta", "historical_volatility", "max_drawdown", "sharpe")},
        })
    db.commit()
    periods = {x["financial_period"] for x in out if x["financial_period"]}
    return {"items": out,
            "note": None if len(periods) <= 1 else
            "Seçilen hisselerin son finansal dönemleri farklı: " + ", ".join(sorted(periods)) +
            ". Finansal oranlar doğrudan karşılaştırılırken dikkatli olun."}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    xu = db.scalar(select(Stock).where(Stock.symbol == "XU100"))
    indices = []
    if xu:
        rows = db.execute(select(StockPrice.close, StockPrice.ts).where(StockPrice.stock_id == xu.id)
                          .order_by(desc(StockPrice.ts)).limit(2)).all()
        if rows:
            prev = rows[1][0] if len(rows) > 1 else None
            indices.append({"symbol": "XU100", "name": "BIST 100", "value": num(rows[0][0]),
                            "as_of": rows[0][1].date().isoformat(),
                            "change_pct": num((rows[0][0] - prev) / prev * 100) if prev else None})
    for sym, name in UNAVAILABLE_INDICES.items():
        indices.append({"symbol": sym, "name": name, "value": None,
                        "message": "Ücretsiz kaynakta bu endeksin verisi yok."})
    fav = db.execute(select(Stock.symbol, Stock.name).join(Watchlist, Watchlist.stock_id == Stock.id)
                     .order_by(Stock.symbol)).all()
    sources = db.execute(select(DataSource.code, DataSource.name, DataSource.enabled, DataSource.freshness,
                                DataSource.last_success_at, DataSource.last_error_at)
                         .order_by(DataSource.code)).all()
    last_job = db.scalar(select(func.max(DataUpdateLog.finished_at)))
    return {
        "indices": indices,
        "movers": movers(limit=8, db=db),
        "disclosures": latest_disclosures(limit=10, db=db)["items"],
        "news": latest_news(limit=10, db=db)["items"],
        "favorites": [{"symbol": s, "name": n} for s, n in fav],
        "sources": [dict(r._mapping) for r in sources],
        "last_update": last_job,
        "note": "Bütün fiyatlar gün sonu verisidir (İş Yatırım); gerçek zamanlı değildir.",
    }
