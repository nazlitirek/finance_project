"""Loglama. Gizli değerler (API anahtarları, veritabanı şifresi) log çıktısından silinir."""

import logging
import re

_PASSWORD_IN_URL = re.compile(r"(://[^:/@\s]+:)([^@\s]+)(@)")


class RedactSecretsFilter(logging.Filter):
    def __init__(self, secrets: list[str]):
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def _redact(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "***")
        return _PASSWORD_IN_URL.sub(r"\1***\3", text)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.getMessage())
        record.args = None
        return True


def setup_logging(level: str, secrets: list[str]) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactSecretsFilter(secrets))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
