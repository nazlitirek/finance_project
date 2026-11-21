"""Temel analiz ve finansal sağlık. Bütün oranlar belgelenmiş formüllerle, saf fonksiyonlarla hesaplanır.

Önemli not (TMS 29): Kaynak her dönemi kendi raporlandığı tarihin satın alma gücüyle verir.
Yıllık / çeyreklik büyüme bu nominal değerlerle hesaplanır; enflasyon dönemlerinde büyümeyi
olduğundan yüksek gösterebilir. Oranlar (marj, ROE vb.) aynı dönem içindeki kalemlerden
hesaplandığı için bu etkiden daha az etkilenir.
"""

from app.analysis.common import Metric, ModuleResult, config, div, mean, scale, weighted
from app.analysis.statements import Financials, pkey

INFLATION_NOTE = ("Büyüme oranları nominal TL'dir. TMS 29 uygulanan dönemlerde her rapor kendi tarihinin "
                  "satın alma gücüyle verildiği için büyüme enflasyon etkisiyle yüksek görünebilir.")
FINANCIAL_PROFILES = {"bank", "insurance", "leasing_factoring", "other_financial"}


def growth(cur, prev) -> float | None:
    """(cur − prev) / |prev|. Önceki değer 0 veya yoksa None. Zarardan kâra geçişte yön doğru kalır."""
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev)


def _sig(v, good_high=True):
    if v is None:
        return None
    return ("positive" if v > 0 else "negative" if v < 0 else "neutral") if good_high else \
        ("positive" if v < 0 else "negative" if v > 0 else "neutral")


# ---------------------------------------------------------------- büyüme

GROWTH_ITEMS = [("revenue", "Hasılat"), ("gross_profit", "Brüt kâr"), ("ebitda", "FAVÖK"),
                ("parent_net_profit", "Net kâr (ana ortaklık)"), ("operating_cash_flow", "İşletme nakit akışı")]
FIN_GROWTH_ITEMS = [("net_interest_income", "Net faiz geliri"), ("parent_net_profit", "Net kâr"),
                    ("earned_premiums", "Kazanılmış primler")]


def _value(f: Financials, item: str, p, kind: str):
    if item == "ebitda":
        if kind == "ttm":
            return f.ebitda_ttm(p)
        if kind == "annual":
            return f.ebitda_ttm(p) if p[1] == 12 else None
        op, dep = f.quarter("operating_profit", p), f.quarter("depreciation", p)
        return None if op is None or dep is None else op + abs(dep)
    if kind == "ttm":
        return f.ttm(item, p)
    if kind == "annual":
        return f.raw(item, p) if p[1] == 12 else None
    return f.quarter(item, p)


def growth_table(f: Financials) -> list[dict]:
    p = f.latest
    last_fy = next((x for x in f.periods if x[1] == 12), None)
    items = GROWTH_ITEMS if f.template == "industrial" else [x for x in FIN_GROWTH_ITEMS if f.code(x[0])]
    out = []
    for item, name in items:
        row = {"item": item, "name": name}
        row["ttm_yoy"] = growth(_value(f, item, p, "ttm"), _value(f, item, f.year_ago(p), "ttm"))
        row["annual"] = growth(_value(f, item, last_fy, "annual"), _value(f, item, f.year_ago(last_fy), "annual")) \
            if last_fy else None
        row["annual_period"] = pkey(last_fy) if last_fy else None
        row["quarter_yoy"] = growth(_value(f, item, p, "q"), _value(f, item, f.year_ago(p), "q"))
        row["quarter_qoq"] = growth(_value(f, item, p, "q"), _value(f, item, f.prev_quarter(p), "q"))
        out.append(row)
    eq = "parent_equity" if f.template == "industrial" else "equity"
    out.append({"item": "equity", "name": "Özkaynak", "ttm_yoy": growth(f.raw(eq, p), f.raw(eq, f.year_ago(p))),
                "annual": None, "annual_period": None, "quarter_yoy": None,
                "quarter_qoq": growth(f.raw(eq, p), f.raw(eq, f.prev_quarter(p)))})
    return out


# ---------------------------------------------------------------- oranlar

def ratios(f: Financials, p, profile: str) -> list[Metric]:
    """Dönem p için finansal sağlık oranları. Önceki değer: bir yıl önceki aynı dönem."""
    if f.template == "financial" or profile in FINANCIAL_PROFILES:
        return _financial_ratios(f, p, profile)
    prev = f.year_ago(p)
    out = []

    def m(code, name, fn, formula, unit="ratio", good_high=True, comment=None):
        v, pv = fn(p), fn(prev)
        out.append(Metric(code, name, v, pv, formula=formula, unit=unit,
                          signal=_sig(None if v is None or pv is None else v - pv, good_high),
                          previous_label=pkey(prev), comment=comment))

    R, T = f.raw, f.ttm
    fin_debt = lambda q: (None if R("short_financial_debt", q) is None or R("long_financial_debt", q) is None
                          else R("short_financial_debt", q) + R("long_financial_debt", q))
    liabilities = lambda q: (None if R("short_liabilities", q) is None or R("long_liabilities", q) is None
                             else R("short_liabilities", q) + R("long_liabilities", q))
    liquid = lambda q: (None if R("cash", q) is None else R("cash", q) + (R("short_investments", q) or 0))

    # Likidite
    m("current_ratio", "Cari oran", lambda q: div(R("current_assets", q), R("short_liabilities", q)),
      "Dönen varlıklar / Kısa vadeli yükümlülükler")
    m("quick_ratio", "Asit-test oranı",
      lambda q: div(None if R("current_assets", q) is None else R("current_assets", q) - (R("inventories", q) or 0),
                    R("short_liabilities", q)), "(Dönen varlıklar − Stoklar) / Kısa vadeli yükümlülükler")
    m("cash_ratio", "Nakit oranı", lambda q: div(liquid(q), R("short_liabilities", q)),
      "(Nakit + Kısa vadeli finansal yatırımlar) / Kısa vadeli yükümlülükler")
    # Borçluluk
    m("liabilities_to_equity", "Toplam borç / Özkaynak", lambda q: div(liabilities(q), R("equity", q)),
      "(Kısa + Uzun vadeli yükümlülükler) / Toplam özkaynak", good_high=False)
    m("net_debt_to_ebitda", "Net borç / FAVÖK",
      lambda q: div(None if fin_debt(q) is None or liquid(q) is None else fin_debt(q) - liquid(q), f.ebitda_ttm(q)),
      "(Finansal borçlar − Nakit − Kısa vadeli fin. yatırımlar) / FAVÖK (son 12 ay)", good_high=False,
      comment="FAVÖK = Faaliyet kârı + Amortisman")
    m("liabilities_to_assets", "Toplam borç / Toplam varlık", lambda q: div(liabilities(q), R("total_assets", q)),
      "(Kısa + Uzun vadeli yükümlülükler) / Toplam varlıklar", good_high=False)
    m("interest_coverage", "Finansman gideri karşılama",
      lambda q: div(T("operating_profit", q), None if T("finance_expense", q) is None else abs(T("finance_expense", q))),
      "Faaliyet kârı (12 ay) / |Finansal giderler (12 ay)|", unit="x",
      comment="Finansal giderler kur farkı zararlarını da içerebilir.")
    # Kârlılık
    m("roe", "Özkaynak kârlılığı (ROE)", lambda q: div(T("parent_net_profit", q), f.avg("parent_equity", q)),
      "Ana ortaklık net kârı (12 ay) / Ortalama ana ortaklık özkaynağı", unit="%")
    m("roa", "Aktif kârlılığı (ROA)", lambda q: div(T("net_profit", q), f.avg("total_assets", q)),
      "Net kâr (12 ay) / Ortalama toplam varlıklar", unit="%")
    m("gross_margin", "Brüt kâr marjı", lambda q: div(T("gross_profit", q), T("revenue", q)),
      "Brüt kâr / Hasılat (12 ay)", unit="%")
    m("operating_margin", "Faaliyet kâr marjı", lambda q: div(T("operating_profit", q), T("revenue", q)),
      "Faaliyet kârı / Hasılat (12 ay)", unit="%")
    m("ebitda_margin", "FAVÖK marjı", lambda q: div(f.ebitda_ttm(q), T("revenue", q)),
      "FAVÖK / Hasılat (12 ay)", unit="%")
    m("net_margin", "Net kâr marjı", lambda q: div(T("net_profit", q), T("revenue", q)),
      "Net kâr / Hasılat (12 ay)", unit="%")
    # Verimlilik
    m("asset_turnover", "Aktif devir hızı", lambda q: div(T("revenue", q), f.avg("total_assets", q)),
      "Hasılat (12 ay) / Ortalama toplam varlıklar", unit="x")
    m("receivable_days", "Alacak tahsil süresi",
      lambda q: None if div(R("trade_receivables", q), T("revenue", q)) is None else
      div(R("trade_receivables", q), T("revenue", q)) * 365,
      "Ticari alacaklar / Hasılat (12 ay) × 365", unit="gün", good_high=False)
    m("inventory_turnover", "Stok devir hızı",
      lambda q: div(None if T("cogs", q) is None else abs(T("cogs", q)), f.avg("inventories", q)),
      "|Satışların maliyeti (12 ay)| / Ortalama stoklar", unit="x")
    for x in out:
        x.inputs = {"period": pkey(p)}
    return out


def _financial_ratios(f: Financials, p, profile: str) -> list[Metric]:
    prev = f.year_ago(p)
    out = []

    def m(code, name, fn, formula, unit="ratio", good_high=True):
        v, pv = fn(p), fn(prev)
        out.append(Metric(code, name, v, pv, formula=formula, unit=unit, previous_label=pkey(prev),
                          signal=_sig(None if v is None or pv is None else v - pv, good_high)))

    R, T = f.raw, f.ttm
    m("roe", "Özkaynak kârlılığı (ROE)", lambda q: div(T("net_profit", q), f.avg("equity", q)),
      "Net kâr (12 ay) / Ortalama özkaynak", "%")
    m("roa", "Aktif kârlılığı (ROA)", lambda q: div(T("net_profit", q), f.avg("total_assets", q)),
      "Net kâr (12 ay) / Ortalama toplam aktif", "%")
    m("equity_to_assets", "Özkaynak / Aktif", lambda q: div(R("equity", q), R("total_assets", q)),
      "Özkaynak / Toplam aktif")
    if profile == "bank":
        m("loans_to_deposits", "Kredi / Mevduat", lambda q: div(R("loans", q), R("deposits", q)),
          "Krediler / Mevduat", good_high=False)
        m("nii_share", "Net faiz geliri payı", lambda q: div(T("net_interest_income", q), T("operating_income", q)),
          "Net faiz geliri / Faaliyet gelirleri toplamı (12 ay)", "%")
        m("cost_of_risk", "Karşılık / Kredi",
          lambda q: div(None if T("loan_provisions", q) is None else abs(T("loan_provisions", q)), f.avg("loans", q)),
          "Kredi değer düşüş karşılığı (12 ay) / Ortalama krediler", "%", good_high=False)
    for code, name in [("current_ratio", "Cari oran"), ("net_debt_to_ebitda", "Net borç / FAVÖK"),
                       ("gross_margin", "Brüt kâr marjı"), ("inventory_turnover", "Stok devir hızı")]:
        out.append(Metric(code, name, None, comment="Finans kuruluşları için uygulanamaz."))
    return out


def _metric(ms: list[Metric], code: str) -> float | None:
    return next((x.value for x in ms if x.code == code), None)


# ---------------------------------------------------------------- modüller

def _base_notes(f: Financials, p) -> list[str]:
    notes = ["Kaynak: İş Yatırım finansal tabloları. Tablonun konsolide mi solo mu olduğu kaynakta belirtilmiyor."]
    infl = f.inflation.get(p)
    if infl is True:
        notes.append("Son dönem TMS 29 (enflasyon muhasebesi) kapsamında.")
    elif infl is None:
        notes.append("Finans kuruluşu: TMS 29 uygulaması teyit edilmedi.")
    return notes


def analyze_fundamental(f: Financials | None, profile: str) -> ModuleResult:
    meaning = "0-100: yüksek puan güçlü kârlılık, büyüme ve nakit üretimi."
    if f is None or f.latest is None:
        return ModuleResult("fundamental", None, 0.0, None, notes=["Finansal tablo verisi yok."], meaning=meaning)
    cfg = config()["fundamental"]
    p = f.latest
    g = growth_table(f)
    gm = {r["item"]: r for r in g}
    ms = ratios(f, p, profile)
    financial = f.template == "financial" or profile in FINANCIAL_PROFILES

    if financial:
        profitability = mean([scale(_metric(ms, "roe"), cfg["roe"])])
        cash = None  # finans kuruluşlarında nakit akış tablosu yok / anlamlı değil
        perf = None
    else:
        profitability = mean([scale(_metric(ms, "net_margin"), cfg["net_margin"]),
                              scale(_metric(ms, "ebitda_margin"), cfg["ebitda_margin"]),
                              scale(_metric(ms, "roe"), cfg["roe"])])
        ocf, np_ = f.ttm("operating_cash_flow", p), f.ttm("net_profit", p)
        fcf = f.ttm("free_cash_flow", p)
        ocf_np = div(ocf, np_) if np_ and np_ > 0 else None
        cash = mean([scale(ocf_np, cfg["ocf_to_net_profit"]),
                     scale(div(fcf, f.ttm("revenue", p)), cfg["fcf_margin"])])
        om_now = _metric(ms, "operating_margin")
        om_prev = next((x.previous for x in ms if x.code == "operating_margin"), None)
        perf = None if om_now is None or om_prev is None else (100.0 if om_now > om_prev else 0.0 if om_now < om_prev
                                                               else 50.0)
    rev_key = "revenue" if not financial else ("net_interest_income" if profile == "bank" else "earned_premiums")
    growth_score = mean([scale(gm.get(rev_key, {}).get("ttm_yoy"), cfg["revenue_growth"]),
                         scale(gm["parent_net_profit"]["ttm_yoy"], cfg["profit_growth"])])
    components = {"profitability": profitability, "growth": growth_score, "cash": cash, "performance": perf}
    score, coverage = weighted(components, cfg["weights"])
    q = f.quarters_available()
    reliability = coverage * min(1.0, q / 8)
    notes = _base_notes(f, p) + [INFLATION_NOTE]
    if financial:
        notes.append("Finans kuruluşu: kârlılık ve büyüme sektöre uygun kalemlerle değerlendirildi; "
                     "nakit akış ölçütleri uygulanmadı.")
    if q < 8:
        notes.append(f"Sadece {q} çeyrek veri var; son 12 ay ve yıllık karşılaştırmalar eksik olabilir.")
    return ModuleResult("fundamental", score, reliability, pkey(p), components=components,
                        metrics=[x for x in ms if x.code in ("roe", "roa", "gross_margin", "operating_margin",
                                                             "ebitda_margin", "net_margin")],
                        notes=notes, meaning=meaning,
                        extra={"growth": g, "template": f.template, "profile": profile,
                               "statement_items": _key_items(f, p)})


def _key_items(f: Financials, p) -> dict:
    items = (["revenue", "gross_profit", "operating_profit", "net_profit", "parent_net_profit", "operating_cash_flow",
              "capex", "free_cash_flow", "total_assets", "equity", "parent_equity", "cash"]
             if f.template == "industrial" else ["total_assets", "equity", "net_profit", "loans", "deposits",
                                                 "net_interest_income", "earned_premiums"])
    out = {}
    for it in items:
        if f.code(it):
            out[it] = {"period": f.raw(it, p), "ttm": f.ttm(it, p) if f.is_flow(it) else None,
                       "quarter": f.quarter(it, p) if f.is_flow(it) else None}
    if f.template == "industrial":
        out["ebitda"] = {"period": None, "ttm": f.ebitda_ttm(p), "quarter": None}
    return out


def analyze_health(f: Financials | None, profile: str) -> ModuleResult:
    meaning = "0-100: yüksek puan güçlü likidite, makul borçluluk ve kârlılık."
    if f is None or f.latest is None:
        return ModuleResult("financial_health", None, 0.0, None, notes=["Finansal tablo verisi yok."], meaning=meaning)
    cfg = config()["financial_health"]
    p = f.latest
    ms = ratios(f, p, profile)
    v = lambda c: _metric(ms, c)
    if f.template == "financial" or profile in FINANCIAL_PROFILES:
        comps = {
            "profitability": mean([scale(v("roe"), cfg["bank_roe"]), scale(v("roa"), cfg["bank_roa"])]),
            "leverage": scale(v("equity_to_assets"), cfg["bank_equity_to_assets"]),
            "liquidity": scale(v("loans_to_deposits"), cfg["bank_loans_to_deposits"]) if profile == "bank" else None,
            "efficiency": None,
        }
    else:
        nde = v("net_debt_to_ebitda")
        ebitda = f.ebitda_ttm(p)
        if ebitda is not None and ebitda <= 0:
            nde_score = 0.0  # FAVÖK negatif → borç ödeme kapasitesi yok
        else:
            nde_score = scale(nde, cfg["net_debt_to_ebitda"])
        comps = {
            "liquidity": mean([scale(v("current_ratio"), cfg["current_ratio"]),
                               scale(v("quick_ratio"), cfg["quick_ratio"])]),
            "leverage": mean([nde_score, scale(v("liabilities_to_equity"), cfg["liabilities_to_equity"]),
                              scale(v("interest_coverage"), cfg["interest_coverage"])]),
            "profitability": mean([scale(v("roe"), cfg["roe"]), scale(v("net_margin"), cfg["net_margin"])]),
            "efficiency": scale(v("asset_turnover"), cfg["asset_turnover"]),
        }
    score, coverage = weighted(comps, cfg["weights"])
    computed = sum(1 for x in ms if x.value is not None)
    applicable = sum(1 for x in ms if not (x.comment or "").startswith("Finans kuruluşları için uygulanamaz"))
    reliability = coverage * (computed / applicable if applicable else 0)
    notes = _base_notes(f, p)
    eq = f.raw("equity", p)
    if eq is not None and eq <= 0:
        notes.append("Özkaynak negatif: özkaynak bazlı oranlar anlamsızdır.")
    return ModuleResult("financial_health", score, reliability, pkey(p), components=comps, metrics=ms, notes=notes,
                        meaning=meaning, extra={"profile": profile, "template": f.template})
