from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ErrorOut(BaseModel):
    error: str  # makine için kısa kod
    message: str  # kullanıcı için Türkçe açıklama


class SourceStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    kind: str
    freshness: str
    is_official: bool
    enabled: bool
    last_success_at: datetime | None
    last_error_at: datetime | None


class HealthOut(BaseModel):
    status: str  # "ok" / "degraded"
    database: str  # "ok" / "unreachable"
    message: str | None = None
    sources: list[SourceStatusOut] = []
    ai_configured: bool
    evds_configured: bool


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    instrument_type: str
    sector: str | None = None
    is_active: bool


class StockListOut(BaseModel):
    total: int
    items: list[StockOut]
