"""Veri kaynağı adapterleri için ortak HTTP katmanı.

- Kaynak başına en az bekleme süresi (kibar erişim, kullanım koşullarına saygı)
- 429 / 5xx / bağlantı hatalarında sınırlı sayıda yeniden deneme
- Bütün hatalar SourceError olarak yükselir; üst katman bir kaynağın hatasını diğerlerinden ayırır
"""

import logging
import threading
import time
from datetime import timedelta, timezone

import httpx

log = logging.getLogger(__name__)

# Türkiye 2016'dan beri sabit UTC+3 kullanıyor (yaz saati yok)
TR_TZ = timezone(timedelta(hours=3), name="Europe/Istanbul")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


class SourceError(Exception):
    """Bir veri kaynağına erişilemedi veya beklenmeyen yanıt verdi."""

    def __init__(self, source: str, message: str):
        super().__init__(f"[{source}] {message}")
        self.source = source
        self.message = message


class HttpSource:
    code: str = "base"
    min_interval: float = 1.0  # aynı kaynağa iki istek arası en az saniye
    max_retries: int = 2
    timeout: float = 30.0

    def __init__(self, client: httpx.Client | None = None, sleep=time.sleep):
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=self.timeout, follow_redirects=True
        )
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_request = 0.0

    def _wait_turn(self) -> None:
        with self._lock:
            wait = self._last_request + self.min_interval - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last_request = time.monotonic()

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._wait_turn()
            try:
                r = self._client.request(method, url, **kw)
            except httpx.HTTPError as exc:
                last_exc = exc
                log.warning("%s: bağlantı hatası (%s), deneme %d", self.code, exc.__class__.__name__, attempt + 1)
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    last_exc = SourceError(self.code, f"HTTP {r.status_code}")
                    log.warning("%s: HTTP %d, deneme %d", self.code, r.status_code, attempt + 1)
                elif r.status_code >= 400:
                    raise SourceError(self.code, f"HTTP {r.status_code}")
                else:
                    return r
            if attempt < self.max_retries:
                self._sleep(2 ** attempt * 2)
        raise SourceError(self.code, f"erişilemedi: {last_exc}")

    def get_json(self, url: str, **kw):
        r = self.request("GET", url, **kw)
        try:
            return r.json()
        except ValueError as exc:
            raise SourceError(self.code, "JSON beklenirken farklı yanıt geldi") from exc
