"""Portföy hesapları (saf fonksiyonlar).

Yöntem: ağırlıklı ortalama maliyet.
- Alış: yeni ortalama = (eski adet × eski ort. + alış adedi × fiyat + komisyon) / yeni adet
- Satış: adet azalır, ortalama maliyet değişmez; gerçekleşen kâr/zarar = adet × (satış fiyatı − ort. maliyet) − komisyon
Güncel değer, son gün sonu kapanış fiyatıyla hesaplanır (gerçek zamanlı değildir).
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Tx:
    id: int
    symbol: str
    side: str  # buy / sell
    quantity: Decimal
    price: Decimal
    fee: Decimal
    traded_at: datetime


@dataclass
class Position:
    symbol: str
    quantity: Decimal = Decimal(0)
    avg_cost: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)  # adet × ortalama maliyet
    realized_pnl: Decimal = Decimal(0)
    transactions: int = 0
    errors: list[str] = field(default_factory=list)


class PortfolioError(ValueError):
    pass


def positions(txs: list[Tx]) -> dict[str, Position]:
    out: dict[str, Position] = {}
    for t in sorted(txs, key=lambda x: (x.traded_at, x.id)):
        p = out.setdefault(t.symbol, Position(t.symbol))
        p.transactions += 1
        if t.side == "buy":
            new_qty = p.quantity + t.quantity
            p.cost_basis = p.cost_basis + t.quantity * t.price + t.fee
            p.quantity = new_qty
            p.avg_cost = p.cost_basis / new_qty
        else:
            if t.quantity > p.quantity:
                raise PortfolioError(f"{t.symbol}: elde {p.quantity} lot varken {t.quantity} lot satış girilmiş.")
            p.realized_pnl += t.quantity * (t.price - p.avg_cost) - t.fee
            p.quantity -= t.quantity
            p.cost_basis = p.quantity * p.avg_cost
            if p.quantity == 0:
                p.avg_cost = Decimal(0)
                p.cost_basis = Decimal(0)
    return out


def valuation(pos: dict[str, Position], prices: dict[str, tuple[Decimal | None, str | None]]) -> dict:
    """prices: sembol → (son kapanış, tarih)."""
    rows, total_cost, total_value, missing = [], Decimal(0), Decimal(0), []
    realized = sum((p.realized_pnl for p in pos.values()), Decimal(0))
    for sym, p in sorted(pos.items()):
        if p.quantity == 0:
            rows.append({"symbol": sym, "quantity": 0, "avg_cost": None, "cost_basis": 0, "price": None,
                         "price_date": None, "market_value": 0, "unrealized_pnl": 0, "unrealized_pct": None,
                         "realized_pnl": float(p.realized_pnl), "closed": True})
            continue
        price, day = prices.get(sym, (None, None))
        value = p.quantity * price if price is not None else None
        pnl = value - p.cost_basis if value is not None else None
        total_cost += p.cost_basis
        if value is None:
            missing.append(sym)
        else:
            total_value += value
        rows.append({
            "symbol": sym, "quantity": float(p.quantity), "avg_cost": float(p.avg_cost),
            "cost_basis": float(p.cost_basis), "price": float(price) if price is not None else None,
            "price_date": day, "market_value": float(value) if value is not None else None,
            "unrealized_pnl": float(pnl) if pnl is not None else None,
            "unrealized_pct": float(pnl / p.cost_basis * 100) if pnl is not None and p.cost_basis else None,
            "realized_pnl": float(p.realized_pnl), "closed": False,
        })
    priced_cost = sum((Decimal(str(r["cost_basis"])) for r in rows if r["market_value"] and not r["closed"]),
                      Decimal(0))
    unreal = total_value - priced_cost
    return {
        "positions": rows,
        "total_cost": float(total_cost), "market_value": float(total_value),
        "unrealized_pnl": float(unreal), "unrealized_pct": float(unreal / priced_cost * 100) if priced_cost else None,
        "realized_pnl": float(realized),
        "missing_prices": missing,
        "note": "Güncel değer son gün sonu kapanış fiyatlarıyla hesaplanır; gerçek zamanlı değildir. "
                "Maliyet yöntemi: ağırlıklı ortalama, komisyon maliyete eklenir.",
    }
