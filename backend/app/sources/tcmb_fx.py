"""TCMB gösterge kurları (today.xml). Resmî, kamuya açık; EVDS için yedek."""

import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.sources.base import HttpSource, SourceError

URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
CURRENCIES = ("USD", "EUR")


def parse_today(xml_text: str) -> tuple[date, dict[str, Decimal]]:
    try:
        root = ET.fromstring(xml_text.lstrip("﻿"))
    except ET.ParseError as exc:
        raise SourceError("tcmb_fx", "XML okunamadı") from exc
    day = datetime.strptime(root.attrib["Tarih"], "%d.%m.%Y").date()
    out = {}
    for cur in root.findall("Currency"):
        code = cur.attrib.get("Kod")
        if code in CURRENCIES:
            txt = (cur.findtext("ForexBuying") or "").strip()
            try:
                out[code] = Decimal(txt)
            except InvalidOperation:
                continue
    return day, out


class TcmbFxSource(HttpSource):
    code = "tcmb_fx"
    min_interval = 2.0
    timeout = 40.0

    def today(self) -> tuple[date, dict[str, Decimal]]:
        return parse_today(self.request("GET", URL).text)
