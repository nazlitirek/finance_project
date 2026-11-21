"""Finansal tablo standartlaştırma kuralları.

Saf fonksiyonlar; veritabanına dokunmaz. Testleri: tests/test_normalize.py
"""

from datetime import date
from decimal import Decimal

# KGK kararıyla TMS 29, 31.12.2023 ve sonrasında sona eren dönemlerde zorunlu.
TMS29_START = date(2023, 12, 31)

# Bu profiller için TMS 29 uygulaması ayrı düzenleyici kararlara (BDDK, SEDDK vb.) bağlı.
# Hangi dönemde uygulandığı teyit edilmeden "bilinmiyor" (None) olarak işaretlenir.
REGULATED_FINANCIAL_PROFILES = {"bank", "insurance", "leasing_factoring", "other_financial"}

# KAP alt sektör adı → analiz profili
SECTOR_PROFILES = {
    "BANKALAR": "bank",
    "SİGORTA ŞİRKETLERİ": "insurance",
    "HOLDİNGLER VE YATIRIM ŞİRKETLERİ": "holding",
    "GAYRİMENKUL YATIRIM ORTAKLIKLARI": "reit",
    "FİNANSAL KİRALAMA VE FAKTORİNG ŞİRKETLERİ": "leasing_factoring",
    "ARACI KURUMLAR": "other_financial",
    "MENKUL KIYMET YATIRIM ORTAKLIKLARI": "other_financial",
    "GİRİŞİM SERMAYESİ YATIRIM ORTAKLIKLARI": "other_financial",
}
FINANCIAL_MAIN_SECTOR = "MALİ KURULUŞLAR"


def sector_profile(sub_sector: str, main_sector: str | None = None) -> str:
    p = SECTOR_PROFILES.get(sub_sector.strip().upper())
    if p:
        return p
    if main_sector and main_sector.strip().upper() == FINANCIAL_MAIN_SECTOR:
        return "other_financial"
    return "general"


def statement_type(item_code: str) -> str | None:
    """İş Yatırım kalem kodunun ilk karakteri tablo türünü verir."""
    return {"1": "balance", "2": "balance", "3": "income", "4": "cashflow"}.get(item_code[:1])


def is_cumulative(stmt_type: str) -> bool:
    # Gelir tablosu ve nakit akış tablosu yıl başından itibaren kümülatif raporlanır.
    return stmt_type in ("income", "cashflow")


def financial_groups(profile: str) -> list[str]:
    """İş Yatırım tablo şablonu, denenme sırasıyla. XI_29: sanayi/hizmet, UFRS: banka/sigorta vb."""
    if profile in ("bank", "insurance", "leasing_factoring"):
        return ["UFRS", "XI_29"]
    return ["XI_29", "UFRS"]


def inflation_status(period_end: date, profile: str) -> tuple[bool | None, str]:
    if period_end < TMS29_START:
        return False, "31.12.2023 öncesi dönem: TMS 29 zorunlu değildi"
    if profile in REGULATED_FINANCIAL_PROFILES:
        return None, "Finans kuruluşu: TMS 29 uygulaması düzenleyici karara bağlı, teyit edilmedi"
    return True, "TMS 29: 31.12.2023 ve sonrası dönemlerde zorunlu (KGK)"


def standalone_quarters(cumulative: dict[tuple[int, int], Decimal | None]) -> dict[tuple[int, int], Decimal | None]:
    """Kümülatif değerlerden tek çeyrek değerleri: Q2 = 6A − 3A, Q4 = 12A − 9A.

    Önceki dönem yoksa sonuç None (tahmin yapılmaz).
    Uyarı: TMS 29 uygulanan dönemlerde her rapor kendi tarihinin satın alma gücüyle verilir;
    bu farkla bulunan çeyrek değeri yaklaşık karşılaştırma içindir. Analiz katmanı bunu belirtmelidir.
    """
    out: dict[tuple[int, int], Decimal | None] = {}
    for (year, period), value in cumulative.items():
        if value is None:
            out[(year, period)] = None
        elif period == 3:
            out[(year, period)] = value
        else:
            prev = cumulative.get((year, period - 3))
            out[(year, period)] = None if prev is None else value - prev
    return out
