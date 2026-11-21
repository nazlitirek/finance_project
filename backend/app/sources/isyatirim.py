"""İş Yatırım adapteri: günlük fiyatlar ve finansal tablolar.

Belgelenmemiş site uç noktaları. Kişisel kullanım, düşük sıklık; veri kimseyle paylaşılmaz.
Bilinen sınırlar (21.11.2026 testleri):
- Açılış fiyatı YOK. Kapanış, en yüksek, en düşük, ağırlıklı ortalama ve TL hacim var.
- Hacim TL cinsinden (lot değil).
- HGDG_* alanları bölünme/temettüye göre düzeltilmiş, HG_* alanları düzeltilmemiş fiyatlar.
- Endeks olarak sadece BIST 100 kapanışı her satırda geliyor (END_ENDEKS_KODU = "01").
- Finansal tablolar TL, tam birim (bin/milyon değil). Gelir ve nakit akış kalemleri kümülatif.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.sources.base import TR_TZ, HttpSource, SourceError

BASE = "https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx"
XU100_CODE = "01"


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    day: date
    adjusted: bool
    close: Decimal | None
    high: Decimal | None
    low: Decimal | None
    avg_price: Decimal | None
    turnover: Decimal | None  # TL


@dataclass(frozen=True)
class PriceBatch:
    bars: list[DailyBar]
    xu100: list[tuple[date, Decimal]]  # BIST 100 kapanışları
    paid_in_capital: tuple[date, Decimal] | None  # en son satırdaki ödenmiş sermaye


@dataclass(frozen=True)
class StatementValue:
    item_code: str
    name_tr: str | None
    name_en: str | None
    fiscal_year: int
    fiscal_period: int  # 3, 6, 9, 12
    value: Decimal | None


def _dec(v) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _positive(v) -> Decimal | None:
    d = _dec(v)
    return d if d is not None and d > 0 else None


def parse_prices(symbol: str, rows: list[dict]) -> PriceBatch:
    bars: list[DailyBar] = []
    xu100: list[tuple[date, Decimal]] = []
    capital = None
    for r in rows:
        try:
            day = datetime.strptime(r["HGDG_TARIH"], "%d-%m-%Y").date()
        except (KeyError, ValueError, TypeError):
            continue
        for adjusted, p in ((True, "HGDG_"), (False, "HG_")):
            close = _positive(r.get(f"{p}KAPANIS"))
            if close is None:
                continue  # fiyat yoksa satır uydurulmaz
            bars.append(DailyBar(
                symbol=symbol, day=day, adjusted=adjusted, close=close,
                high=_positive(r.get(f"{p}MAX")), low=_positive(r.get(f"{p}MIN")),
                avg_price=_positive(r.get(f"{p}AOF")), turnover=_dec(r.get(f"{p}HACIM")),
            ))
        if r.get("END_ENDEKS_KODU") == XU100_CODE:
            idx = _positive(r.get("END_DEGER"))
            if idx is not None:
                xu100.append((day, idx))
        cap = _positive(r.get("SERMAYE"))
        if cap is not None:
            capital = (day, cap)
    return PriceBatch(bars=bars, xu100=xu100, paid_in_capital=capital)


def period_end(year: int, period: int) -> date:
    return date(year, period, monthrange(year, period)[1])


def parse_statements(rows: list[dict], periods: list[tuple[int, int]]) -> list[StatementValue]:
    out = []
    for r in rows:
        code = (r.get("itemCode") or "").strip()
        if not code:
            continue
        for i, (year, period) in enumerate(periods, start=1):
            raw = r.get(f"value{i}")
            if raw is None or raw == "":
                continue  # o dönem için değer yok → kaydedilmez
            out.append(StatementValue(
                item_code=code,
                name_tr=(r.get("itemDescTr") or "").strip() or None,
                name_en=(r.get("itemDescEng") or "").strip() or None,
                fiscal_year=year, fiscal_period=period, value=_dec(raw),
            ))
    return out


def recent_quarters(today: date, count: int) -> list[tuple[int, int]]:
    """Bugünden geriye doğru dönem sonları: [(2026, 9), (2026, 6), ...]. İçinde bulunulan çeyrek hariç."""
    year, q = today.year, (today.month - 1) // 3  # tamamlanmış son çeyrek
    out = []
    while len(out) < count:
        if q == 0:
            year, q = year - 1, 4
        out.append((year, q * 3))
        q -= 1
    return out


class IsYatirimSource(HttpSource):
    code = "isyatirim"
    min_interval = 1.5

    def daily_prices(self, symbol: str, start: date, end: date) -> PriceBatch:
        j = self.get_json(f"{BASE}/HisseTekil", params={
            "hisse": symbol, "startdate": start.strftime("%d-%m-%Y"), "enddate": end.strftime("%d-%m-%Y"),
        })
        if not isinstance(j, dict) or not j.get("ok"):
            raise SourceError(self.code, f"{symbol} fiyatları alınamadı: {(j or {}).get('errorDescription')}")
        return parse_prices(symbol, j.get("value") or [])

    def statements(self, symbol: str, financial_group: str, periods: list[tuple[int, int]]) -> list[StatementValue]:
        """Bir istekte en fazla 4 dönem. periods: [(yıl, ay), ...]"""
        out: list[StatementValue] = []
        for i in range(0, len(periods), 4):
            chunk = periods[i:i + 4]
            params = {"companyCode": symbol, "exchange": "TRY", "financialGroup": financial_group}
            for n, (y, p) in enumerate(chunk, start=1):
                params[f"year{n}"], params[f"period{n}"] = y, p
            j = self.get_json(f"{BASE}/MaliTablo", params=params)
            if not isinstance(j, dict) or not j.get("ok"):
                raise SourceError(self.code, f"{symbol} finansal tabloları alınamadı")
            out.extend(parse_statements(j.get("value") or [], chunk))
        return out


def bar_time(day: date) -> datetime:
    """Günlük mumun zaman damgası: o günün 00:00'ı (İstanbul)."""
    return datetime(day.year, day.month, day.day, tzinfo=TR_TZ)
