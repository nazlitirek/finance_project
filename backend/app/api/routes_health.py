import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.schemas import HealthOut, SourceStatusOut
from app.core.config import get_settings
from app.db.models import DataSource
from app.db.session import get_db

log = logging.getLogger(__name__)
router = APIRouter(tags=["sistem"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    settings = get_settings()
    base = {
        "ai_configured": settings.anthropic_api_key is not None,
        "evds_configured": settings.evds_api_key is not None,
    }
    try:
        db.execute(text("SELECT 1"))
        sources = db.scalars(select(DataSource).order_by(DataSource.code)).all()
    except SQLAlchemyError as exc:
        log.error("Veritabanı sağlık kontrolü başarısız: %s", exc.__class__.__name__)
        body = HealthOut(
            status="degraded",
            database="unreachable",
            message="Veritabanına bağlanılamadı. PostgreSQL servisinin çalıştığını kontrol edin.",
            **base,
        )
        return JSONResponse(status_code=503, content=body.model_dump(mode="json"))

    return HealthOut(
        status="ok",
        database="ok",
        sources=[SourceStatusOut.model_validate(s) for s in sources],
        **base,
    )
