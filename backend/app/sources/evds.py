"""TCMB EVDS adapteri (resmî, ücretsiz API; anahtar gerekir)."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.sources.base import HttpSource, SourceError

BASE = "https://evds3.tcmb.gov.tr/igmevdsms-dis"


@dataclass(frozen=True)
class SeriesDef:
    code: str
    name: str
    frequency: str  # daily / weekly / monthly
    unit: str
    evds_frequency: int | None = None  # EVDS "frequency" parametresi (5 = aylık)
    note: str | None = None  # doğrulama notu


# Çekilecek seriler. Kodlar 21.11.2026'da gerçek isteklerle denendi.
SERIES: list[SeriesDef] = [
    SeriesDef("TP.DK.USD.A", "USD/TRY döviz alış kuru (TCMB)", "daily", "TL"),
    SeriesDef("TP.DK.EUR.A", "EUR/TRY döviz alış kuru (TCMB)", "daily", "TL"),
    SeriesDef("TP.APIFON4", "TCMB ağırlıklı ortalama fonlama maliyeti", "daily", "%"),
    SeriesDef("TP.FG.J0", "TÜFE endeksi", "monthly", "endeks", evds_frequency=5,
              note="Bu seride son değer 2026-01; TÜİK baz yılı değişikliği nedeniyle yeni seri kodu teyit edilmeli."),
    SeriesDef("TP.YISGUCU2.G8", "İşsizlik oranı", "monthly", "%",
              note="Seri tanımı EVDS'de teyit edilmeli."),
]

_DAY = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_MONTH = re.compile(r"^(\d{4})-(\d{1,2})$")


def parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if _DAY.match(raw):
        return datetime.strptime(raw, "%d-%m-%Y").date()
    m = _MONTH.match(raw)
    if m:
        return date(int(m[1]), int(m[2]), 1)
    return None


def parse_series(code: str, payload: dict) -> list[tuple[date, Decimal]]:
    col = code.replace(".", "_")
    out = []
    for item in payload.get("items") or []:
        d = parse_date(item.get("Tarih"))
        raw = item.get(col)
        if d is None or raw in (None, ""):
            continue  # tatil / eksik gün → kaydedilmez, doldurulmaz
        try:
            out.append((d, Decimal(str(raw))))
        except InvalidOperation:
            continue
    return out


class EvdsSource(HttpSource):
    code = "evds"
    min_interval = 0.5

    def __init__(self, api_key: str | None, **kw):
        super().__init__(**kw)
        self._key = api_key

    def series(self, s: SeriesDef, start: date, end: date) -> list[tuple[date, Decimal]]:
        if not self._key:
            raise SourceError(self.code, "EVDS_API_KEY tanımlı değil")
        url = f"{BASE}/series={s.code}&startDate={start:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json"
        if s.evds_frequency:
            url += f"&frequency={s.evds_frequency}"
        payload = self.get_json(url, headers={"key": self._key})
        if not isinstance(payload, dict):
            raise SourceError(self.code, f"{s.code}: beklenmeyen yanıt")
        return parse_series(s.code, payload)
