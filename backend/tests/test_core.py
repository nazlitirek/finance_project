import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import RedactSecretsFilter
from app.core.text import normalize_search


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TÜRK HAVA YOLLARI", "turk hava yollari"),
        ("türk hava yolları", "turk hava yollari"),
        ("  İŞ   Bankası ", "is bankasi"),
        ("ŞİŞECAM", "sisecam"),
        ("Çelebi Ğ Ö", "celebi g o"),
        ("", ""),
    ],
)
def test_normalize_search(raw, expected):
    assert normalize_search(raw) == expected


def test_cors_accepts_comma_list():
    s = Settings(database_url="postgresql://u:p@localhost/db", cors_origins="http://localhost:3000, http://127.0.0.1:3000")
    assert s.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_cors_rejects_non_local_origin():
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://u:p@localhost/db", cors_origins="https://example.com")


def test_empty_api_keys_become_none():
    s = Settings(database_url="postgresql://u:p@localhost/db", anthropic_api_key="", evds_api_key="")
    assert s.anthropic_api_key is None and s.evds_api_key is None


def test_secrets_not_in_repr():
    s = Settings(database_url="postgresql://u:supersecret@localhost/db", anthropic_api_key="sk-ant-xyz")
    assert "supersecret" not in repr(s) and "sk-ant-xyz" not in repr(s)


def test_log_filter_redacts_secrets_and_url_passwords():
    f = RedactSecretsFilter(["sk-ant-xyz"])
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "key=%s url=%s", ("sk-ant-xyz", "postgresql://u:pw123@h/db"), None)
    f.filter(rec)
    msg = rec.getMessage()
    assert "sk-ant-xyz" not in msg and "pw123" not in msg
    assert "postgresql://u:***@h/db" in msg
