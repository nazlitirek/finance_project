"""Fiyat alarmı kontrolü. Son gün sonu kapanış fiyatıyla karşılaştırılır (gerçek zamanlı değildir).

Bir alarm tetiklenince pasif olur (tekrar tetiklenmez); kullanıcı isterse yeniden etkinleştirir.
Bildirim: frontend /api/alerts/triggered uç noktasını düzenli sorgular ve tarayıcı bildirimi gösterir.
Bunun için backend ve tarayıcı sekmesinin açık olması gerekir.
"""

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import PriceAlert, StockPrice
from app.ingest.runner import JobOutcome


def select_last_two(stock_id: int):
    """Son iki gün sonu kapanış (düzeltilmemiş): (close, ts)."""
    return (select(StockPrice.close, StockPrice.ts).where(
        StockPrice.stock_id == stock_id, StockPrice.interval == "1d", StockPrice.is_adjusted.is_(False))
        .order_by(desc(StockPrice.ts)).limit(2))


def last_close(db: Session, stock_id: int):
    return db.execute(select_last_two(stock_id).limit(1)).first()


def is_hit(condition: str, target, price) -> bool:
    return price >= target if condition == "above" else price <= target


def check(db: Session) -> JobOutcome:
    fired = 0
    for a in db.scalars(select(PriceAlert).where(PriceAlert.is_active.is_(True))):
        row = last_close(db, a.stock_id)
        if row is None or row[0] is None:
            continue
        price, _ = row
        if is_hit(a.condition, a.target_price, price):
            a.is_active = False
            a.triggered_at = datetime.now(timezone.utc)
            a.triggered_price = price
            fired += 1
    return JobOutcome(rows=fired, message=f"{fired} alarm tetiklendi")
