"""Kişisel özellikler: favoriler, portföy, fiyat alarmları (tek kullanıcı)."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.analysis import portfolio as pf
from app.db.models import Portfolio, PortfolioTransaction, PriceAlert, Stock, Watchlist
from app.db.session import get_db
from app.ingest import alerts as alert_logic

router = APIRouter(tags=["kişisel"])
DEFAULT_PORTFOLIO = "Ana Portföy"


def _equity(db: Session, symbol: str) -> Stock:
    st = db.scalar(select(Stock).where(Stock.symbol == symbol.upper().strip()))
    if st is None:
        raise HTTPException(404, f"'{symbol.upper()}' kodlu hisse bulunamadı.")
    if st.instrument_type != "equity":
        raise HTTPException(400, "Sadece hisseler eklenebilir.")
    return st


def _quote(db: Session, stock_id: int) -> dict:
    rows = db.execute(alert_logic.select_last_two(stock_id)).all()
    if not rows:
        return {"price": None, "as_of": None, "change_pct": None}
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    chg = float((cur[0] - prev[0]) / prev[0] * 100) if prev and prev[0] else None
    return {"price": float(cur[0]), "as_of": cur[1].date().isoformat(), "change_pct": chg}


# ---------------------------------------------------------------- favoriler

class WatchIn(BaseModel):
    symbol: str
    note: str | None = Field(None, max_length=500)


@router.get("/watchlist")
def watchlist(db: Session = Depends(get_db)):
    rows = db.execute(select(Watchlist, Stock).join(Stock).order_by(Stock.symbol)).all()
    return {"items": [{"symbol": s.symbol, "name": s.name, "note": w.note, "added_at": w.added_at,
                       **_quote(db, s.id)} for w, s in rows],
            "note": "Fiyatlar gün sonu kapanışıdır."}


@router.post("/watchlist", status_code=201)
def add_watch(body: WatchIn, db: Session = Depends(get_db)):
    st = _equity(db, body.symbol)
    if db.scalar(select(Watchlist).where(Watchlist.stock_id == st.id)):
        raise HTTPException(409, f"{st.symbol} zaten favorilerde.")
    db.add(Watchlist(stock_id=st.id, note=body.note))
    db.commit()
    return {"symbol": st.symbol}


@router.delete("/watchlist/{symbol}", status_code=204)
def remove_watch(symbol: str, db: Session = Depends(get_db)):
    st = _equity(db, symbol)
    w = db.scalar(select(Watchlist).where(Watchlist.stock_id == st.id))
    if w is None:
        raise HTTPException(404, f"{st.symbol} favorilerde değil.")
    db.delete(w)
    db.commit()


# ---------------------------------------------------------------- portföy

class TxIn(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=4)
    price: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    fee: Decimal = Field(Decimal(0), ge=0, max_digits=20, decimal_places=6)
    traded_at: datetime
    note: str | None = Field(None, max_length=500)

    @field_validator("traded_at")
    @classmethod
    def _not_future(cls, v: datetime) -> datetime:
        v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if v > datetime.now(timezone.utc):
            raise ValueError("İşlem tarihi gelecekte olamaz.")
        return v


def _portfolio(db: Session) -> Portfolio:
    p = db.scalar(select(Portfolio).where(Portfolio.name == DEFAULT_PORTFOLIO))
    if p is None:
        p = Portfolio(name=DEFAULT_PORTFOLIO)
        db.add(p)
        db.flush()
    return p


def _txs(db: Session, portfolio_id: int) -> list[pf.Tx]:
    rows = db.execute(select(PortfolioTransaction, Stock.symbol).join(Stock)
                      .where(PortfolioTransaction.portfolio_id == portfolio_id)).all()
    return [pf.Tx(t.id, sym, t.side, t.quantity, t.price, t.fee, t.traded_at) for t, sym in rows]


@router.get("/portfolio")
def get_portfolio(db: Session = Depends(get_db)):
    p = _portfolio(db)
    db.commit()
    pos = pf.positions(_txs(db, p.id))
    prices = {}
    for sym in pos:
        st = db.scalar(select(Stock.id).where(Stock.symbol == sym))
        q = _quote(db, st)
        prices[sym] = (Decimal(str(q["price"])) if q["price"] is not None else None, q["as_of"])
    return {"name": p.name, **pf.valuation(pos, prices)}


@router.get("/portfolio/transactions")
def list_tx(db: Session = Depends(get_db)):
    p = _portfolio(db)
    db.commit()
    rows = db.execute(select(PortfolioTransaction, Stock.symbol).join(Stock)
                      .where(PortfolioTransaction.portfolio_id == p.id)
                      .order_by(desc(PortfolioTransaction.traded_at), desc(PortfolioTransaction.id))).all()
    return {"items": [{"id": t.id, "symbol": sym, "side": t.side, "quantity": float(t.quantity),
                       "price": float(t.price), "fee": float(t.fee), "traded_at": t.traded_at, "note": t.note}
                      for t, sym in rows]}


@router.post("/portfolio/transactions", status_code=201)
def add_tx(body: TxIn, db: Session = Depends(get_db)):
    st = _equity(db, body.symbol)
    p = _portfolio(db)
    t = PortfolioTransaction(portfolio_id=p.id, stock_id=st.id, side=body.side, quantity=body.quantity,
                             price=body.price, fee=body.fee, traded_at=body.traded_at, note=body.note)
    db.add(t)
    db.flush()
    try:
        pf.positions(_txs(db, p.id))  # satış eldeki adedi aşıyor mu?
    except pf.PortfolioError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return {"id": t.id}


@router.delete("/portfolio/transactions/{tx_id}", status_code=204)
def delete_tx(tx_id: int, db: Session = Depends(get_db)):
    p = _portfolio(db)
    t = db.get(PortfolioTransaction, tx_id)
    if t is None or t.portfolio_id != p.id:
        raise HTTPException(404, "İşlem bulunamadı.")
    db.delete(t)
    db.flush()
    try:
        pf.positions(_txs(db, p.id))  # silinen alış sonrası satışlar açıkta kalıyor mu?
    except pf.PortfolioError as exc:
        db.rollback()
        raise HTTPException(400, f"Bu işlem silinemez: {exc}") from exc
    db.commit()


# ---------------------------------------------------------------- alarmlar

class AlertIn(BaseModel):
    symbol: str
    condition: str = Field(pattern="^(above|below)$")
    target_price: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    note: str | None = Field(None, max_length=500)


def _alert_out(a: PriceAlert, sym: str, name: str, q: dict | None = None) -> dict:
    return {"id": a.id, "symbol": sym, "name": name, "condition": a.condition,
            "target_price": float(a.target_price), "is_active": a.is_active, "created_at": a.created_at,
            "triggered_at": a.triggered_at,
            "triggered_price": float(a.triggered_price) if a.triggered_price is not None else None,
            "note": a.note, **({"current": q} if q is not None else {})}


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db)):
    rows = db.execute(select(PriceAlert, Stock.symbol, Stock.name).join(Stock)
                      .order_by(desc(PriceAlert.is_active), desc(PriceAlert.created_at))).all()
    return {"items": [_alert_out(a, s, n, _quote(db, a.stock_id)) for a, s, n in rows],
            "note": "Alarmlar gün sonu kapanış fiyatıyla kontrol edilir (hafta içi 19:00, veri güncellemesinden sonra). "
                    "Bildirim için backend ve tarayıcı sekmesinin açık olması gerekir."}


@router.post("/alerts", status_code=201)
def add_alert(body: AlertIn, db: Session = Depends(get_db)):
    st = _equity(db, body.symbol)
    a = PriceAlert(stock_id=st.id, condition=body.condition, target_price=body.target_price, note=body.note)
    db.add(a)
    db.commit()
    q = _quote(db, st.id)
    already = q["price"] is not None and alert_logic.is_hit(body.condition, body.target_price,
                                                           Decimal(str(q["price"])))
    return {"id": a.id, "already_met": already,
            "message": "Koşul son kapanış fiyatında zaten sağlanıyor; bir sonraki kontrolde tetiklenecek."
            if already else None}


@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(PriceAlert, alert_id)
    if a is None:
        raise HTTPException(404, "Alarm bulunamadı.")
    db.delete(a)
    db.commit()


@router.post("/alerts/{alert_id}/reactivate")
def reactivate(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(PriceAlert, alert_id)
    if a is None:
        raise HTTPException(404, "Alarm bulunamadı.")
    a.is_active, a.triggered_at, a.triggered_price = True, None, None
    db.commit()
    return {"id": a.id, "is_active": True}


@router.post("/alerts/check")
def check_now(db: Session = Depends(get_db)):
    out = alert_logic.check(db)
    db.commit()
    return {"triggered": out.rows}


@router.get("/alerts/triggered")
def triggered(since: datetime = Query(...), db: Session = Depends(get_db)):
    """Frontend bu uç noktayı düzenli sorgular; dönen alarmlar için tarayıcı bildirimi gösterir."""
    since = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    rows = db.execute(select(PriceAlert, Stock.symbol, Stock.name).join(Stock)
                      .where(PriceAlert.triggered_at.is_not(None), PriceAlert.triggered_at > since)
                      .order_by(PriceAlert.triggered_at)).all()
    return {"items": [_alert_out(a, s, n) for a, s, n in rows], "server_time": datetime.now(timezone.utc)}
