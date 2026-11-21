"""Haber ve KAP puanı: AI'nin her haber için verdiği nitel etiketlerden (yön, önem, ilgi) matematiksel puan.

puan = 50 + 50 × Σ(ağırlık × yön) / Σ(ağırlık)
ağırlık = önem × ilgi × kaynak güvenilirliği × 0.5^(yaş / yarı ömür)

- Normalize edilmiş ortalama olduğu için haber SAYISI tek başına puanı yükseltmez veya düşürmez.
- Kopya haberler ve ilgisiz haberler hesaba girmez.
- Kaynak güvenilirliği AI'den değil, kaynağın türünden gelir (KAP resmî).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from app.analysis.common import ModuleResult, config

MEANING = ("0-100: 50 nötr. Üstü haber akışının ağırlıkla olumlu, altı olumsuz olduğunu gösterir. "
           "Haber sayısı tek başına puanı etkilemez.")
MAJOR_PUBLISHERS = {"Anadolu Ajansı", "Bloomberg HT", "Dünya", "Ekonomim"}


@dataclass
class ScoredItem:
    ref: str
    published_at: datetime | None
    source_tier: str  # official / major / other
    relevance: str
    direction: str
    importance: str
    duplicate: bool = False


def source_tier(kind: str, publisher: str | None) -> str:
    if kind == "kap":
        return "official"
    return "major" if publisher in MAJOR_PUBLISHERS else "other"


def item_weight(it: ScoredItem, now: datetime, cfg: dict) -> float:
    if it.duplicate:
        return 0.0
    age = max(0.0, (now - it.published_at).total_seconds() / 86400) if it.published_at else cfg["window_days"]
    if age > cfg["window_days"]:
        return 0.0
    decay = 0.5 ** (age / cfg["half_life_days"])
    return (cfg["importance"][it.importance] * cfg["relevance"][it.relevance]
            * cfg["source_reliability"][it.source_tier] * decay)


def score(items: list[ScoredItem], now: datetime | None = None) -> tuple[float | None, float, dict]:
    cfg = config()["news"]
    now = now or datetime.now(timezone.utc)
    total_w = signed = 0.0
    counts = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
    used = 0
    for it in items:
        w = item_weight(it, now, cfg)
        if w <= 0:
            continue
        used += 1
        counts[it.direction] += 1
        total_w += w
        signed += w * cfg["direction"][it.direction]
    if total_w == 0:
        return None, 0.0, {"used_items": 0, "directions": counts}
    s = 50 + 50 * signed / total_w
    reliability = min(1.0, total_w / cfg["full_reliability_weight"])
    return s, reliability, {"used_items": used, "total_weight": round(total_w, 3), "directions": counts}


def analyze(items: list[ScoredItem], analyzed_count: int, pending_count: int, as_of: str | None) -> ModuleResult:
    s, rel, details = score(items)
    notes = ["Yön, önem ve ilgi etiketleri AI tarafından verilir; puan bu etiketlerden formülle hesaplanır.",
             "Kaynak güvenilirliği: KAP resmî (1.0), büyük yayın kuruluşları (0.8), diğer (0.5)."]
    if pending_count:
        notes.append(f"{pending_count} haber/bildirim henüz AI ile değerlendirilmedi; puana katılmadı.")
    if s is None:
        notes.append("Son dönemde şirketle ilgili değerlendirilmiş haber yok.")
    return ModuleResult("news", s, rel, as_of, components={}, notes=notes, meaning=MEANING,
                        extra={**details, "analyzed_items": analyzed_count})
