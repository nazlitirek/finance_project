"""Haber ve KAP bildirimlerinin AI ile değerlendirilmesi ve haber puanı için verilerin hazırlanması.

Bir haber birden fazla şirketi ilgilendirebileceği için news.ai_analysis hisse koduna göre saklanır:
{"THYAO": {...analiz...}}. KAP bildirimi tek şirkete ait olduğu için doğrudan saklanır.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ai import client, prompts
from app.ai.schemas import NEWS_CATEGORY_TR, NewsBatch
from app.analysis import news_score
from app.analysis.common import config
from app.db.models import KapDisclosure, News, NewsStock, Stock


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _candidates(db: Session, stock: Stock, days: int) -> list[tuple[str, object]]:
    since = _now() - timedelta(days=days)
    news = db.scalars(select(News).join(NewsStock, NewsStock.news_id == News.id).where(
        NewsStock.stock_id == stock.id, News.duplicate_of_id.is_(None), News.published_at >= since)
        .order_by(desc(News.published_at))).all()
    kap = db.scalars(select(KapDisclosure).where(
        KapDisclosure.stock_id == stock.id, KapDisclosure.published_at >= since)
        .order_by(desc(KapDisclosure.published_at))).all()
    out = [("news", n) for n in news] + [("kap", k) for k in kap]
    out.sort(key=lambda x: x[1].published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


def _analysis_of(kind: str, row, symbol: str) -> dict | None:
    if kind == "kap":
        return row.ai_analysis
    return (row.ai_analysis or {}).get(symbol)


def pending(db: Session, stock: Stock) -> list[tuple[str, object]]:
    cfg = config()["ai"]
    items = [x for x in _candidates(db, stock, cfg["news_lookback_days"]) if _analysis_of(*x, stock.symbol) is None]
    return items[: cfg["max_news_items"]]


def _ref(kind: str, row) -> str:
    return f"{'K' if kind == 'kap' else 'N'}{row.id}"


def analyze_pending(db: Session, stock: Stock) -> dict:
    """Henüz değerlendirilmemiş haberleri tek istekte Claude'a gönderir, sonuçları saklar."""
    items = pending(db, stock)
    if not items:
        return {"analyzed": 0, "message": "Değerlendirilecek yeni haber yok."}
    by_ref = {_ref(k, r): (k, r) for k, r in items}
    payload = [{
        "ref": ref, "kind": k,
        "source": "KAP" if k == "kap" else (r.publisher or "bilinmiyor"),
        "published": r.published_at.isoformat() if r.published_at else "bilinmiyor",
        "title": (r.subject or r.company_title) if k == "kap" else r.title,
        "summary": r.summary,
    } for ref, (k, r) in by_ref.items()]
    company = {"name": stock.name, "symbol": stock.symbol, "sector": stock.sector.name if stock.sector else None}
    batch, meta = client.structured(prompts.NEWS_SYSTEM, prompts.news_user_message(company, payload), NewsBatch,
                                    effort=config()["ai"]["news_effort"], max_tokens=16000)
    stored, injections = 0, 0
    for a in batch.items:
        if a.ref not in by_ref:
            continue  # AI'nin uydurduğu kimlikler yok sayılır
        kind, row = by_ref[a.ref]
        data = a.model_dump()
        data["model"] = meta.model
        data["analyzed_at"] = _now().isoformat()
        if a.duplicate_of not in by_ref:
            data["duplicate_of"] = None
        injections += int(a.injection_detected)
        if kind == "kap":
            row.ai_analysis = data
        else:
            row.ai_analysis = {**(row.ai_analysis or {}), stock.symbol: data}
        row.ai_analyzed_at = _now()
        row.category = a.category
        stored += 1
    db.flush()
    return {"analyzed": stored, "requested": len(items), "injections_detected": injections, "ai": meta.to_dict()}


def scored_items(db: Session, stock: Stock) -> tuple[list[news_score.ScoredItem], list[dict], int]:
    """Puan için değerlendirilmiş öğeler, rapor için okunur liste ve bekleyen sayısı."""
    cfg = config()["news"]
    items, readable, waiting = [], [], 0
    for kind, row in _candidates(db, stock, cfg["window_days"]):
        a = _analysis_of(kind, row, stock.symbol)
        if a is None:
            waiting += 1
            continue
        tier = news_score.source_tier(kind, None if kind == "kap" else row.publisher)
        items.append(news_score.ScoredItem(
            ref=_ref(kind, row), published_at=row.published_at, source_tier=tier, relevance=a["relevance"],
            direction=a["direction"], importance=a["importance"], duplicate=bool(a.get("duplicate_of"))))
        if a["relevance"] != "unrelated":
            readable.append({
                "ref": _ref(kind, row), "kind": kind, "source": "KAP" if kind == "kap" else row.publisher,
                "source_reliability": tier, "published_at": row.published_at.isoformat() if row.published_at else None,
                "event_date": a.get("event_date"), "title": prompts.clean_untrusted(
                    (row.subject or row.company_title) if kind == "kap" else row.title, 300),
                "category": NEWS_CATEGORY_TR.get(a["category"], a["category"]), "summary": a["summary"],
                "direction": a["direction"], "importance": a["importance"], "horizon": a["horizon"],
                "significance": a["significance"], "positive_effects": a["positive_effects"],
                "negative_effects": a["negative_effects"], "url": row.url,
            })
    return items, readable, waiting


def module(db: Session, stock: Stock):
    items, readable, waiting = scored_items(db, stock)
    res = news_score.analyze(items, len(items), waiting, _now().date().isoformat())
    res.extra["items"] = readable[:30]
    return res
