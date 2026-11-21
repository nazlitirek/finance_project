"""Türkçe metin yardımcıları."""

_TR_FOLD = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "I": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})


def normalize_search(text: str) -> str:
    """Arama için metni sadeleştirir: Türkçe harfleri ASCII'ye çevirir, küçük harf yapar,
    fazla boşlukları siler. "TÜRK HAVA YOLLARI" ve "turk hava yollari" aynı sonucu verir."""
    folded = text.translate(_TR_FOLD).lower()
    return " ".join(folded.split())
