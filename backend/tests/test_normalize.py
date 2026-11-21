from datetime import date
from decimal import Decimal

import pytest

from app.normalize.financials import (
    financial_groups,
    inflation_status,
    is_cumulative,
    sector_profile,
    standalone_quarters,
    statement_type,
)
from app.normalize.news_match import StockKey, build_keys, match, name_key


# ---------------------------------------------------------------- finansal tablolar

@pytest.mark.parametrize(("code", "expected"), [
    ("1A", "balance"), ("2AA", "balance"), ("3C", "income"), ("4C", "cashflow"), ("9X", None), ("", None)])
def test_statement_type(code, expected):
    assert statement_type(code) == expected


def test_cumulative_only_for_flow_statements():
    assert is_cumulative("income") and is_cumulative("cashflow") and not is_cumulative("balance")


@pytest.mark.parametrize(("sub", "main", "expected"), [
    ("BANKALAR", "MALİ KURULUŞLAR", "bank"),
    ("SİGORTA ŞİRKETLERİ", "MALİ KURULUŞLAR", "insurance"),
    ("HOLDİNGLER VE YATIRIM ŞİRKETLERİ", "MALİ KURULUŞLAR", "holding"),
    ("GAYRİMENKUL YATIRIM ORTAKLIKLARI", "MALİ KURULUŞLAR", "reit"),
    ("BİLİNMEYEN MALİ ALT SEKTÖR", "MALİ KURULUŞLAR", "other_financial"),
    ("SAVUNMA", "İMALAT", "general"),
])
def test_sector_profile(sub, main, expected):
    assert sector_profile(sub, main) == expected


def test_financial_groups_order():
    assert financial_groups("bank")[0] == "UFRS"
    assert financial_groups("general")[0] == "XI_29"


@pytest.mark.parametrize(("pe", "profile", "expected"), [
    (date(2023, 9, 30), "general", False),
    (date(2023, 12, 31), "general", True),
    (date(2026, 9, 30), "holding", True),
    (date(2026, 9, 30), "bank", None),  # teyit edilmedi → bilinmiyor
    (date(2026, 9, 30), "insurance", None),
    (date(2022, 12, 31), "bank", False),
])
def test_inflation_status(pe, profile, expected):
    value, basis = inflation_status(pe, profile)
    assert value is expected and basis


def test_standalone_quarters_from_cumulative():
    cum = {(2026, 3): Decimal(100), (2026, 6): Decimal(250), (2026, 9): Decimal(450), (2025, 12): Decimal(900)}
    q = standalone_quarters(cum)
    assert q[(2026, 3)] == 100 and q[(2026, 6)] == 150 and q[(2026, 9)] == 200
    assert q[(2025, 12)] is None  # 2025/9 yok → tahmin edilmez


def test_standalone_quarters_none_and_negative():
    q = standalone_quarters({(2026, 3): Decimal(-50), (2026, 6): None, (2026, 9): Decimal(10)})
    assert q[(2026, 3)] == -50 and q[(2026, 6)] is None and q[(2026, 9)] is None


# ---------------------------------------------------------------- haber eşleştirme

@pytest.mark.parametrize(("title", "expected"), [
    ("ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.", "aselsan"),
    ("TÜRK HAVA YOLLARI A.O.", "turk hava yollari"),
    ("AVRUPA YATIRIM HOLDİNG A.Ş.", "avrupa yatirim"),  # "avrupa" tek başına sıradan → iki kelime
    ("KOÇ HOLDİNG A.Ş.", None),  # çok kısa
])
def test_name_key(title, expected):
    assert name_key(title) == expected


KEYS = build_keys([(1, "THYAO", "TÜRK HAVA YOLLARI A.O."), (2, "ASELS", "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş."),
                   (3, "AVHOL", "AVRUPA YATIRIM HOLDİNG A.Ş."), (4, "SISE", "TÜRKİYE ŞİŞE VE CAM FABRİKALARI A.Ş."),
                   (5, "ATA", "ATA YATIRIM")])


def test_match_by_symbol():
    assert match("BofA bugün THYAO toplarken ASELS sattı", KEYS) == {1: "symbol", 2: "symbol"}


def test_short_symbols_and_lowercase_symbols_ignored():
    assert match("ata thyao", KEYS) == {}


def test_single_word_name_needs_finance_context_and_capital():
    assert match("Aselsan yeni bir ihracat sözleşmesi imzaladı", KEYS) == {2: "name"}
    assert match("Aselsan stantı fuarda ilgi gördü", KEYS) == {}  # finans bağlamı yok
    assert match("aselsan hissesi yükseldi", KEYS) == {}  # büyük harf yok


def test_multi_word_name_matches_without_context():
    assert match("Türk Hava Yolları yeni rota açtı", KEYS) == {1: "name"}


def test_generic_words_do_not_match():
    assert match("Avrupa borsaları güne düşüşle başladı, hisse senetleri geriledi", KEYS) == {}


def test_ambiguous_name_keys_disabled():
    keys = build_keys([(1, "AAAA", "ORNEKCO GIDA A.Ş."), (2, "BBBB", "ORNEKCO ENERJİ A.Ş.")])
    assert all(k.name_key is None for k in keys)
    assert isinstance(keys[0], StockKey)
