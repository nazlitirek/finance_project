"""Claude API istemcisi. Sadece backend'de çalışır; anahtar .env'den okunur, frontend'e gönderilmez.

- Yapılandırılmış çıktı: client.beta.messages.parse(output_format=PydanticModel) → doğrulanmış nesne
- Reddedilen isteklerde sunucu tarafı yedek model (fallbacks="default")
- Bütün API hataları Türkçe mesajlı AIError'a çevrilir; çağıran modül çökmez
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from app.core.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIError(Exception):
    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.message = message
        self.kind = kind  # not_configured / refusal / rate_limit / connection / invalid_output / error


@dataclass
class AIMeta:
    model: str
    request_id: str | None
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    fallback_used: bool = False
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@lru_cache
def _client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if key is None:
        raise AIError("ANTHROPIC_API_KEY tanımlı değil. backend/.env dosyasına ekleyin.", "not_configured")
    return anthropic.Anthropic(api_key=key.get_secret_value().strip(), timeout=300.0, max_retries=2)


def is_configured() -> bool:
    return get_settings().anthropic_api_key is not None


def structured(system: str, user: str, schema: type[T], effort: str = "medium", max_tokens: int = 16000) -> tuple[T, AIMeta]:
    """Tek istek → şemaya göre doğrulanmış çıktı. Hata durumunda AIError."""
    model = get_settings().claude_model
    try:
        resp = _client().beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            cache_control={"type": "ephemeral"},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort},
            output_format=schema,
        )
    except AIError:
        raise
    except anthropic.AuthenticationError as exc:
        raise AIError("Claude API anahtarı geçersiz.", "not_configured") from exc
    except anthropic.PermissionDeniedError as exc:
        raise AIError("Claude API anahtarının bu modele erişim izni yok.", "not_configured") from exc
    except anthropic.RateLimitError as exc:
        raise AIError("Claude API istek limiti aşıldı. Biraz sonra tekrar deneyin.", "rate_limit") from exc
    except anthropic.BadRequestError as exc:
        raise AIError(f"Claude API isteği reddetti: {exc.message}", "error") from exc
    except anthropic.APIStatusError as exc:
        raise AIError(f"Claude API hatası (HTTP {exc.status_code}). Daha sonra tekrar deneyin.", "error") from exc
    except anthropic.APIConnectionError as exc:
        raise AIError("Claude API'ye bağlanılamadı. İnternet bağlantısını kontrol edin.", "connection") from exc

    usage = resp.usage
    meta = AIMeta(
        model=resp.model, request_id=getattr(resp, "_request_id", None), stop_reason=resp.stop_reason,
        input_tokens=getattr(usage, "input_tokens", 0) or 0, output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        fallback_used=any(getattr(i, "type", None) == "fallback_message" for i in (getattr(usage, "iterations", None) or [])),
    )
    if resp.stop_reason == "refusal":
        cat = getattr(getattr(resp, "stop_details", None), "category", None)
        raise AIError(f"Claude bu isteği yanıtlamadı (kategori: {cat}).", "refusal")
    if resp.stop_reason == "max_tokens":
        raise AIError("AI yanıtı uzunluk sınırına takıldı; rapor tamamlanamadı.", "invalid_output")
    parsed = resp.parsed_output
    if parsed is None:
        raise AIError("AI çıktısı beklenen JSON şemasına uymadı.", "invalid_output")
    log.info("Claude %s: %d giriş / %d çıkış token (önbellekten %d)", meta.model, meta.input_tokens,
             meta.output_tokens, meta.cache_read_tokens)
    return parsed, meta
