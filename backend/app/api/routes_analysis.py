from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.analysis import service as analysis
from app.db.models import Stock
from app.db.session import get_db
from app.ingest import service as ingest

router = APIRouter(tags=["analiz"])

MODULES = ("technical", "fundamental", "financial_health", "valuation", "sector", "risk", "news")


def _stock(db: Session, symbol: str) -> Stock:
    st = db.scalar(select(Stock).options(joinedload(Stock.sector)).where(Stock.symbol == symbol.upper()))
    if st is None:
        raise HTTPException(404, f"'{symbol.upper()}' kodlu hisse bulunamadı.")
    if st.instrument_type != "equity":
        raise HTTPException(400, "Analiz sadece hisseler için yapılır.")
    return st


@router.get("/stocks/{symbol}/analysis")
def full_analysis(symbol: str, db: Session = Depends(get_db)):
    result = analysis.analyze_stock(db, _stock(db, symbol))
    db.commit()  # hesaplanan oranlar financial_ratios tablosuna kaydedilir
    return result


@router.get("/stocks/{symbol}/analysis/{module}")
def module_analysis(symbol: str, module: str, db: Session = Depends(get_db)):
    if module not in MODULES:
        raise HTTPException(404, f"Bilinmeyen modül. Seçenekler: {', '.join(MODULES)}")
    result = analysis.analyze_stock(db, _stock(db, symbol))
    db.commit()
    return {"symbol": result["symbol"], "module": module, **result["modules"][module]}


@router.post("/stocks/{symbol}/peers/refresh")
async def refresh_peers(symbol: str, db: Session = Depends(get_db)):
    """Sektördeki rakiplerin fiyat ve finansal tablolarını çeker (sektör karşılaştırması için).
    Rakip sayısına göre birkaç dakika sürebilir."""
    st = _stock(db, symbol)
    symbols = [p.symbol for p in analysis.peers(db, st)] + [st.symbol]
    results = [await run_in_threadpool(ingest.update_prices, symbols),
               await run_in_threadpool(ingest.update_financials, symbols)]
    return {"symbol": st.symbol, "peers": symbols, "results": [r.__dict__ for r in results]}
