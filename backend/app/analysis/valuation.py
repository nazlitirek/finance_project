"""Şirket değerleme: çarpanlar ve indirgenmiş nakit akışı (DCF, 3 senaryo).

- Piyasa değeri = son gün sonu kapanış (düzeltilmemiş) × ödenmiş sermaye.
  BIST'te pay başı nominal değer genellikle 1 TL'dir; bu yüzden ödenmiş sermaye pay adedine eşit kabul edilir.
- DCF sonucu kesin hedef fiyat değildir; varsayımlara çok duyarlı bir "model değeri"dir.
- Veri yetersizse DCF hesaplanmaz ve puana katılmaz.
"""

from dataclasses import dataclass

from app.analysis.common import Metric, ModuleResult, config, div, mean, num, scale, weighted
from app.analysis.fundamental import FINANCIAL_PROFILES
from app.analysis.statements import Financials, pkey

MEANING = "0-100: yüksek puan görece ucuz değerleme (sektör/geçmiş çarpanlarına ve DCF modeline göre)."


@dataclass
class Market:
    price: float | None  # son kapanış (düzeltilmemiş)
    price_date: str | None
    shares: float | None  # ödenmiş sermaye
    risk_free: float | None  # yıllık, oran (ör. 0.36)
    risk_free_source: str | None
    beta: float | None


def market_cap(m: Market) -> float | None:
    return None if m.price is None or m.shares is None else m.price * m.shares


def net_debt(f: Financials, p) -> float | None:
    sd, ld, cash = f.raw("short_financial_debt", p), f.raw("long_financial_debt", p), f.raw("cash", p)
    if None in (sd, ld, cash):
        return None
    return sd + ld - cash - (f.raw("short_investments", p) or 0)


def multiples(f: Financials, p, mcap: float | None, profile: str) -> dict[str, float | None]:
    """Çarpanlar. Payda ≤ 0 ise (zarar, negatif özkaynak) çarpan anlamsızdır → None."""
    def pos(x):
        x = num(x)
        return x if x is not None and x > 0 else None

    eq_item = "parent_equity" if f.template == "industrial" else "equity"
    out = {
        "pe": div(mcap, pos(f.ttm("parent_net_profit", p))),
        "pb": div(mcap, pos(f.raw(eq_item, p))),
    }
    if f.template == "industrial" and profile not in FINANCIAL_PROFILES:
        nd = net_debt(f, p)
        ev = None if mcap is None or nd is None else mcap + nd + (f.raw("minority_interest", p) or 0)
        out.update({
            "ev": ev,
            "ev_ebitda": div(ev, pos(f.ebitda_ttm(p))),
            "ev_sales": div(ev, pos(f.ttm("revenue", p))),
            "p_cf": div(mcap, pos(f.ttm("operating_cash_flow", p))),
        })
    return out


MULTIPLE_INFO = {
    "pe": ("F/K", "Piyasa değeri / Ana ortaklık net kârı (12 ay)"),
    "pb": ("PD/DD", "Piyasa değeri / Ana ortaklık özkaynağı"),
    "ev_ebitda": ("FD/FAVÖK", "Firma değeri / FAVÖK (12 ay); FD = PD + Net borç + Azınlık payları"),
    "ev_sales": ("FD/Satışlar", "Firma değeri / Hasılat (12 ay)"),
    "p_cf": ("Fiyat / Nakit akışı", "Piyasa değeri / İşletme faaliyetlerinden nakit akışı (12 ay)"),
}


# ---------------------------------------------------------------- DCF

def dcf_scenario(base: dict, sc: dict, cfg: dict) -> dict:
    """Tek senaryo. base: revenue, ebitda_margin, da_pct, capex_pct, net_debt, minority, shares, wacc0.

    Serbest nakit akışı (FCFF) = (FAVÖK − Amortisman) × (1 − vergi) + Amortisman − Yatırım − İşletme sermayesi değişimi
    WACC 1. yıldaki değerinden 5. yıla doğru uzun vadeli seviyeye doğrusal iner.
    Uç değer = FCFF₅ × (1 + g) / (WACC₅ − g)
    """
    years, tax = cfg["years"], cfg["tax_rate"]
    margin = base["ebitda_margin"] + sc["margin_change"]
    wacc_start = base["wacc0"] + sc["wacc_change"]
    wacc_end = base["wacc_long"] + sc["wacc_change"]
    g_term = sc["terminal_growth"]
    rev_prev, disc, pv_sum, rows = base["revenue"], 1.0, 0.0, []
    fcf = wacc = None
    for t in range(years):
        growth = sc["revenue_growth"][t]
        rev = rev_prev * (1 + growth)
        ebitda = rev * margin
        da = rev * base["da_pct"]
        capex = rev * base["capex_pct"]
        dnwc = (rev - rev_prev) * cfg["nwc_to_revenue_change"]
        fcf = (ebitda - da) * (1 - tax) + da - capex - dnwc
        wacc = wacc_start + (wacc_end - wacc_start) * (t / (years - 1) if years > 1 else 0)
        disc *= 1 + wacc
        pv = fcf / disc
        pv_sum += pv
        rows.append({"year": t + 1, "revenue": rev, "growth": growth, "ebitda": ebitda, "fcf": fcf,
                     "wacc": wacc, "pv": pv})
        rev_prev = rev
    if wacc - g_term < 0.02:
        return {"valid": False, "reason": "Uç büyüme oranı WACC'a çok yakın veya üzerinde."}
    tv = fcf * (1 + g_term) / (wacc - g_term)
    pv_tv = tv / disc
    ev = pv_sum + pv_tv
    equity = ev - base["net_debt"] - base["minority"]
    return {
        "valid": True, "years": rows, "pv_fcf": pv_sum, "terminal_value": tv, "pv_terminal": pv_tv,
        "enterprise_value": ev, "equity_value": equity,
        "value_per_share": div(equity, base["shares"]),
        "assumptions": {"revenue_growth": sc["revenue_growth"], "ebitda_margin": margin, "tax_rate": tax,
                        "capex_pct_revenue": base["capex_pct"], "da_pct_revenue": base["da_pct"],
                        "nwc_to_revenue_change": cfg["nwc_to_revenue_change"], "wacc_start": wacc_start,
                        "wacc_end": wacc_end, "terminal_growth": g_term},
        "terminal_share": div(pv_tv, ev),
        "note": ("Model özkaynak değeri negatif: bu varsayımlarla firma değeri net borcu karşılamıyor."
                 if equity < 0 else None),
    }


def wacc_inputs(m: Market, mcap: float | None, debt: float | None, cfg: dict) -> dict | None:
    if m.risk_free is None or mcap is None or mcap <= 0:
        return None
    beta = m.beta if m.beta is not None else 1.0
    ke = m.risk_free + beta * cfg["equity_risk_premium"]
    kd = (m.risk_free + cfg["debt_spread"]) * (1 - cfg["tax_rate"])
    d = max(debt or 0.0, 0.0)
    we = mcap / (mcap + d)
    ke_long = cfg["long_term_risk_free"] + beta * cfg["equity_risk_premium"]
    kd_long = (cfg["long_term_risk_free"] + cfg["debt_spread"]) * (1 - cfg["tax_rate"])
    return {"risk_free": m.risk_free, "risk_free_source": m.risk_free_source, "beta": beta,
            "beta_source": "risk modülü (1 yıl, BIST 100)" if m.beta is not None else "varsayılan 1.0",
            "cost_of_equity": ke, "cost_of_debt_after_tax": kd, "equity_weight": we,
            "wacc0": we * ke + (1 - we) * kd, "wacc_long": we * ke_long + (1 - we) * kd_long}


def dcf(f: Financials, p, m: Market, profile: str) -> dict:
    cfg = config()["dcf"]
    if f.template != "industrial" or profile in FINANCIAL_PROFILES:
        return {"valid": False, "reason": "DCF finans kuruluşları için uygulanmaz."}
    if f.quarters_available() < cfg["min_quarters"]:
        return {"valid": False, "reason": f"En az {cfg['min_quarters']} çeyrek finansal veri gerekir."}
    rev, ebitda = f.ttm("revenue", p), f.ebitda_ttm(p)
    dep, capex = f.ttm("depreciation", p), f.ttm("capex", p)
    nd = net_debt(f, p)
    if None in (rev, ebitda, dep, capex, nd) or rev <= 0:
        return {"valid": False, "reason": "Hasılat, FAVÖK, amortisman, yatırım veya net borç verisi eksik."}
    if ebitda <= 0:
        return {"valid": False, "reason": "Son 12 ay FAVÖK negatif; DCF anlamlı değil."}
    mcap = market_cap(m)
    debt = (f.raw("short_financial_debt", p) or 0) + (f.raw("long_financial_debt", p) or 0)
    w = wacc_inputs(m, mcap, debt, cfg)
    if w is None:
        return {"valid": False, "reason": "Risksiz faiz veya piyasa değeri yok."}
    base = {"revenue": rev, "ebitda_margin": ebitda / rev, "da_pct": abs(dep) / rev, "capex_pct": abs(capex) / rev,
            "net_debt": nd, "minority": f.raw("minority_interest", p) or 0.0, "shares": m.shares,
            "wacc0": w["wacc0"], "wacc_long": w["wacc_long"]}
    scenarios = {name: dcf_scenario(base, sc, cfg) for name, sc in cfg["scenarios"].items()}
    for sc in scenarios.values():
        if sc.get("valid") and m.price:
            sc["vs_price"] = div(sc["value_per_share"], m.price) - 1 if sc["value_per_share"] is not None else None
    return {"valid": scenarios["base"].get("valid", False), "base_period": pkey(p), "inputs": base, "wacc": w,
            "scenarios": scenarios,
            "note": "Model değeri kesin hedef fiyat değildir; özellikle büyüme, marj ve WACC varsayımlarına çok duyarlıdır. "
                    "Nominal TL ile hesaplanmıştır."}


# ---------------------------------------------------------------- modül

def percentile_score(value: float | None, others: list[float], lower_is_better: bool) -> float | None:
    """Değerin karşılaştırma grubundaki yüzdelik konumu → 0-100 puan."""
    vs = [x for x in others if x is not None]
    if value is None or len(vs) < 1:
        return None
    below = sum(1 for x in vs if x < value) + 0.5 * sum(1 for x in vs if x == value)
    pct = below / len(vs)
    return (1 - pct) * 100 if lower_is_better else pct * 100


def analyze(f: Financials | None, m: Market, profile: str, peer_multiples: list[dict] | None = None,
            history: dict[str, list[float]] | None = None) -> ModuleResult:
    cfg = config()["valuation"]
    if f is None or f.latest is None:
        return ModuleResult("valuation", None, 0.0, None, notes=["Finansal tablo verisi yok."], meaning=MEANING)
    p = f.latest
    mcap = market_cap(m)
    mult = multiples(f, p, mcap, profile)
    peers = peer_multiples or []
    hist = history or {}
    metrics, parts, basis = [], [], None
    for code in ("pe", "pb", "ev_ebitda", "ev_sales", "p_cf"):
        if code not in mult:
            continue
        name, formula = MULTIPLE_INFO[code]
        val = mult[code]
        peer_vals = [x.get(code) for x in peers if x.get(code) is not None]
        med = sorted(peer_vals)[len(peer_vals) // 2] if peer_vals else None
        metrics.append(Metric(code, name, val, formula=formula, unit="x", sector_median=med,
                              comment=None if val is not None else "Payda sıfır veya negatif (zarar / negatif özkaynak)"))
        if code in ("pe", "pb", "ev_ebitda"):
            if len(peer_vals) >= cfg["min_peers"]:
                parts.append(percentile_score(val, peer_vals, lower_is_better=True))
                basis = "sector"
            elif len(hist.get(code, [])) >= 4:
                parts.append(percentile_score(val, hist[code], lower_is_better=True))
                basis = basis or "own_history"
    mult_score = mean(parts)
    d = dcf(f, p, m, profile)
    dcf_score = scale(d["scenarios"]["base"].get("vs_price"), cfg["dcf_upside"]) if d.get("valid") else None
    comps = {"multiples": mult_score, "dcf": dcf_score}
    score, coverage = weighted(comps, cfg["weights"])
    notes = ["Piyasa değeri = son gün sonu kapanış × ödenmiş sermaye (pay başı nominal 1 TL varsayımı).",
             "Çarpanlarda düşük değer görece ucuzluğu gösterir; sektör ve büyüme farkları dikkate alınmalıdır."]
    if basis == "own_history":
        notes.append(f"Yeterli sektör karşılaştırması yok (en az {cfg['min_peers']} şirket); "
                     "çarpanlar şirketin kendi geçmişiyle karşılaştırıldı.")
    elif basis is None:
        notes.append("Çarpanlar için ne yeterli sektör verisi ne de yeterli geçmiş var; çarpan puanı hesaplanmadı.")
    if not d.get("valid"):
        notes.append(f"DCF hesaplanmadı: {d.get('reason')}")
    return ModuleResult("valuation", score, coverage, pkey(p), components=comps, metrics=metrics, notes=notes,
                        meaning=MEANING,
                        extra={"market_cap": mcap, "price": m.price, "price_date": m.price_date, "shares": m.shares,
                               "multiples_basis": basis, "dcf": d,
                               "ev": mult.get("ev")})
