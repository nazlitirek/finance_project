"""Google Gemini sağlayıcısı (google-genai SDK, Interactions API).

Yapılandırılmış çıktı: response_format içinde JSON şema verilir, dönen metin Pydantic ile doğrulanır.
Şemadaki $ref / $defs referansları gönderilmeden önce açılır (iç içe şemalar için).
Not: Ücretsiz katmanda Google, gönderilen içeriği ürünlerini geliştirmek için kullanabilir; ücretli katmanda kullanmaz.
"""

import copy
import logging
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.client import AIError, AIMeta
from app.core.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Uygulamadaki effort adları → Gemini thinking_level (low / medium / high bütün güncel modellerde var)
THINKING = {"low": "low", "medium": "medium", "high": "high"}


@lru_cache
def _client():
    from google import genai

    key = get_settings().gemini_api_key
    if key is None:
        raise AIError("GEMINI_API_KEY tanımlı değil. backend/.env dosyasına ekleyin.", "not_configured")
    return genai.Client(api_key=key.get_secret_value().strip())


def inline_refs(schema: dict) -> dict:
    """Pydantic JSON şemasındaki {"$ref": "#/$defs/X"} referanslarını tanımla değiştirir."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = copy.deepcopy(defs[ref.split("/")[-1]])
                extra = {k: v for k, v in node.items() if k != "$ref"}
                return walk({**target, **extra})
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def structured(system: str, user: str, schema: type[T], effort: str = "medium",
               max_tokens: int = 16000) -> tuple[T, AIMeta]:
    from google.genai import errors

    model = get_settings().gemini_model
    try:
        inter = _client().interactions.create(
            model=model,
            input=user,
            system_instruction=system,
            response_format={"type": "text", "mime_type": "application/json",
                             "schema": inline_refs(schema.model_json_schema())},
            # düşünme token'ları da çıktı sınırına dahil → rapor için geniş sınır
            generation_config={"thinking_level": THINKING.get(effort, "medium"),
                               "max_output_tokens": max(max_tokens, 32000)},
            timeout=300,
        )
    except AIError:
        raise
    except errors.ClientError as exc:
        code = getattr(exc, "code", None)
        if code in (401, 403):
            raise AIError("Gemini API anahtarı geçersiz veya bu modele erişim izni yok.", "not_configured") from exc
        if code == 429:
            raise AIError("Gemini API istek limiti / kotası aşıldı. Biraz sonra tekrar deneyin.", "rate_limit") from exc
        if code == 404:
            raise AIError(f"Gemini modeli bulunamadı: {model}. GEMINI_MODEL ayarını kontrol edin.", "error") from exc
        raise AIError(f"Gemini API isteği reddetti (HTTP {code}).", "error") from exc
    except errors.ServerError as exc:
        raise AIError(f"Gemini API sunucu hatası (HTTP {getattr(exc, 'code', '?')}). Daha sonra tekrar deneyin.",
                      "error") from exc
    except errors.APIError as exc:
        raise AIError(f"Gemini API hatası (HTTP {getattr(exc, 'code', '?')}).", "error") from exc
    except Exception as exc:  # noqa: BLE001 — bağlantı / zaman aşımı hataları (httpx)
        raise AIError("Gemini API'ye bağlanılamadı. İnternet bağlantısını kontrol edin.", "connection") from exc

    usage = inter.usage
    meta = AIMeta(
        model=inter.model or model, request_id=inter.id, stop_reason=str(inter.status),
        input_tokens=getattr(usage, "total_input_tokens", 0) or 0,
        output_tokens=(getattr(usage, "total_output_tokens", 0) or 0) + (getattr(usage, "total_thought_tokens", 0) or 0),
        cache_read_tokens=getattr(usage, "total_cached_tokens", 0) or 0,
        extra={"provider": "gemini"},
    )
    if inter.status == "incomplete":
        raise AIError("AI yanıtı uzunluk sınırına takıldı; çıktı tamamlanamadı.", "invalid_output")
    if inter.status != "completed":
        detail = "; ".join(str(e) for e in (inter.errors or []))[:300]
        raise AIError(f"Gemini isteği tamamlanmadı (durum: {inter.status}). {detail}".strip(), "error")
    if not inter.output_text:
        raise AIError("Gemini boş yanıt döndürdü (güvenlik filtresi olabilir).", "refusal")
    try:
        parsed = schema.model_validate_json(inter.output_text)
    except ValidationError as exc:
        raise AIError("AI çıktısı beklenen JSON şemasına uymadı.", "invalid_output") from exc
    log.info("Gemini %s: %d giriş / %d çıkış token", meta.model, meta.input_tokens, meta.output_tokens)
    return parsed, meta
