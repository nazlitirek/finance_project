"""Test ayarları.

Veritabanı testleri ayrı bir test veritabanında (TEST_DATABASE_URL) çalışır.
Her test oturumunda tablolar sıfırdan migration ile kurulur; ana veritabanına dokunulmaz.
"""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BACKEND_DIR, get_settings
from app.db.session import get_db, make_engine


def _test_url() -> str | None:
    s = get_settings().test_database_url
    return s.get_secret_value() if s else None


@pytest.fixture(scope="session")
def db_engine():
    url = _test_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL tanımlı değil")
    if url == get_settings().database_url.get_secret_value():
        pytest.exit("TEST_DATABASE_URL ana veritabanıyla aynı olamaz", returncode=2)
    engine = make_engine(url)
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Test veritabanına bağlanılamadı: {exc.__class__.__name__}")

    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.cmd_opts = None
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine) -> Session:
    """Her test kendi transaction'ında çalışır ve sonunda geri alınır."""
    conn = db_engine.connect()
    trans = conn.begin()
    session = sessionmaker(bind=conn, join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    trans.rollback()
    conn.close()


@pytest.fixture
def client(db) -> TestClient:
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()
