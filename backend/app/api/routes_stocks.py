from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.schemas import StockListOut, StockOut
from app.core.text import normalize_search
from app.db.models import Stock
from app.db.session import get_db

router = APIRouter(prefix="/stocks", tags=["hisseler"])


def _to_out(s: Stock) -> StockOut:
    return StockOut(
        symbol=s.symbol,
        name=s.name,
        instrument_type=s.instrument_type,
        sector=s.sector.name if s.sector else None,
        is_active=s.is_active,
    )


@router.get("", response_model=StockListOut)
def list_stocks(
    instrument_type: str | None = Query(None, pattern="^(equity|index)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = select(Stock).where(Stock.is_active.is_(True))
    if instrument_type:
        q = q.where(Stock.instrument_type == instrument_type)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.options(joinedload(Stock.sector)).order_by(Stock.symbol).limit(limit).offset(offset)).all()
    return StockListOut(total=total, items=[_to_out(s) for s in rows])


@router.get("/search", response_model=list[StockOut])
def search_stocks(
    q: str = Query(..., min_length=1, max_length=60, description="Hisse kodu veya şirket adı"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    term = normalize_search(q)
    if not term:
        return []
    symbol_term = q.strip().upper()
    like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

    # Sıralama: tam kod eşleşmesi > kod başlangıcı > isimde geçen
    rank = case(
        (Stock.symbol == symbol_term, 0),
        (Stock.symbol.startswith(symbol_term, autoescape=True), 1),
        else_=2,
    )
    stmt = (
        select(Stock)
        .options(joinedload(Stock.sector))
        .where(
            Stock.is_active.is_(True),
            or_(Stock.symbol.startswith(symbol_term, autoescape=True), Stock.search_name.like(like, escape="\\")),
        )
        .order_by(rank, Stock.symbol)
        .limit(limit)
    )
    return [_to_out(s) for s in db.scalars(stmt).all()]


@router.get("/{symbol}", response_model=StockOut)
def get_stock(symbol: str, db: Session = Depends(get_db)):
    s = db.scalar(select(Stock).options(joinedload(Stock.sector)).where(Stock.symbol == symbol.upper()))
    if s is None:
        raise HTTPException(status_code=404, detail=f"'{symbol.upper()}' kodlu hisse bulunamadı.")
    return _to_out(s)
