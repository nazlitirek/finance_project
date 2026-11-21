"""Haber RSS akışları. Sadece başlık, kısa özet ve bağlantı saklanır (tam metin saklanmaz).

Haber metinleri güvenilmeyen veridir: AI katmanına talimat olarak verilmez.
"""

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from app.core.text import normalize_search
from app.sources.base import HttpSource, SourceError

FEEDS: dict[str, str] = {
    "Anadolu Ajansı": "https://www.aa.com.tr/tr/rss/default?cat=ekonomi",
    "Bloomberg HT": "https://www.bloomberght.com/rss",
    "Dünya": "https://www.dunya.com/rss",
    "Ekonomim": "https://www.ekonomim.com/export/rss",
}


def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=tr&gl=TR&ceid=TR:tr"


@dataclass(frozen=True)
class NewsItem:
    url: str
    title: str
    summary: str | None
    publisher: str
    published_at: datetime | None

    @property
    def content_hash(self) -> str:
        return title_hash(self.title)


_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_GOOGLE_SUFFIX = re.compile(r"\s+-\s+[^-]{2,60}$")  # Google News başlık sonundaki " - Yayıncı"


def clean_text(raw: str | None, limit: int = 600) -> str | None:
    if not raw:
        return None
    text = _SPACE.sub(" ", html.unescape(_TAG.sub(" ", html.unescape(raw)))).strip()
    return text[:limit] or None


def title_hash(title: str) -> str:
    """Aynı haberin farklı sitelerdeki kopyalarını yakalamak için başlıktan özet."""
    base = normalize_search(_GOOGLE_SUFFIX.sub("", title))
    base = re.sub(r"[^a-z0-9 ]", "", base)
    return hashlib.sha256(base.encode()).hexdigest()


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(raw.strip())
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_feed(xml_text: str, publisher: str) -> list[NewsItem]:
    try:
        root = ET.fromstring(xml_text.lstrip("﻿").strip())
    except ET.ParseError as exc:
        raise SourceError("rss", f"{publisher}: XML okunamadı") from exc
    out = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        title = clean_text(item.findtext("title"), 600)
        if not link or not title:
            continue
        src = item.find("source")
        pub = (src.text.strip() if src is not None and src.text else publisher)
        out.append(NewsItem(
            url=link[:1000], title=title, summary=clean_text(item.findtext("description")),
            publisher=pub[:200], published_at=_parse_date(item.findtext("pubDate")),
        ))
    return out


class RssSource(HttpSource):
    code = "rss"
    min_interval = 1.0

    def fetch(self, url: str, publisher: str) -> list[NewsItem]:
        return parse_feed(self.request("GET", url).text, publisher)
