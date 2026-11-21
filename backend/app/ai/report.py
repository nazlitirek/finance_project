"""AI destekli genel analiz raporu.

Akış:
1. Yeni haberler AI ile değerlendirilir (hata olursa rapor yine üretilir, not düşülür)
2. Bütün modüller hesaplanır (saf Python) → puanlar
3. Hesaplanan sonuçlardan kısaltılmış bir "girdi görüntüsü" (snapshot) hazırlanır
4. Rapor kaydı + modül puanları veritabanına yazılır (AI çağrısından ÖNCE; AI hata verse bile puanlar kalır)
5. Claude raporu yazar; çıktı şemayla doğrulanır, yasaklı ifadeler denetlenir
6. Rapor, girdi görüntüsüyle birlikte değişmeden saklanır; eski raporlar yeniden hesaplanmaz
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai import client, news, prompts
from app.ai.schemas import AiReport, Section
from app.analysis import service as analysis
from app.analysis.common import config
from app.db.models import AnalysisReport, AnalysisScore, Stock

log = logging.getLogger(__name__)

SNAPSHOT_EXTRA = {
    "technical": ("history_days",),
    "fundamental": ("growth", "statement_items", "profile", "template"),
    "financial_health": ("profile",),
    "valuation": ("market_cap", "price", "price_date", "multiples_basis", "dcf"),
    "sector": ("stats", "peer_count", "sector"),
    "risk": ("window_start", "window_end", "observations", "risk_free", "risk_free_source"),
    "news": ("used_items", "directions", "analyzed_items"),
}


def _round(x):
    if isinstance(x, float):
        return float(f"{x:.4g}")
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    return x


def _dcf_summary(d: dict) -> dict:
    if not d or not d.get("valid"):
        return {"valid": False, "reason": (d or {}).get("reason")}
    return {
        "valid": True, "base_period": d.get("base_period"), "note": d.get("note"),
        "wacc": {k: v for k, v in d["wacc"].items()},
        "scenarios": {n: {k: s.get(k) for k in ("valid", "value_per_share", "vs_price", "terminal_share",
                                                 "assumptions", "note")} for n, s in d["scenarios"].items()},
    }


def build_snapshot(result: dict, news_items: list[dict]) -> dict:
    """AI'ye verilecek, hesaplanmış sonuçların kısaltılmış kopyası (formüller ve ham satırlar hariç)."""
    mods = {}
    for name, m in result["modules"].items():
        extra = {k: m["extra"].get(k) for k in SNAPSHOT_EXTRA.get(name, ()) if k in m["extra"]}
        if "dcf" in extra:
            extra["dcf"] = _dcf_summary(extra["dcf"])
        mods[name] = {
            "score": m["score"], "label": m["label"], "reliability": m["reliability"], "meaning": m["meaning"],
            "as_of": m["as_of"], "components": m["components"], "assessments": m["assessments"], "notes": m["notes"],
            "metrics": [{k: x[k] for k in ("code", "name", "value", "previous", "previous_label", "unit", "signal",
                                           "comment", "sector_median") if x.get(k) is not None}
                        for x in m["metrics"]],
            "extra": extra,
        }
    return _round({
        "company": {"symbol": result["symbol"], "name": result["name"], "sector": result["sector"],
                    "analysis_profile": result["profile"]},
        "price": {"last_close": result["price"], "date": result["price_date"], "freshness": "gün sonu"},
        "financial_period": result["financial_period"],
        "overall": {k: result["overall"][k] for k in ("score", "label", "label_tr", "coverage", "missing_modules",
                                                      "weights")},
        "modules": mods,
        "horizon_inputs": {
            "short_term": ["technical (trend, momentum, hacim, oynaklık, destek/direnç)"],
            "medium_term": ["fundamental (çeyreklik büyüme)", "valuation", "sector", "news"],
            "long_term": ["financial_health", "fundamental (kârlılık, nakit)", "risk (borçluluk, kâr istikrarı)"],
        },
        "news_items": news_items,
    })


_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_PARAMS = {9.0, 12.0, 14.0, 20.0, 21.0, 50.0, 100.0, 200.0}  # gösterge parametreleri (RSI 14, SMA 50 ...)


def unverified_evidence(r: AiReport, snapshot: dict) -> list[str]:
    """Raporun 'evidence' alanlarındaki sayıların girdi verisinde gerçekten bulunduğunu denetler.
    Girdide karşılığı olmayan (uydurulmuş olabilecek) ifadeleri döndürür. Oranlar yüzde olarak da kabul edilir."""
    known: list[float] = []

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            known.append(float(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(snapshot)

    def found(v: float) -> bool:
        for s in known:
            for c in (s, s * 100):
                if c == v or (c and abs(v - c) / abs(c) < 0.006):
                    return True
        return False

    out = []
    for name in AiReport.model_fields:
        sec = getattr(r, name)
        if not isinstance(sec, Section):
            continue
        for e in sec.evidence:
            core = re.sub(r"\([^)]*\)", "", e)  # parantez içindeki tarih/dönem
            nums = [float(m) for m in _NUM.findall(core.replace(",", ""))]
            if any(n not in _PARAMS and not found(n) for n in nums):
                out.append(f"{name}: {e}")
    return out


def _texts(r: AiReport) -> list[str]:
    out = []
    for name in AiReport.model_fields:
        v = getattr(r, name)
        if isinstance(v, list):
            out.extend(v)
        else:
            out.append(v.text)
    return out


def generate(db: Session, stock: Stock) -> AnalysisReport:
    cfg = config()["ai"]
    news_step: dict = {}
    if client.is_configured():
        try:
            news_step = news.analyze_pending(db, stock)
            db.commit()
        except client.AIError as exc:
            db.rollback()
            news_step = {"error": exc.message}
            log.warning("Haber analizi başarısız: %s", exc.message)

    result = analysis.analyze_stock(db, stock)
    _, news_items, _ = news.scored_items(db, stock)
    snapshot = build_snapshot(result, news_items[:20])
    ov = result["overall"]

    rep = AnalysisReport(
        stock_id=stock.id, status="pending", model=None,
        overall_score=ov["score"], overall_label=ov["label"], data_coverage=ov["coverage"],
        input_snapshot={"snapshot": snapshot, "analysis": result},
        data_as_of={"price_date": result["price_date"], "financial_period": result["financial_period"],
                    "modules": {k: m["as_of"] for k, m in result["modules"].items()},
                    "generated_at": datetime.now(timezone.utc).isoformat()},
        sources=["İş Yatırım (fiyat, finansal tablolar)", "KAP (bildirimler, şirket ve sektör listesi)",
                 "TCMB EVDS (risksiz faiz)", "Haber RSS akışları"],
    )
    db.add(rep)
    db.flush()
    for name, m in result["modules"].items():
        db.add(AnalysisScore(report_id=rep.id, module=name, score=m["score"], reliability=m["reliability"],
                             label=m["label"], details={"components": m["components"], "meaning": m["meaning"],
                                                        "notes": m["notes"]}))
    db.commit()

    try:
        user = prompts.report_user_message(snapshot)
        parsed, meta = client.structured(prompts.REPORT_SYSTEM, user, AiReport, effort=cfg["report_effort"])
        violations = prompts.policy_violations(_texts(parsed))
        attempts = [meta.to_dict()]
        if violations:
            log.info("Rapor yasaklı ifade içeriyor, bir kez yeniden deneniyor: %s", violations)
            user += ("\n\nÖnceki taslakta kesin alım/satım talimatı veya hedef fiyat ifadesi vardı "
                     f"({'; '.join(violations[:5])}). Bu ifadeleri kullanmadan yeniden yaz.")
            parsed, meta = client.structured(prompts.REPORT_SYSTEM, user, AiReport, effort=cfg["report_effort"])
            attempts.append(meta.to_dict())
            violations = prompts.policy_violations(_texts(parsed))
        rep.report = {**parsed.model_dump(), "policy_warnings": violations, "news_step": news_step,
                      "unverified_evidence": unverified_evidence(parsed, snapshot), "ai": attempts}
        rep.model = meta.model
        rep.status = "completed"
    except client.AIError as exc:
        rep.status = "failed"
        rep.error = exc.message
        rep.report = {"news_step": news_step}
    db.commit()
    return rep


def to_dict(rep: AnalysisReport, symbol: str | None = None) -> dict:
    return {
        "id": rep.id, "symbol": symbol, "created_at": rep.created_at, "status": rep.status, "model": rep.model,
        "overall_score": float(rep.overall_score) if rep.overall_score is not None else None,
        "overall_label": rep.overall_label,
        "data_coverage": float(rep.data_coverage) if rep.data_coverage is not None else None,
        "data_as_of": rep.data_as_of, "sources": rep.sources, "error": rep.error, "report": rep.report,
        "scores": [{"module": s.module, "score": float(s.score) if s.score is not None else None,
                    "reliability": float(s.reliability), "label": s.label, "details": s.details}
                   for s in rep.scores],
        "analysis": (rep.input_snapshot or {}).get("analysis"),
        "note": "Bu rapor oluşturulduğu tarihteki verilerle hazırlanmıştır; yeniden hesaplanmaz.",
    }
