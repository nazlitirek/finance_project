"""KAP (Kamuyu Aydınlatma Platformu) adapteri.

Resmî ve belgelenmiş bir API değil; KAP sitesinin kullandığı yanıtlar okunur.
Erişim sıklığı düşük tutulur (min_interval).
"""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from app.sources.base import TR_TZ, HttpSource, SourceError

BASE = "https://www.kap.org.tr"


@dataclass(frozen=True)
class KapCompany:
    mkk_oid: str
    title: str
    symbols: tuple[str, ...]  # bazı şirketlerin birden fazla pay kodu var: "ISCTR, ISATR"
    city: str | None


@dataclass(frozen=True)
class KapSectorMembership:
    main_name: str
    main_oid: str
    main_no: str
    sub_name: str
    sub_oid: str
    sub_no: str
    mkk_oid: str
    symbol: str


@dataclass(frozen=True)
class KapDisclosureRow:
    index: int
    published_at: datetime
    company_title: str
    symbols: tuple[str, ...]
    disclosure_class: str | None
    disclosure_type: str | None
    category: str | None
    subject: str | None
    summary: str | None
    attachment_count: int

    @property
    def url(self) -> str:
        return f"{BASE}/tr/Bildirim/{self.index}"


_COMPANY_RE = re.compile(
    r'\{"mkkMemberOid":"(?P<oid>[^"]*)","kapMemberTitle":"(?P<title>[^"]*)","relatedMemberTitle":"[^"]*",'
    r'"stockCode":"(?P<codes>[^"]*)","cityName":"(?P<city>[^"]*)","relatedMemberOid":"[^"]*","kapMemberType":"IGS"\}'
)
_SUB_RE = re.compile(
    r'\{"sectorName":"(?P<name>[^"]*)","sectorOid":"(?P<oid>[^"]*)","sectorNo":"(?P<no>[^"]*)",'
    r'"mkkMemberOid":"(?P<mkk>[^"]*)","stockCode":"(?P<codes>[^"]*)","title":"[^"]*","kapTypes":\[[^\]]*"IGS"[^\]]*\]\}'
)
_MAIN_RE = re.compile(
    r'\{"mainSectorName":"(?P<name>[^"]*)","mainSectorOid":"(?P<oid>[^"]*)","mainSectorNo":"(?P<no>[^"]*)",'
    r'"mkkMemberOid":"(?P<mkk>[^"]*)","stockCode":"(?P<codes>[^"]*)"'
)


def _unescape(page: str) -> str:
    # Sayfa içi veri JSON-in-JS olarak kaçışlı geliyor: \"  →  "
    return page.replace('\\"', '"')


def _split_codes(codes: str) -> tuple[str, ...]:
    return tuple(c.strip().upper() for c in codes.split(",") if c.strip())


def parse_companies(page: str) -> list[KapCompany]:
    seen: dict[str, KapCompany] = {}
    for m in _COMPANY_RE.finditer(_unescape(page)):
        oid = m["oid"]
        if oid not in seen:
            seen[oid] = KapCompany(oid, m["title"].strip(), _split_codes(m["codes"]), m["city"] or None)
    return list(seen.values())


def parse_sectors(page: str) -> list[KapSectorMembership]:
    text = _unescape(page)
    main_by_mkk = {m["mkk"]: m for m in _MAIN_RE.finditer(text)}
    out = []
    for s in _SUB_RE.finditer(text):
        main = main_by_mkk.get(s["mkk"])
        if main is None:
            continue
        for code in _split_codes(s["codes"]):
            out.append(KapSectorMembership(
                main_name=main["name"], main_oid=main["oid"], main_no=main["no"],
                sub_name=s["name"], sub_oid=s["oid"], sub_no=s["no"], mkk_oid=s["mkk"], symbol=code,
            ))
    return out


def parse_disclosures(rows: list[dict]) -> list[KapDisclosureRow]:
    out = []
    for r in rows:
        try:
            published = datetime.strptime(r["publishDate"], "%d.%m.%Y %H:%M:%S").replace(tzinfo=TR_TZ)
            out.append(KapDisclosureRow(
                index=int(r["disclosureIndex"]),
                published_at=published,
                company_title=(r.get("kapTitle") or "").strip(),
                symbols=_split_codes(r.get("stockCodes") or ""),
                disclosure_class=r.get("disclosureClass"),
                disclosure_type=r.get("disclosureType"),
                category=r.get("disclosureCategory"),
                subject=r.get("subject"),
                summary=r.get("summary"),
                attachment_count=int(r.get("attachmentCount") or 0),
            ))
        except (KeyError, ValueError, TypeError):
            continue  # bozuk satır atlanır, diğerleri işlenir
    return out


class KapSource(HttpSource):
    code = "kap"
    min_interval = 3.0

    def companies(self) -> list[KapCompany]:
        page = self.request("GET", f"{BASE}/tr/bist-sirketler").text
        out = parse_companies(page)
        if not out:
            raise SourceError(self.code, "şirket listesi okunamadı (sayfa yapısı değişmiş olabilir)")
        return out

    def sectors(self) -> list[KapSectorMembership]:
        page = self.request("GET", f"{BASE}/tr/Sektorler").text
        out = parse_sectors(page)
        if not out:
            raise SourceError(self.code, "sektör listesi okunamadı (sayfa yapısı değişmiş olabilir)")
        return out

    def disclosures(self, start: date, end: date) -> list[KapDisclosureRow]:
        r = self.request(
            "POST",
            f"{BASE}/tr/api/disclosure/members/byCriteria",
            json={"fromDate": start.isoformat(), "toDate": end.isoformat(), "memberType": "IGS"},
        )
        try:
            rows = r.json()
        except json.JSONDecodeError as exc:
            raise SourceError(self.code, "bildirim listesi JSON değil") from exc
        if not isinstance(rows, list):
            raise SourceError(self.code, "bildirim listesi beklenen biçimde değil")
        return parse_disclosures(rows)
