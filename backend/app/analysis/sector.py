"""Sektör ve rakip karşılaştırması. Sadece aynı finansal döneme ait veriler karşılaştırılır."""

import statistics

from app.analysis.common import ModuleResult, config, mean
from app.analysis.valuation import percentile_score

# (kod, ad, yüksek değer iyi mi)
CRITERIA = [
    ("pe", "F/K", False), ("pb", "PD/DD", False), ("ev_ebitda", "FD/FAVÖK", False), ("roe", "ROE", True),
    ("net_margin", "Net kâr marjı", True), ("liabilities_to_equity", "Borç / Özkaynak", False),
    ("revenue_growth", "Gelir büyümesi (12 ay, yıllık)", True), ("ebitda_margin", "FAVÖK marjı", True),
    ("ocf_margin", "İşletme nakit akışı / Hasılat", True),
]
MEANING = "0-100: yüksek puan, şirketin aynı dönemdeki sektör şirketlerine göre daha iyi konumda olduğunu gösterir."


def analyze(target: dict, peers: list[dict], period: str | None, sector_name: str | None) -> ModuleResult:
    """target / peers: {"symbol", "name", "period", <kriter kodları>: değer}. Farklı dönemdeki rakipler dışarıda bırakılır."""
    cfg = config()["sector"]
    if period is None:
        return ModuleResult("sector", None, 0.0, None, notes=["Şirketin finansal tablo verisi yok."], meaning=MEANING)
    same = [p for p in peers if p.get("period") == period and p["symbol"] != target["symbol"]]
    excluded = [p["symbol"] for p in peers if p.get("period") != period and p["symbol"] != target["symbol"]]
    rows, stats, parts = [], {}, {}
    for code, name, high_good in CRITERIA:
        vals = [p.get(code) for p in same if p.get(code) is not None]
        group = vals + ([target.get(code)] if target.get(code) is not None else [])
        enough = len(vals) >= cfg["min_peers"]
        stats[code] = {
            "name": name, "higher_is_better": high_good, "peer_count": len(vals),
            "average": mean(group) if enough else None,
            "median": statistics.median(group) if enough else None,
            "company": target.get(code),
        }
        if enough:
            ps = percentile_score(target.get(code), vals, lower_is_better=not high_good)
            stats[code]["position_score"] = ps
            stats[code]["position"] = None if ps is None else ("üst çeyrek" if ps >= 75 else "alt çeyrek" if ps < 25
                                                                else "orta")
            parts[code] = ps
    for p in [target] + same:
        rows.append({"symbol": p["symbol"], "name": p.get("name"), **{c: p.get(c) for c, _, _ in CRITERIA}})
    score = mean(parts.values())
    reliability = len([v for v in parts.values() if v is not None]) / len(CRITERIA)
    notes = [f"Sektör: {sector_name or 'bilinmiyor'}. Karşılaştırma dönemi: {period}."]
    if len(same) < cfg["min_peers"]:
        notes.append(f"Aynı dönem verisi olan karşılaştırılabilir şirket sayısı {len(same)}; "
                     f"ortalama ve medyan için en az {cfg['min_peers']} gerekir. Rakiplerin verisi çekilerek artırılabilir.")
    if excluded:
        notes.append(f"Farklı finansal dönemde oldukları için dışarıda bırakılan: {', '.join(excluded[:15])}")
    return ModuleResult("sector", score, reliability, period, components=parts, notes=notes, meaning=MEANING,
                        extra={"table": rows, "stats": stats, "peer_count": len(same), "sector": sector_name})
