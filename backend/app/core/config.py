"""Uygulama ayarları. Değerler sadece backend/.env dosyasından ve ortam değişkenlerinden okunur."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr
    test_database_url: SecretStr | None = None

    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-opus-5-5"

    evds_api_key: SecretStr | None = None

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    log_level: str = "INFO"

    @field_validator("anthropic_api_key", "evds_api_key", "test_database_url", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        return None if v in ("", None) else v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("cors_origins")
    @classmethod
    def _only_local(cls, v: list[str]) -> list[str]:
        allowed_hosts = ("http://localhost", "http://127.0.0.1")
        for origin in v:
            if not origin.startswith(allowed_hosts):
                raise ValueError(f"CORS sadece yerel adreslere izin verir: {origin}")
        return v

    def secret_values(self) -> list[str]:
        """Loglardan silinecek gizli değerler."""
        out = []
        for s in (self.database_url, self.test_database_url, self.anthropic_api_key, self.evds_api_key):
            if s is not None and s.get_secret_value():
                out.append(s.get_secret_value())
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
