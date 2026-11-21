"""Genel puan: modül puanlarının ağırlıklı ortalaması.

- Ağırlıklar config/scoring.toml → [overall].weights
- Eksik modüller (veri yok / henüz yok) genel puanı düşürmez: mevcut modüllerin ağırlıkları normalize edilir.
- Kapsama (mevcut modüllerin ağırlık payı) ayrıca gösterilir; çok düşükse sınıf verilmez.
- Risk puanında 100 = düşük risk olduğu için genel puana aynı yönde katılır (düşük risk olumlu).
"""

from app.analysis.common import DISCLAIMER, LABEL_TR, ModuleResult, config, label, weighted

MODULE_NAMES = {
    "technical": "Teknik analiz", "fundamental": "Temel analiz", "financial_health": "Finansal sağlık",
    "valuation": "Şirket değerleme", "sector": "Sektör karşılaştırması", "news": "Haber ve KAP analizi",
    "risk": "Risk analizi",
}


def overall(results: dict[str, ModuleResult | None]) -> dict:
    cfg = config()["overall"]
    weights = cfg["weights"]
    scores = {k: (r.score if r is not None else None) for k, r in results.items()}
    for k in weights:
        scores.setdefault(k, None)
    score, coverage = weighted(scores, weights)
    lab = label(score) if coverage >= cfg["min_coverage"] else None
    missing = [MODULE_NAMES[k] for k, v in scores.items() if v is None]
    return {
        "score": round(score, 1) if score is not None else None,
        "label": lab, "label_tr": LABEL_TR.get(lab) if lab else None,
        "coverage": round(coverage, 2),
        "weights": weights,
        "thresholds": {"strong_at": cfg["strong_at"], "weak_below": cfg["weak_below"],
                       "min_coverage": cfg["min_coverage"]},
        "missing_modules": missing,
        "note": ("Genel sınıf verilmedi: puanlanabilen modüllerin ağırlık payı yetersiz."
                 if score is not None and lab is None else None),
        "disclaimer": DISCLAIMER,
    }
