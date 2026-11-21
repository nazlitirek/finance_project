"""İş çalıştırıcı: her veri işini ayrı bir log kaydıyla çalıştırır.

Bir iş hata verirse:
- data_update_logs'a "failed" yazılır, kaynağın last_error alanı güncellenir,
- hata yukarı fırlatılmaz → diğer işler çalışmaya devam eder,
- daha önce kaydedilmiş veri silinmez.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import DataSource, DataUpdateLog

log = logging.getLogger(__name__)


@dataclass
class JobOutcome:
    rows: int = 0
    message: str | None = None
    partial: bool = False  # bazı kalemler başarısız oldu


@dataclass
class JobResult:
    job: str
    source: str
    status: str
    rows: int
    message: str | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_job(
    session_factory: sessionmaker[Session],
    source_code: str,
    job: str,
    fn: Callable[[Session], JobOutcome],
    stock_id: int | None = None,
) -> JobResult:
    with session_factory() as s:
        source = s.scalar(select(DataSource).where(DataSource.code == source_code))
        if source is None:
            return JobResult(job, source_code, "failed", 0, f"Bilinmeyen kaynak: {source_code}")
        if not source.enabled:
            return JobResult(job, source_code, "skipped", 0, f"{source.name} kapalı")
        entry = DataUpdateLog(source_id=source.id, job=job, stock_id=stock_id, status="running", rows_written=0)
        s.add(entry)
        s.commit()
        log_id, source_id = entry.id, source.id

    status, rows, message = "failed", 0, None
    with session_factory() as s:
        try:
            outcome = fn(s)
            s.commit()
            status = "partial" if outcome.partial else "success"
            rows, message = outcome.rows, outcome.message
        except Exception as exc:  # noqa: BLE001 — her hata kaydedilir, iş zinciri durmaz
            s.rollback()
            message = str(exc)[:2000]
            log.warning("%s/%s başarısız: %s", source_code, job, message)

    with session_factory() as s:
        entry = s.get(DataUpdateLog, log_id)
        entry.status, entry.rows_written, entry.message, entry.finished_at = status, rows, message, _now()
        src = s.get(DataSource, source_id)
        if status in ("success", "partial"):
            src.last_success_at = _now()
        if status in ("failed", "partial"):
            src.last_error_at, src.last_error = _now(), message
        s.commit()

    log.info("%s/%s: %s (%d satır)", source_code, job, status, rows)
    return JobResult(job, source_code, status, rows, message)
