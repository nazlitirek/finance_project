"""Finansal hesaplamaların bilinen değerlerle doğrulanması (internetsiz, veritabanısız)."""

import math

import numpy as np
import pandas as pd
import pytest

from app.analysis import fundamental, risk, scoring, technical, valuation
from app.analysis.common import ModuleResult, div, scale, weighted
from app.analysis.statements import build

# ---------------------------------------------------------------- ortak

def test_div_and_scale_edge_cases():
    assert div(1, 0) is None and div(None, 2) is None and div(6, 3) == 2
    assert scale(0.5, [0, 1]) == 50 and scale(2, [0, 1]) == 100 and scale(-1, [0, 1]) == 0
    assert scale(1.0, [4.0, 0.0]) == 75  # düşük daha iyi
    assert scale(float("nan"), [0, 1]) is None


def test_weighted_normalizes_missing_parts():
    score, cov = weighted({"a": 80, "b": None, "c": 40}, {"a": 50, "b": 25, "c": 25})
    assert score == pytest.approx((80 * 50 + 40 * 25) / 75) and cov == pytest.approx(0.75)
    assert weighted({"a": None}, {"a": 1}) == (None, 0.0)


# ---------------------------------------------------------------- teknik göstergeler

def s(values):
    return pd.Series(values, dtype=float, index=pd.date_range("2026-01-01", periods=len(values)))


def test_sma_and_ema_known_values():
    x = s([1, 2, 3, 4, 5])
    assert technical.sma(x, 3).tolist()[2:] == [2, 3, 4]
    # EMA(3): α = 0.5, ilk değer 1 → 1, 1.5, 2.25, 3.125, 4.0625 (ilk 2 değer min_periods nedeniyle boş)
    assert technical.ema(x, 3).round(4).tolist()[2:] == [2.25, 3.125, 4.0625]


def test_rsi_wilder_hand_calculated():
    # Değişimler: +1, −1, +2, −1, +1  (n = 2)
    # İlk ort. kazanç = (1+0)/2 = 0.5, ilk ort. kayıp = (0+1)/2 = 0.5 → RSI = 50
    # Sonra: kazanç = (0.5·1 + 2)/2 = 1.25, kayıp = (0.5·1 + 0)/2 = 0.25 → RSI = 100 − 100/(1+5) = 83.333
    x = s([10, 11, 10, 12, 11, 12])
    r = technical.rsi(x, 2)
    assert r.iloc[2] == pytest.approx(50.0)
    assert r.iloc[3] == pytest.approx(100 - 100 / 6)


def test_rsi_all_gains_is_100_all_losses_is_0():
    assert technical.rsi(s(range(1, 30)), 14).iloc[-1] == 100
    assert technical.rsi(s(range(30, 1, -1)), 14).iloc[-1] == pytest.approx(0.0)


def test_macd_relationship():
    x = s(np.linspace(10, 50, 60))
    m = technical.macd(x)
    assert (m["hist"] - (m["macd"] - m["signal"])).abs().max() < 1e-12
    assert m["macd"].iloc[-1] > 0  # yükselen seride hızlı EMA yavaşın üzerinde


def test_atr_true_range_with_gap():
    high, low, close = s([10, 12, 15]), s([9, 10, 14]), s([9.5, 11, 14.5])
    tr = technical.true_range(high, low, close)
    # Gün 2: max(12−10, |12−9.5|, |10−9.5|) = 2.5 ; Gün 3: max(1, |15−11|, |14−11|) = 4 (boşluk dahil)
    assert tr.iloc[1] == 2.5 and tr.iloc[2] == 4
    a = technical.atr(high, low, close, 2)
    assert a.iloc[2] == pytest.approx((2.5 + 4) / 2)


def test_stochastic_and_williams():
    high, low = s([10, 11, 12]), s([8, 9, 10])
    close = s([9, 10, 11.5])
    st = technical.stochastic(high, low, close, n=3, d=1)
    assert st["k"].iloc[-1] == pytest.approx(100 * (11.5 - 8) / (12 - 8))
    assert technical.williams_r(high, low, close, 3).iloc[-1] == pytest.approx(-100 * (12 - 11.5) / 4)


def test_stochastic_flat_range_is_none():
    st = technical.stochastic(s([5, 5, 5]), s([5, 5, 5]), s([5, 5, 5]), n=3, d=1)
    assert math.isnan(st["k"].iloc[-1])  # sıfıra bölme → değer yok


def test_bollinger_and_hist_vol():
    x = s([10] * 25)
    bb = technical.bollinger(x)
    assert bb["upper"].iloc[-1] == 10 and math.isnan(bb["pct_b"].iloc[-1])
    assert technical.historical_volatility(x).iloc[-1] == 0


def test_obv_and_mfi():
    close, vol = s([10, 11, 10, 10]), s([100, 200, 300, 400])
    assert technical.obv(close, vol).tolist() == [0, 200, -100, -100]
    h = l = c = s([1, 2, 3, 4, 5])
    assert technical.mfi(h, l, c, s([10] * 5), n=3).iloc[-1] == 100  # hep yükselen → negatif akış yok


def test_support_resistance_finds_levels():
    pattern = [100, 105, 110, 105, 100, 95, 90, 95, 100, 105, 110, 105, 100, 95, 90, 95, 100]
    x = s(pattern * 3)
    lv = technical.support_resistance(x, x, x, window=2, tolerance=0.01)
    assert lv["resistances"][0]["level"] == 110 and lv["resistances"][0]["touches"] >= 2
    assert lv["supports"][0]["level"] == 90


def test_technical_analyze_trend_up_and_short_history():
    n = 260
    close = s(np.linspace(50, 150, n) + np.sin(np.arange(n)) * 0.5)
    df = pd.DataFrame({"close": close, "high": close + 1, "low": close - 1, "turnover": 1e6})
    r = technical.analyze(df)
    assert r.assessments["trend_direction"] == "up" and r.components["trend"] == 100
    assert r.reliability > 0.9 and 0 <= r.score <= 100
    assert next(m for m in r.metrics if m.code == "vwap").value is None
    short = technical.analyze(df.tail(20))
    assert short.score is None and short.reliability == 0


# ---------------------------------------------------------------- finansal tablolar

def fin(rows, profile="general"):
    return build([(y, p, c, v, True) for (y, p), items in rows.items() for c, v in items.items()], profile)


BASE = {
    "1A": 500, "1AA": 100, "1AB": 20, "1AC": 120, "1AF": 80, "1BL": 2000,
    "2A": 400, "2AA": 150, "2B": 600, "2BA": 350, "2N": 1000, "2O": 900, "2ODA": 100,
}


def industrial():
    """Kümülatif gelir: 2025 Q1..Q4 ve 2026 Q1..Q3."""
    rev = {(2025, 3): 100, (2025, 6): 220, (2025, 9): 350, (2025, 12): 500,
           (2026, 3): 130, (2026, 6): 280, (2026, 9): 450}
    rows = {}
    for (y, p), r in rev.items():
        rows[(y, p)] = {**BASE, "3C": r, "3CA": -0.6 * r, "3D": 0.4 * r, "3DF": 0.2 * r, "3HC": -0.05 * r,
                        "3L": 0.1 * r, "3Z": 0.09 * r, "4B": -0.05 * r, "4C": 0.15 * r, "4CAI": -0.08 * r,
                        "4CB": 0.07 * r}
    return fin(rows)


def test_template_detection():
    assert industrial().template == "industrial"
    assert fin({(2026, 9): {"1Z": 1, "2O": 1, "3Z": 1}}, "bank").template == "financial"


def test_ttm_quarter_and_avg():
    f = industrial()
    # TTM 2026/09 = 450 + 500 − 350 = 600
    assert f.ttm("revenue", (2026, 9)) == 600
    assert f.ttm("revenue", (2025, 12)) == 500
    assert f.ttm("revenue", (2025, 9)) is None  # 2024 verisi yok → tahmin yok
    assert f.quarter("revenue", (2026, 9)) == 170 and f.quarter("revenue", (2026, 3)) == 130
    assert f.ebitda_ttm((2026, 9)) == pytest.approx(0.2 * 600 + 0.05 * 600)
    assert f.avg("total_assets", (2026, 9)) == 2000


def test_bank_and_insurance_codes_do_not_mix():
    bank = fin({(2026, 9): {"3AA": 5}}, "bank")
    ins = fin({(2026, 9): {"3AA": 5}}, "insurance")
    assert bank.code("earned_premiums") is None and ins.code("earned_premiums") == "3AA"
    assert ins.code("loans") is None


def test_growth_function():
    assert fundamental.growth(120, 100) == pytest.approx(0.2)
    assert fundamental.growth(50, -100) == pytest.approx(1.5)  # zarardan kâra: olumlu yön
    assert fundamental.growth(10, 0) is None and fundamental.growth(None, 1) is None


def test_ratios_known_values():
    f = industrial()
    ms = {m.code: m for m in fundamental.ratios(f, (2026, 9), "general")}
    assert ms["current_ratio"].value == pytest.approx(500 / 400)
    assert ms["quick_ratio"].value == pytest.approx((500 - 80) / 400)
    assert ms["cash_ratio"].value == pytest.approx(120 / 400)
    assert ms["liabilities_to_equity"].value == pytest.approx(1000 / 1000)
    assert ms["net_debt_to_ebitda"].value == pytest.approx((500 - 120) / 150)
    assert ms["interest_coverage"].value == pytest.approx(120 / 30)
    assert ms["gross_margin"].value == pytest.approx(0.4)
    assert ms["net_margin"].value == pytest.approx(0.1)
    assert ms["roe"].value == pytest.approx(0.09 * 600 / 900)
    assert ms["receivable_days"].value == pytest.approx(120 / 600 * 365)
    assert ms["inventory_turnover"].value == pytest.approx(0.6 * 600 / 80)
    assert all(m.formula for m in ms.values())


def test_ratios_zero_denominator_gives_none():
    rows = {(2026, 9): {**BASE, "2A": 0, "3C": 0, "3Z": 1, "3L": 1}}
    ms = {m.code: m for m in fundamental.ratios(fin(rows), (2026, 9), "general")}
    assert ms["current_ratio"].value is None and ms["net_margin"].value is None


def test_financial_profile_skips_industrial_ratios():
    f = fin({(2026, 9): {"1Z": 1000, "2O": 100, "3Z": 20, "1AF": 600, "2A": 700}}, "bank")
    ms = {m.code: m for m in fundamental.ratios(f, (2026, 9), "bank")}
    assert ms["loans_to_deposits"].value == pytest.approx(600 / 700)
    assert ms["current_ratio"].value is None and "uygulanamaz" in ms["current_ratio"].comment


def test_fundamental_and_health_scores_in_range():
    f = industrial()
    fr = fundamental.analyze_fundamental(f, "general")
    hr = fundamental.analyze_health(f, "general")
    assert 0 <= fr.score <= 100 and 0 <= hr.score <= 100
    assert fr.reliability < 1  # 7 çeyrek < 8
    assert fundamental.analyze_fundamental(None, "general").score is None


# ---------------------------------------------------------------- değerleme

def test_multiples_and_negative_earnings():
    f = industrial()
    m = valuation.multiples(f, (2026, 9), mcap=1000.0, profile="general")
    assert m["pe"] == pytest.approx(1000 / (0.09 * 600))
    assert m["pb"] == pytest.approx(1000 / 900)
    nd = 150 + 350 - 100 - 20
    assert m["ev"] == pytest.approx(1000 + nd + 100)
    assert m["ev_ebitda"] == pytest.approx((1000 + nd + 100) / 150)
    loss = fin({(2026, 12): {**BASE, "3Z": -5, "3C": 10}})
    assert valuation.multiples(loss, (2026, 12), 1000.0, "general")["pe"] is None


def test_dcf_scenario_hand_calculated():
    """Tek yıllık, sabit WACC'lı basit model elle hesaplanır."""
    cfg = {"years": 1, "tax_rate": 0.25, "nwc_to_revenue_change": 0.1}
    base = {"revenue": 100.0, "ebitda_margin": 0.2, "da_pct": 0.05, "capex_pct": 0.05, "net_debt": 10.0,
            "minority": 0.0, "shares": 10.0, "wacc0": 0.2, "wacc_long": 0.2}
    sc = {"revenue_growth": [0.1], "margin_change": 0.0, "wacc_change": 0.0, "terminal_growth": 0.05}
    r = valuation.dcf_scenario(base, sc, cfg)
    rev = 110.0
    fcf = (22 - 5.5) * 0.75 + 5.5 - 5.5 - 1.0  # = 11.375
    pv = fcf / 1.2
    tv = fcf * 1.05 / 0.15
    equity = pv + tv / 1.2 - 10
    assert r["years"][0]["revenue"] == pytest.approx(rev)
    assert r["years"][0]["fcf"] == pytest.approx(fcf)
    assert r["equity_value"] == pytest.approx(equity)
    assert r["value_per_share"] == pytest.approx(equity / 10)


def test_dcf_rejects_terminal_growth_near_wacc():
    cfg = {"years": 1, "tax_rate": 0.25, "nwc_to_revenue_change": 0.1}
    base = {"revenue": 100.0, "ebitda_margin": 0.2, "da_pct": 0.05, "capex_pct": 0.05, "net_debt": 0.0,
            "minority": 0.0, "shares": 1.0, "wacc0": 0.1, "wacc_long": 0.1}
    sc = {"revenue_growth": [0.1], "margin_change": 0.0, "wacc_change": 0.0, "terminal_growth": 0.09}
    assert valuation.dcf_scenario(base, sc, cfg)["valid"] is False


def test_dcf_not_computed_with_short_history():
    m = valuation.Market(price=10, price_date="2026-11-20", shares=100, risk_free=0.36, risk_free_source="x", beta=1)
    d = valuation.dcf(industrial(), (2026, 9), m, "general")
    assert d["valid"] is False and "çeyrek" in d["reason"]
    assert valuation.dcf(industrial(), (2026, 9), m, "bank")["valid"] is False


def test_percentile_score():
    assert valuation.percentile_score(5, [1, 2, 3, 4], lower_is_better=True) == 0
    assert valuation.percentile_score(0, [1, 2, 3, 4], lower_is_better=True) == 100
    assert valuation.percentile_score(None, [1], True) is None


# ---------------------------------------------------------------- risk

def test_beta_of_index_with_itself_is_one_and_scaled_series():
    rng = np.random.default_rng(1)
    idx = s(rng.normal(0, 0.01, 300))
    assert risk.beta(idx, idx) == pytest.approx(1.0)
    assert risk.beta(idx * 2, idx) == pytest.approx(2.0)
    assert risk.beta(idx.head(50), idx.head(50)) is None  # yetersiz gözlem


def test_max_drawdown_known():
    assert risk.max_drawdown(s([100, 120, 60, 90, 130])) == pytest.approx(-0.5)
    assert risk.max_drawdown(s([1, 2, 3])) == 0


def test_sharpe_and_downside():
    r = s([0.01, -0.01] * 100)
    assert risk.sharpe(r, 0.0) == pytest.approx(0.0, abs=1e-9)
    assert risk.downside_deviation(s([0.01, 0.02])) == 0
    dd = risk.downside_deviation(s([-0.02, 0.0]))
    assert dd == pytest.approx(math.sqrt((0.02 ** 2) / 2) * math.sqrt(252))
    assert risk.rf_daily(0.0) == 0


def test_risk_analyze_low_vs_high_volatility():
    n = 300
    calm = pd.DataFrame({"close": s(100 * np.cumprod(1 + np.full(n, 0.001)))})
    calm["high"], calm["low"], calm["turnover"] = calm["close"] * 1.001, calm["close"] * 0.999, 3e8
    rng = np.random.default_rng(2)
    wild = pd.DataFrame({"close": s(100 * np.cumprod(1 + rng.normal(0, 0.05, n)))})
    wild["high"], wild["low"], wild["turnover"] = wild["close"] * 1.03, wild["close"] * 0.97, 1e6
    a = risk.analyze(calm, None, None, 0.3, "test")
    b = risk.analyze(wild, None, None, 0.3, "test")
    assert a.score > b.score  # 100 = düşük risk
    assert "100 düşük risk" in a.meaning


# ---------------------------------------------------------------- genel puan

def test_overall_normalizes_and_labels():
    def mr(score):
        return ModuleResult("x", score, 1.0, None)
    res = scoring.overall({"technical": mr(80), "fundamental": mr(80), "financial_health": mr(80),
                           "valuation": mr(80), "sector": None, "news": None, "risk": mr(80)})
    assert res["score"] == 80 and res["label"] == "strong" and res["coverage"] == 0.85
    assert "Sektör karşılaştırması" in res["missing_modules"]
    low = scoring.overall({"technical": mr(90)})
    assert low["score"] == 90 and low["label"] is None and low["note"]  # kapsama %15 < %50


def test_ai_cannot_change_scores_structure():
    """Puanlar sadece bu modüllerin çıktısıdır; to_dict sonrası değiştirilen bir kopya kaynak sonucu etkilemez."""
    r = ModuleResult("technical", 55.5, 1.0, None)
    d = r.to_dict()
    d["score"] = 99
    assert r.score == 55.5
