"""Haberleri hisselerle eşleştirme (kural tabanlı, saf fonksiyonlar).

- Kod eşleşmesi: büyük harfle yazılmış hisse kodu (ör. "THYAO"), en az 4 karakter.
- İsim eşleşmesi: şirket unvanından çıkarılan kısa ad (ör. "pegasus", "turk hava yollari").
  Tek kelimelik adlar (ör. "Aselsan") ancak metinde büyük harfle başlıyorsa VE haberde
  finans bağlamı (hisse, borsa, KAP, temettü...) varsa eşleşir. Böylece "Avrupa", "Hayat"
  gibi sıradan kelimeler ve şirketin finansla ilgisiz haberleri (ör. maç sonuçları) elenir.
Kural tabanlı olduğu için hatalı eşleşme olabilir; match_type ile ayrıca saklanır.
"""

import re
from dataclasses import dataclass

from app.core.text import normalize_search

_LEGAL = re.compile(
    r"\b(a\.?s\.?|a\.?o\.?|t\.?a\.?s\.?|anonim sirketi|sanayi|sanayii|ticaret|ve|holding|yatirim ortakligi|"
    r"gayrimenkul yatirim ortakligi|bankasi|bank|grubu|group|insaat|enerji|turizm|uretim|pazarlama|ithalat|ihracat)\b.*$"
)
# Tek başına ayırt edici olmayan ilk kelimeler
_GENERIC = {
    "turk", "turkiye", "turkiye'nin", "anadolu", "istanbul", "ege", "akdeniz", "marmara", "karadeniz", "global",
    "yeni", "ulusal", "milli", "genel", "dogu", "bati", "orta", "ilk", "net", "best", "mega", "ana", "park", "europe",
    # şirket adı olarak kullanılan sıradan kelimeler / yer adları
    "afyon", "akademi", "altin", "arena", "atlas", "avrupa", "baskent", "bayrak", "bereket", "birikim", "birlik",
    "bizim", "bursa", "buyuk", "deger", "destek", "dinamik", "dogru", "elite", "federal", "formul", "galata",
    "gelecek", "girisim", "golden", "gozde", "hareket", "hayat", "huzur", "indeks", "kalkinma", "kapital",
    "katilim", "yatirim", "servet", "izmir", "ankara", "kocaeli", "konya", "adana", "antalya", "kayseri",
    "gaziantep", "trakya", "pamukkale", "kuzey", "guney", "dunya", "gunes", "yildiz", "ozel", "merkez", "lider",
    "pozitif", "pera", "sinerji", "vakif", "ziraat", "halk", "emlak", "konut", "enerji", "gida", "kimya",
}
# Tek kelimelik ad eşleşmesi için haberde bulunması gereken finans kelimeleri (normalize edilmiş)
_FINANCE_CONTEXT = (
    "hisse", "borsa", "bist", "kap ", "sirket", "temettu", "bilanco", "net kar", "kar payi", "zarar", "ciro",
    "hasilat", "favok", "sermaye", "bedelsiz", "bedelli", "halka arz", "ihale", "sozlesme", "yatirimci",
    "hedef fiyat", "ceyrek", "pay geri", "satis gelir", "piyasa degeri", "kredi notu", "ihracat", "siparis",
)


@dataclass(frozen=True)
class StockKey:
    stock_id: int
    symbol: str
    name_key: str | None


def name_key(title: str) -> str | None:
    """Şirket unvanından haberlerde aranacak kısa ad."""
    base = normalize_search(title).replace(".", " ").replace(",", " ")
    base = " ".join(base.split())
    short = _LEGAL.sub("", base).strip() or base
    words = short.split()
    if not words:
        return None
    if len(words[0]) >= 5 and words[0] not in _GENERIC:
        return words[0]
    key = " ".join(words[:3]) if len(words) >= 3 else " ".join(words)
    return key if len(key) >= 8 and " " in key else None


def build_keys(stocks: list[tuple[int, str, str]]) -> list[StockKey]:
    """stocks: (id, symbol, şirket unvanı). Aynı kısa adı paylaşan şirketler için isim eşleşmesi kapatılır."""
    keys = [StockKey(sid, sym, name_key(title)) for sid, sym, title in stocks]
    counts: dict[str, set[str]] = {}
    for k in keys:
        if k.name_key:
            counts.setdefault(k.name_key, set()).add(k.symbol[:4])
    return [k if (k.name_key is None or len(counts[k.name_key]) == 1) else StockKey(k.stock_id, k.symbol, None)
            for k in keys]


_WORD = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9\-]+")


def _capitalized_words(text: str) -> set[str]:
    """Metinde büyük harfle başlayan kelimelerin normalize hâli (kesme işaretinden önceki kök)."""
    return {normalize_search(w) for w in _WORD.findall(text) if w[:1].isupper()}


def match(text: str, keys: list[StockKey]) -> dict[int, str]:
    """Metinde geçen hisseler: {stock_id: "symbol" | "name"}"""
    out: dict[int, str] = {}
    norm = " " + " ".join(re.sub(r"[^a-z0-9 ]", " ", normalize_search(text)).split()) + " "
    has_context = any(f" {w}" in norm for w in _FINANCE_CONTEXT)
    capitalized = _capitalized_words(text)
    for k in keys:
        if len(k.symbol) >= 4 and re.search(rf"(?<![A-Z0-9ÇĞİÖŞÜ]){re.escape(k.symbol)}(?![A-Z0-9ÇĞİÖŞÜ])", text):
            out[k.stock_id] = "symbol"
        elif k.name_key and f" {k.name_key} " in norm:
            if " " in k.name_key or (has_context and k.name_key in capitalized):
                out.setdefault(k.stock_id, "name")
    return out
