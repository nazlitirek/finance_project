"""Risk analizi. Puan yönü diğer modüllerin TERSİ gibi okunmamalı: 100 = DÜŞÜK risk, 0 = YÜKSEK risk.

Piyasa riski: düzeltilmiş günlük kapanışlardan; referans endeks BIST 100 (XU100).
Risksiz faiz: TCMB ağırlıklı ortalama fonlama maliyetinin (EVDS TP.APIFON4) dönem ortalaması.
"""

import math

import numpy as np
import pandas as pd

from app.analysis.common import Metric, ModuleResult, config, div, num, scale, weighted
from app.analysis.statements import Financials, pkey

TRADING_DAYS = 252
MEANING = "0-100: 100 düşük risk, 0 yüksek risk. Diğer puanlarla aynı yönde değildir; yüksek puan daha az risk demektir."


def daily_returns(close: pd.Series) -> pd.Series:
    return close.astype(float).pct_change().dropna()


def annual_volatility(r: pd.Series) -> float | None:
    return num(r.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(r) > 2 else None


def beta(stock: pd.Series, index: pd.Series, min_obs: int = 120) -> float | None:
    """Günlük getiriler üzerinden β = Kov(hisse, endeks) / Var(endeks). Ortak günler kullanılır."""
    df = pd.concat([stock, index], axis=1, join="inner").dropna()
    if len(df) < min_obs:
        return None
    var = df.iloc[:, 1].var(ddof=1)
    return num(df.iloc[:, 0].cov(df.iloc[:, 1]) / var) if var else None


def max_drawdown(close: pd.Series) -> float | None:
    c = close.astype(float).dropna()
    if len(c) < 2:
        return None
    return num((c / c.cummax() - 1).min())


def rf_daily(rf_annual: float) -> float:
    return (1 + rf_annual) ** (1 / TRADING_DAYS) - 1


def downside_deviation(r: pd.Series, target: float = 0.0) -> float | None:
    """Yıllıklandırılmış aşağı yönlü sapma: √ort(min(0, r − hedef)²) × √252."""
    if len(r) < 2:
        return None
    d = np.minimum(0.0, r - target)
    return num(math.sqrt(float((d ** 2).mean())) * math.sqrt(TRADING_DAYS))


def sharpe(r: pd.Series, rf_annual: float) -> float | None:
    ex = r - rf_daily(rf_annual)
    sd = ex.std(ddof=1)
    return num(ex.mean() / sd * math.sqrt(TRADING_DAYS)) if len(r) > 2 and sd else None


def sortino(r: pd.Series, rf_annual: float) -> float | None:
    t = rf_daily(rf_annual)
    dd = downside_deviation(r, t)
    return num((r - t).mean() * TRADING_DAYS / dd) if dd else None


def profit_cv(f: Financials | None) -> tuple[float | None, int]:
    """Son 8 çeyreklik tek çeyrek net kârın değişim katsayısı (std / |ortalama|) ve zararlı çeyrek sayısı."""
    if f is None:
        return None, 0
    qs = [f.quarter("net_profit", p) for p in f.periods[:8]]
    qs = [q for q in qs if q is not None]
    if len(qs) < 4:
        return None, 0
    m = float(np.mean(qs))
    losses = sum(1 for q in qs if q < 0)
    return (num(float(np.std(qs, ddof=1)) / abs(m)) if m else None), losses


def analyze(prices: pd.DataFrame, index_close: pd.Series | None, f: Financials | None, risk_free: float | None,
            risk_free_source: str | None, health_metrics: list[Metric] | None = None) -> ModuleResult:
    cfg = config()["risk"]
    look = cfg["lookback_days"]
    close = prices["close"].astype(float).dropna() if prices is not None and len(prices) else pd.Series(dtype=float)
    if len(close) < 60:
        return ModuleResult("risk", None, 0.0, None, notes=["Risk analizi için en az 60 günlük fiyat gerekir."],
                            meaning=MEANING)
    r_all = daily_returns(close)
    r = r_all.tail(look)
    window_start, window_end = r.index[0].date().isoformat(), r.index[-1].date().isoformat()
    hv = annual_volatility(r)
    b = beta(r, daily_returns(index_close).reindex(r.index) if index_close is not None else pd.Series(dtype=float))
    mdd = max_drawdown(close)  # bütün geçmiş (en fazla ~3 yıl)
    dd = downside_deviation(r)
    sh = sharpe(r, risk_free) if risk_free is not None else None
    so = sortino(r, risk_free) if risk_free is not None else None
    turnover = prices["turnover"].astype(float).tail(20).mean() if "turnover" in prices else None
    atr_pct = None
    if {"high", "low"} <= set(prices.columns):
        from app.analysis.technical import atr
        a = atr(prices["high"].astype(float), prices["low"].astype(float), prices["close"].astype(float))
        atr_pct = div(a.dropna().iloc[-1], close.iloc[-1]) if a.notna().any() else None
    hm = {x.code: x.value for x in (health_metrics or [])}
    nde, cr = hm.get("net_debt_to_ebitda"), hm.get("current_ratio")
    cv, losses = profit_cv(f)
    ebitda = f.ebitda_ttm(f.latest) if f and f.latest and f.template == "industrial" else None

    metrics = [
        Metric("historical_volatility", "Tarihsel oynaklık (yıllık)", hv, unit="%",
               formula="Günlük getirilerin standart sapması × √252"),
        Metric("beta", "Beta (BIST 100)", b, formula="Kov(hisse, BIST 100) / Var(BIST 100), günlük getiriler"),
        Metric("max_drawdown", "Maksimum düşüş", mdd, unit="%",
               formula="En yüksek seviyeden en büyük yüzde düşüş (eldeki bütün fiyat geçmişi)"),
        Metric("sharpe", "Sharpe oranı", sh, formula="(Ort. günlük getiri − risksiz) / std × √252"),
        Metric("sortino", "Sortino oranı", so, formula="(Ort. günlük getiri − risksiz) × 252 / Aşağı yönlü sapma"),
        Metric("downside_deviation", "Aşağı yönlü sapma (yıllık)", dd, unit="%",
               formula="√ort(min(0, getiri)²) × √252"),
        Metric("atr_pct", "ATR / Fiyat", atr_pct, unit="%", formula="ATR(14) / Son kapanış"),
        Metric("net_debt_to_ebitda", "Borçluluk riski: Net borç / FAVÖK", nde, unit="x"),
        Metric("current_ratio", "Likidite riski: Cari oran", cr),
        Metric("avg_turnover_20", "Piyasa likiditesi: 20 günlük ort. hacim", num(turnover), unit="TL"),
        Metric("profit_cv", "Kârlılık istikrarsızlığı (değişim katsayısı)", cv,
               formula="Son 8 çeyrek tek çeyrek net kârın std / |ortalama|",
               comment=f"Son 8 çeyrekte {losses} zararlı çeyrek" if cv is not None else None),
    ]
    if ebitda is not None and ebitda <= 0:
        lev = 0.0
    else:
        lev = scale(nde, cfg["net_debt_to_ebitda"])
    comps = {
        "historical_volatility": scale(hv, cfg["historical_volatility"]),
        "beta": scale(b, cfg["beta"]),
        "max_drawdown": scale(mdd, cfg["max_drawdown"]),
        "downside_deviation": scale(dd, cfg["downside_deviation"]),
        "leverage": lev,
        "liquidity": scale(cr, cfg["current_ratio"]),
        "market_liquidity": scale(num(turnover), cfg["avg_turnover_tl"]),
        "profit_stability": scale(cv, cfg["profit_cv"]),
    }
    score, coverage = weighted(comps, cfg["weights"])
    notes = [f"Beta, oynaklık, Sharpe ve Sortino: {window_start} – {window_end} ({len(r)} işlem günü).",
             "Referans endeks: BIST 100 (İş Yatırım gün sonu kapanışları)."]
    if risk_free is not None:
        notes.append(f"Risksiz faiz: yıllık %{risk_free * 100:.2f} ({risk_free_source}).")
    else:
        notes.append("Risksiz faiz verisi yok; Sharpe ve Sortino hesaplanmadı.")
    if b is None:
        notes.append("Beta için yeterli ortak gün (en az 120) yok.")
    return ModuleResult("risk", score, coverage * min(1.0, len(r) / look), window_end, components=comps,
                        metrics=metrics, notes=notes, meaning=MEANING,
                        extra={"window_start": window_start, "window_end": window_end, "observations": len(r),
                               "risk_free": risk_free, "risk_free_source": risk_free_source,
                               "financial_period": pkey(f.latest) if f and f.latest else None})
