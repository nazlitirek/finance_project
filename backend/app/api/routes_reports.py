from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.ai import client, news, report
from app.reports import pdf
from app.db.models import AnalysisReport, Stock
from app.db.session import get_db

router = APIRouter(tags=["ai-rapor"])


def _stock(db: Session, symbol: str) -> Stock:
    st = db.scalar(select(Stock).options(joinedload(Stock.sector)).where(Stock.symbol == symbol.upper()))
    if st is None:
        raise HTTPException(404, f"'{symbol.upper()}' kodlu hisse bulunamadı.")
    if st.instrument_type != "equity":
        raise HTTPException(400, "Rapor sadece hisseler için oluşturulur.")
    return st


@router.post("/stocks/{symbol}/report")
def create_report(symbol: str, db: Session = Depends(get_db)):
    """Yeni AI raporu (yaklaşık 1-2 dakika). AI API hatasında puanlar yine kaydedilir, rapor 'failed' olur."""
    st = _stock(db, symbol)
    if not client.is_configured():
        raise HTTPException(503, f"AI raporu için {client.key_name()} gerekli (backend/.env).")
    rep = report.generate(db, st)
    db.refresh(rep, ["scores"])
    return report.to_dict(rep, st.symbol)


@router.post("/stocks/{symbol}/news/analyze")
def analyze_news(symbol: str, db: Session = Depends(get_db)):
    st = _stock(db, symbol)
    try:
        out = news.analyze_pending(db, st)
    except client.AIError as exc:
        db.rollback()
        raise HTTPException(503, exc.message) from exc
    db.commit()
    return out


@router.get("/stocks/{symbol}/reports")
def list_reports(symbol: str, db: Session = Depends(get_db)):
    st = _stock(db, symbol)
    rows = db.scalars(select(AnalysisReport).where(AnalysisReport.stock_id == st.id)
                      .order_by(desc(AnalysisReport.created_at)).limit(100)).all()
    return {"symbol": st.symbol, "items": [{
        "id": r.id, "created_at": r.created_at, "status": r.status, "model": r.model,
        "overall_score": float(r.overall_score) if r.overall_score is not None else None,
        "overall_label": r.overall_label, "error": r.error} for r in rows]}


def _load(db: Session, report_id: int) -> dict:
    rep = db.scalar(select(AnalysisReport).options(selectinload(AnalysisReport.scores))
                    .where(AnalysisReport.id == report_id))
    if rep is None:
        raise HTTPException(404, "Rapor bulunamadı.")
    sym = db.scalar(select(Stock.symbol).where(Stock.id == rep.stock_id))
    return report.to_dict(rep, sym)


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    return _load(db, report_id)


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: int, db: Session = Depends(get_db)):
    """Saklanan raporun PDF'i (yeniden hesaplama yok)."""
    data = jsonable_encoder(_load(db, report_id))
    try:
        content = pdf.build(data)
    except pdf.PdfError as exc:
        code = 409 if "tamamlanmış" in str(exc) else 500
        raise HTTPException(code, str(exc)) from exc
    name = pdf.filename(data)
    ascii_name = name.encode("ascii", "ignore").decode() or "rapor.pdf"
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"})
