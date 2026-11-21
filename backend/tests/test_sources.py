"""Adapter ayrıştırma testleri. Örnekler kaynakların 21.11.2026'daki gerçek yanıt biçimindedir; internet gerekmez."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.sources.base import HttpSource, SourceError
from app.sources.evds import parse_series
from app.sources.isyatirim import parse_prices, parse_statements, recent_quarters
from app.sources.kap import parse_companies, parse_disclosures, parse_sectors
from app.sources.rss import parse_feed, title_hash
from app.sources.tcmb_fx import parse_today

# ---------------------------------------------------------------- KAP

KAP_COMPANIES = (
    'self.__next_f.push([1,"[{\\"mkkMemberOid\\":\\"oid1\\",\\"kapMemberTitle\\":\\"TÜRK HAVA YOLLARI A.O.\\",'
    '\\"relatedMemberTitle\\":\\"X\\",\\"stockCode\\":\\"THYAO\\",\\"cityName\\":\\"İSTANBUL\\",'
    '\\"relatedMemberOid\\":\\"r1\\",\\"kapMemberType\\":\\"IGS\\"},'
    '{\\"mkkMemberOid\\":\\"oid2\\",\\"kapMemberTitle\\":\\"TÜRKİYE İŞ BANKASI A.Ş.\\",'
    '\\"relatedMemberTitle\\":\\"Y\\",\\"stockCode\\":\\"ISCTR, ISATR\\",\\"cityName\\":\\"İSTANBUL\\",'
    '\\"relatedMemberOid\\":\\"r2\\",\\"kapMemberType\\":\\"IGS\\"},'
    '{\\"mkkMemberOid\\":\\"oid3\\",\\"kapMemberTitle\\":\\"BİR FON\\",'
    '\\"relatedMemberTitle\\":\\"Z\\",\\"stockCode\\":\\"FON\\",\\"cityName\\":\\"\\",'
    '\\"relatedMemberOid\\":\\"r3\\",\\"kapMemberType\\":\\"FON\\"}]"])'
)

KAP_SECTORS = (
    '{"sectorName":"BANKALAR","sectorOid":"s-bank","sectorNo":"008000.001000.","mkkMemberOid":"oid2",'
    '"stockCode":"ISCTR, ISATR","title":"TÜRKİYE İŞ BANKASI A.Ş.","kapTypes":["IGS"]},'
    '{"sectorName":"ULAŞTIRMA VE DEPOLAMA","sectorOid":"s-ul","sectorNo":"007000.001000.","mkkMemberOid":"oid1",'
    '"stockCode":"THYAO","title":"TÜRK HAVA YOLLARI A.O.","kapTypes":["IGS"]}]}},"content":['
    '{"mainSectorName":"MALİ KURULUŞLAR","mainSectorOid":"m-mali","mainSectorNo":"008000.","mkkMemberOid":"oid2",'
    '"stockCode":"ISCTR, ISATR","title":"TÜRKİYE İŞ BANKASI A.Ş."},'
    '{"mainSectorName":"ULAŞTIRMA VE DEPOLAMA","mainSectorOid":"m-ul","mainSectorNo":"007000.","mkkMemberOid":"oid1",'
    '"stockCode":"THYAO","title":"TÜRK HAVA YOLLARI A.O."}'
).replace('"', '\\"')


def test_kap_companies_igs_only_and_multi_codes():
    out = {c.mkk_oid: c for c in parse_companies(KAP_COMPANIES)}
    assert set(out) == {"oid1", "oid2"}
    assert out["oid2"].symbols == ("ISCTR", "ISATR")
    assert out["oid1"].title == "TÜRK HAVA YOLLARI A.O."


def test_kap_sectors_link_main_and_sub():
    rows = {r.symbol: r for r in parse_sectors(KAP_SECTORS)}
    assert set(rows) == {"ISCTR", "ISATR", "THYAO"}
    assert rows["ISATR"].sub_name == "BANKALAR" and rows["ISATR"].main_name == "MALİ KURULUŞLAR"
    assert rows["THYAO"].sub_name == rows["THYAO"].main_name  # ana = alt durumu


def test_kap_disclosures_timezone_and_bad_rows():
    rows = parse_disclosures([
        {"publishDate": "20.11.2026 23:51:04", "kapTitle": " KUZUGRUP GYO A.Ş. ", "disclosureClass": "ODA",
         "disclosureType": "CA", "disclosureCategory": "STT", "summary": "s", "subject": "Pay geri alım",
         "disclosureIndex": 1700896, "stockCodes": "KZGYO", "attachmentCount": 0},
        {"publishDate": "bozuk", "disclosureIndex": 1},
    ])
    assert len(rows) == 1
    d = rows[0]
    assert d.published_at.utcoffset() == timedelta(hours=3)
    assert d.symbols == ("KZGYO",) and d.company_title == "KUZUGRUP GYO A.Ş."
    assert d.url.endswith("/tr/Bildirim/1700896")


# ---------------------------------------------------------------- İş Yatırım

PRICE_ROWS = [
    {"HGDG_HS_KODU": "THYAO", "HGDG_TARIH": "19-11-2026", "HGDG_KAPANIS": 320.5, "HGDG_AOF": 319.0, "HGDG_MIN": 318,
     "HGDG_MAX": 322, "HGDG_HACIM": 9.0e9, "END_ENDEKS_KODU": "01", "END_DEGER": 11050.1, "SERMAYE": 1.38e9,
     "HG_KAPANIS": 320.5, "HG_AOF": 319.0, "HG_MIN": 318, "HG_MAX": 322, "HG_HACIM": 9.0e9},
    {"HGDG_HS_KODU": "THYAO", "HGDG_TARIH": "20-11-2026", "HGDG_KAPANIS": 329.0, "HGDG_AOF": 326.2, "HGDG_MIN": 322.75,
     "HGDG_MAX": 329.25, "HGDG_HACIM": 9.5e9, "END_ENDEKS_KODU": "01", "END_DEGER": 11131.32, "SERMAYE": 1.38e9,
     "HG_KAPANIS": 329.0, "HG_AOF": 326.2, "HG_MIN": 322.75, "HG_MAX": 329.25, "HG_HACIM": 9.5e9},
    {"HGDG_TARIH": "21-11-2026", "HGDG_KAPANIS": 0, "HG_KAPANIS": None},  # fiyatsız gün
    {"HGDG_TARIH": "bozuk"},
]


def test_prices_adjusted_and_raw_no_open():
    b = parse_prices("THYAO", PRICE_ROWS)
    assert len(b.bars) == 4  # 2 gün × (düzeltilmiş + düzeltilmemiş); fiyatsız gün atlandı
    assert {x.adjusted for x in b.bars} == {True, False}
    last = [x for x in b.bars if x.day == date(2026, 11, 20) and x.adjusted][0]
    assert last.close == Decimal("329.0") and last.high == Decimal("329.25") and last.turnover == Decimal("9500000000.0")
    assert not hasattr(last, "open")  # kaynak açılış vermiyor
    assert b.xu100 == [(date(2026, 11, 19), Decimal("11050.1")), (date(2026, 11, 20), Decimal("11131.32"))]
    assert b.paid_in_capital == (date(2026, 11, 20), Decimal("1380000000.0"))


def test_statements_map_values_to_periods():
    rows = [
        {"itemCode": "3C", "itemDescTr": "Satış Gelirleri", "itemDescEng": "Revenue",
         "value1": "981030000000", "value2": "585069000000", "value3": None, "value4": ""},
        {"itemCode": "", "value1": "1"},
    ]
    out = parse_statements(rows, [(2026, 9), (2026, 6), (2026, 3), (2025, 12)])
    assert [(v.fiscal_year, v.fiscal_period, v.value) for v in out] == [
        (2026, 9, Decimal("981030000000")), (2026, 6, Decimal("585069000000"))]


@pytest.mark.parametrize(("today", "expected"), [
    (date(2026, 11, 21), [(2026, 9), (2026, 6), (2026, 3), (2025, 12), (2025, 9)]),
    (date(2026, 1, 5), [(2025, 12), (2025, 9), (2025, 6), (2025, 3), (2024, 12)]),
    (date(2026, 3, 31), [(2025, 12), (2025, 9), (2025, 6), (2025, 3), (2024, 12)]),
])
def test_recent_quarters(today, expected):
    assert recent_quarters(today, 5) == expected


# ---------------------------------------------------------------- EVDS / TCMB

def test_evds_daily_monthly_and_holidays():
    daily = parse_series("TP.DK.USD.A", {"items": [
        {"Tarih": "19-11-2026", "TP_DK_USD_A": "50.3536"}, {"Tarih": "21-11-2026", "TP_DK_USD_A": None}]})
    assert daily == [(date(2026, 11, 19), Decimal("50.3536"))]
    monthly = parse_series("TP.FG.J0", {"items": [{"Tarih": "2026-1", "TP_FG_J0": "3683.83"}]})
    assert monthly == [(date(2026, 1, 1), Decimal("3683.83"))]


def test_tcmb_today_xml():
    xml = ('<?xml version="1.0" encoding="UTF-8"?><Tarih_Date Tarih="20.11.2026" Date="11/20/2026">'
           '<Currency Kod="USD"><ForexBuying>50.3786</ForexBuying></Currency>'
           '<Currency Kod="EUR"><ForexBuying>55.3581</ForexBuying></Currency>'
           '<Currency Kod="GBP"><ForexBuying>66.1</ForexBuying></Currency></Tarih_Date>')
    day, rates = parse_today(xml)
    assert day == date(2026, 11, 20) and rates == {"USD": Decimal("50.3786"), "EUR": Decimal("55.3581")}


# ---------------------------------------------------------------- RSS

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>THYAO &amp; PGSUS yükseldi - Hisse.net</title><link>https://x.test/1</link>
<description>&lt;p&gt;Borsa &lt;b&gt;güne&lt;/b&gt; yükselişle başladı&lt;/p&gt;</description>
<pubDate>Fri, 20 Nov 2026 10:00:00 +0300</pubDate><source url="https://hisse.net">Hisse.net</source></item>
<item><title></title><link>https://x.test/2</link></item>
</channel></rss>"""


def test_rss_parse_cleans_html_and_reads_source():
    items = parse_feed(RSS, "Google Haberler")
    assert len(items) == 1
    it = items[0]
    assert it.title == "THYAO & PGSUS yükseldi - Hisse.net"
    assert it.summary == "Borsa güne yükselişle başladı"
    assert it.publisher == "Hisse.net"
    assert it.published_at == datetime(2026, 11, 20, 7, 0, tzinfo=timezone.utc)


def test_title_hash_ignores_publisher_suffix_and_case():
    assert title_hash("THYAO yükseldi - Hisse.net") == title_hash("thyao YÜKSELDİ")
    assert title_hash("THYAO yükseldi") != title_hash("THYAO düştü")


def test_rss_bad_xml_raises_source_error():
    with pytest.raises(SourceError):
        parse_feed("<html>bakım</html><", "AA")


# ---------------------------------------------------------------- HTTP katmanı

def _source(handler) -> HttpSource:
    src = HttpSource(client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    src.min_interval = 0
    return src


def test_http_retries_on_503_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"ok": True})

    assert _source(handler).get_json("https://x.test") == {"ok": True}
    assert len(calls) == 2


def test_http_404_fails_without_retry():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(SourceError):
        _source(handler).get_json("https://x.test")
    assert len(calls) == 1


def test_http_gives_up_after_retries():
    with pytest.raises(SourceError):
        _source(lambda req: httpx.Response(500)).get_json("https://x.test")


def test_http_non_json_is_source_error():
    with pytest.raises(SourceError):
        _source(lambda req: httpx.Response(200, text="<html>")).get_json("https://x.test")
