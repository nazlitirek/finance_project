"""Teknik analiz: göstergeler, değerlendirmeler ve 0-100 teknik puan.

Girdi: günlük, bölünme/temettüye göre düzeltilmiş fiyatlar (DataFrame: close, high, low, turnover; tarih indeksi).
Kaynak sınırları:
- Açılış fiyatı yok → açılış gerektiren gösterge kullanılmaz.
- Hacim TL cinsinden. OBV ve hacim ortalaması TL hacimle hesaplanır.
  MFI'daki "para akışı" (tipik fiyat × hacim) yerine doğrudan TL hacim kullanılır (aynı anlam).
- Gün içi veri yok → VWAP hesaplanmaz.
"""

import math

import numpy as np
import pandas as pd

from app.analysis.common import Metric, ModuleResult, config, num, weighted

TRADING_DAYS = 252


# ---------------------------------------------------------------- göstergeler (saf fonksiyonlar)

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder yumuşatması: ilk değer n günlük basit ortalama, sonra (önceki × (n−1) + yeni) / n."""
    out = pd.Series(np.nan, index=s.index, dtype=float)
    vals = s.to_numpy(dtype=float)
    valid = np.where(~np.isnan(vals))[0]
    if len(valid) < n:
        return out
    start = valid[0]
    if np.isnan(vals[start:start + n]).any():
        return out
    prev = vals[start:start + n].mean()
    out.iloc[start + n - 1] = prev
    for i in range(start + n, len(vals)):
        if np.isnan(vals[i]):
            continue
        prev = (prev * (n - 1) + vals[i]) / n
        out.iloc[i] = prev
    return out


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), n)
    loss = _wilder(-delta.clip(upper=0), n)
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def stochastic(high, low, close, n: int = 14, d: int = 3) -> pd.DataFrame:
    hh, ll = high.rolling(n, min_periods=n).max(), low.rolling(n, min_periods=n).min()
    k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    return pd.DataFrame({"k": k, "d": k.rolling(d, min_periods=d).mean()})


def williams_r(high, low, close, n: int = 14) -> pd.Series:
    hh, ll = high.rolling(n, min_periods=n).max(), low.rolling(n, min_periods=n).min()
    return -100 * (hh - close) / (hh - ll).replace(0, np.nan)


def roc(close: pd.Series, n: int = 12) -> pd.Series:
    return 100 * (close / close.shift(n) - 1)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    width = (upper - lower).replace(0, np.nan)
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower,
                         "pct_b": (close - lower) / width, "bandwidth": (upper - lower) / mid})


def true_range(high, low, close) -> pd.Series:
    pc = close.shift(1)
    return pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1, skipna=False)


def atr(high, low, close, n: int = 14) -> pd.Series:
    return _wilder(true_range(high, low, close), n)


def historical_volatility(close: pd.Series, n: int = 20) -> pd.Series:
    """Yıllıklandırılmış, logaritmik getirilerin standart sapması (oran, ör. 0.35 = %35)."""
    r = np.log(close / close.shift(1))
    return r.rolling(n, min_periods=n).std(ddof=1) * math.sqrt(TRADING_DAYS)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume.fillna(0)).cumsum()


def mfi(high, low, close, money_flow: pd.Series, n: int = 14) -> pd.Series:
    tp = (high + low + close) / 3
    up = tp > tp.shift(1)
    down = tp < tp.shift(1)
    pos = money_flow.where(up, 0.0).rolling(n, min_periods=n).sum()
    neg = money_flow.where(down, 0.0).rolling(n, min_periods=n).sum()
    out = 100 - 100 / (1 + pos / neg)
    return out.where(neg != 0, 100.0).where(pos.notna())


def support_resistance(high, low, close, window: int = 5, lookback: int = 250, tolerance: float = 0.015,
                       max_levels: int = 3) -> dict:
    """Tarihsel dönüş noktalarından (yerel tepe/dip) destek ve direnç seviyeleri.

    Bir gün, önceki ve sonraki `window` günün en yükseği ise tepe, en düşüğü ise dip sayılır.
    Birbirine `tolerance` oranında yakın noktalar tek seviyede birleştirilir; seviyenin gücü = dokunma sayısı.
    """
    h, lo = high.tail(lookback), low.tail(lookback)
    if len(h) < window * 2 + 1 or close.dropna().empty:
        return {"supports": [], "resistances": []}
    span = window * 2 + 1
    peaks = h[(h == h.rolling(span, center=True, min_periods=span).max())].dropna()
    troughs = lo[(lo == lo.rolling(span, center=True, min_periods=span).min())].dropna()
    points = sorted([float(x) for x in peaks] + [float(x) for x in troughs])
    clusters: list[list[float]] = []
    for p in points:
        if clusters and abs(p - np.mean(clusters[-1])) / np.mean(clusters[-1]) <= tolerance:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = [{"level": round(float(np.mean(c)), 4), "touches": len(c)} for c in clusters]
    price = float(close.dropna().iloc[-1])
    supports = sorted([x for x in levels if x["level"] < price], key=lambda x: -x["level"])[:max_levels]
    resistances = sorted([x for x in levels if x["level"] > price], key=lambda x: x["level"])[:max_levels]
    return {"supports": supports, "resistances": resistances}


# ---------------------------------------------------------------- değerlendirme ve puan

def _last(s: pd.Series, back: int = 0) -> float | None:
    s = s.dropna()
    return num(s.iloc[-1 - back]) if len(s) > back else None


def _sig(x: float | None) -> str | None:
    if x is None:
        return None
    return "positive" if x > 0 else "negative" if x < 0 else "neutral"


def _cat(values: list[float | None]) -> float | None:
    vs = [v for v in values if v is not None]
    return 50 + 50 * sum(vs) / len(vs) if vs else None


def analyze(df: pd.DataFrame) -> ModuleResult:
    """df: tarih indeksli, sütunlar close, high, low, turnover (düzeltilmiş günlük fiyatlar)."""
    cfg = config()["technical"]
    meaning = "0-100: yüksek puan olumlu teknik görünüm (trend, momentum, hacim desteği, düşük oynaklık)."
    df = df.sort_index()
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["turnover"].astype(float)
    n = int(close.notna().sum())
    if n < 30:
        return ModuleResult("technical", None, 0.0, None, notes=["Teknik analiz için en az 30 günlük fiyat gerekir."],
                            meaning=meaning)
    as_of = df.index[-1].date().isoformat() if hasattr(df.index[-1], "date") else str(df.index[-1])
    price = _last(close)

    s = {f"sma_{k}": sma(close, k) for k in (20, 50, 100, 200)}
    e = {f"ema_{k}": ema(close, k) for k in (9, 21, 50, 200)}
    r = rsi(close)
    m = macd(close)
    st = stochastic(high, low, close)
    w = williams_r(high, low, close)
    rc = roc(close)
    bb = bollinger(close)
    a = atr(high, low, close)
    hv = historical_volatility(close)
    sd = close.rolling(20, min_periods=20).std(ddof=1)
    ob = obv(close, vol)
    vma = sma(vol, 20)
    mf = mfi(high, low, close, vol)

    metrics: list[Metric] = []

    def add(code, name, series, unit=None, signal=None, comment=None):
        metrics.append(Metric(code, name, _last(series), _last(series, 1), unit=unit, signal=signal, comment=comment))

    def above(series):
        v = _last(series)
        return None if v is None or price is None else (1 if price > v else -1)

    for k, ser in {**s, **e}.items():
        p = above(ser)
        add(k, k.upper().replace("_", " "), ser, "TL", _sig(p),
            None if p is None else ("Fiyat ortalamanın üzerinde" if p > 0 else "Fiyat ortalamanın altında"))

    rv = _last(r)
    rsi_state = None if rv is None else "overbought" if rv >= 70 else "oversold" if rv <= 30 else "normal"
    add("rsi_14", "RSI 14", r, signal=None if rv is None else "negative" if rv >= 70 else "positive" if rv <= 30 else
        _sig(rv - 50), comment={"overbought": "Aşırı alım bölgesi (≥70)", "oversold": "Aşırı satım bölgesi (≤30)",
                                "normal": "Normal bölge"}.get(rsi_state))
    add("macd", "MACD", m["macd"])
    add("macd_signal", "MACD Sinyal", m["signal"])
    hist = _last(m["hist"])
    add("macd_hist", "MACD Histogram", m["hist"], signal=_sig(hist),
        comment=None if hist is None else ("MACD sinyalin üzerinde" if hist > 0 else "MACD sinyalin altında"))
    k_, d_ = _last(st["k"]), _last(st["d"])
    add("stoch_k", "Stokastik %K", st["k"], signal=None if k_ is None or d_ is None else _sig(k_ - d_))
    add("stoch_d", "Stokastik %D", st["d"])
    wv = _last(w)
    add("williams_r", "Williams %R", w, comment=None if wv is None else "Aşırı alım (> −20)" if wv > -20 else
        "Aşırı satım (< −80)" if wv < -80 else "Normal bölge")
    add("roc_12", "Değişim Oranı (ROC 12, %)", rc, None, _sig(_last(rc)))
    add("bb_upper", "Bollinger Üst", bb["upper"], "TL")
    add("bb_mid", "Bollinger Orta", bb["mid"], "TL")
    add("bb_lower", "Bollinger Alt", bb["lower"], "TL")
    add("bb_pct_b", "Bollinger %B", bb["pct_b"])
    add("atr_14", "ATR 14", a, "TL")
    add("hist_vol_20", "Tarihsel Oynaklık (20 gün, yıllık)", hv, "%")
    add("std_20", "Standart Sapma (20 gün)", sd, "TL")
    add("obv", "OBV (TL hacim)", ob, "TL")
    add("volume_ma_20", "Hacim Ortalaması (20 gün, TL)", vma, "TL")
    mv = _last(mf)
    add("mfi_14", "Para Akışı Endeksi (MFI 14)", mf, comment=None if mv is None else "Aşırı alım (≥80)" if mv >= 80
        else "Aşırı satım (≤20)" if mv <= 20 else "Normal bölge")
    metrics.append(Metric("vwap", "VWAP", None, comment="Gün içi veri olmadığı için hesaplanmadı."))

    # ---- trend
    s50, s200 = _last(s["sma_50"]), _last(s["sma_200"])
    s50_prev = _last(s["sma_50"], 20)
    trend_signals = [
        above(s["sma_50"]), above(s["sma_200"]),
        None if s50 is None or s200 is None else (1 if s50 > s200 else -1),
        None if _last(e["ema_21"]) is None or _last(e["ema_50"]) is None else
        (1 if _last(e["ema_21"]) > _last(e["ema_50"]) else -1),
        None if s50 is None or s50_prev is None else (1 if s50 > s50_prev else -1),
    ]
    trend = _cat(trend_signals)
    tv = [x for x in trend_signals if x is not None]
    trend_dir = None if not tv else ("up" if sum(tv) >= 2 else "down" if sum(tv) <= -2 else "sideways")

    # ---- momentum
    def rsi_pts(v):
        if v is None:
            return None
        return 0.5 if v >= 70 else 1 if v >= 55 else 0 if v >= 45 else -1 if v > 30 else -0.5
    hist_prev = _last(m["hist"], 1)
    mom_signals = [
        rsi_pts(rv),
        None if hist is None else (1 if hist > 0 else -1),
        None if hist is None or hist_prev is None else (0.5 if hist > hist_prev else -0.5),
        None if _last(rc) is None else (1 if _last(rc) > 0 else -1),
        None if k_ is None or d_ is None else (1 if k_ > d_ else -1),
        None if wv is None else (0 if wv > -20 or wv < -80 else (1 if wv > -50 else -1)),
    ]
    momentum = _cat(mom_signals)
    mvs = [x for x in mom_signals if x is not None]
    mom_strength = None if not mvs else ("strong" if momentum >= 65 else "weak" if momentum <= 35 else "neutral")

    # ---- hacim
    obv_ma = sma(ob, 20)
    recent = df.tail(20)
    chg = recent["close"].diff()
    up_vol, down_vol = recent["turnover"][chg > 0].mean(), recent["turnover"][chg < 0].mean()
    vol_ratio = num(up_vol / down_vol) if num(down_vol) else None
    vol_signals = [
        None if _last(ob) is None or _last(obv_ma) is None else (1 if _last(ob) > _last(obv_ma) else -1),
        None if mv is None else (-0.5 if mv >= 80 else 0.5 if mv <= 20 else 1 if mv >= 50 else -1),
        None if vol_ratio is None else (1 if vol_ratio > 1.2 else -1 if vol_ratio < 0.8 else 0),
    ]
    volume = _cat(vol_signals)
    vol_support = None if vol_ratio is None else ("supportive" if vol_ratio > 1.2 else "weak" if vol_ratio < 0.8
                                                  else "neutral")

    # ---- oynaklık ve fiyat davranışı
    pb = _last(bb["pct_b"])
    hv_now = _last(hv)
    hv_year = hv.dropna().tail(TRADING_DAYS)
    hv_pct = num((hv_year < hv_now).mean()) if hv_now is not None and len(hv_year) >= 60 else None
    atr_pct = (a / close).dropna()
    atr_now = num(atr_pct.iloc[-1]) if len(atr_pct) else None
    atr_med = num(atr_pct.tail(TRADING_DAYS).median()) if len(atr_pct) >= 60 else None
    volat_signals = [
        None if pb is None else (0.5 if 0.2 <= pb <= 0.8 else -0.5 if pb > 1 or pb < 0 else 0),
        None if hv_pct is None else (1 if hv_pct < 0.5 else -1 if hv_pct > 0.8 else 0),
        None if atr_now is None or atr_med is None else (1 if atr_now < atr_med else -1),
    ]
    volatility = _cat(volat_signals)
    vol_state = None if hv_pct is None else ("high" if hv_pct > 0.8 else "low" if hv_pct < 0.3 else "normal")

    components = {"trend": trend, "momentum": momentum, "volume": volume, "volatility": volatility}
    score, _ = weighted(components, cfg["weights"])

    computed = sum(1 for x in metrics if x.value is not None)
    expected = len(metrics) - 1  # VWAP hariç
    reliability = (computed / expected) * min(1.0, n / cfg["min_history_days"])

    notes = ["Fiyatlar gün sonu ve bölünme/temettüye göre düzeltilmiştir (İş Yatırım).",
             "Hacim TL cinsindendir; OBV ve MFI TL hacimle hesaplanır.",
             "Açılış fiyatı ve gün içi veri olmadığı için VWAP hesaplanmaz."]
    if n < cfg["min_history_days"]:
        notes.append(f"Fiyat geçmişi {n} gün; SMA 200 gibi uzun ortalamalar eksik olabilir, güvenilirlik düşürüldü.")

    return ModuleResult(
        module="technical", score=score, reliability=reliability, as_of=as_of, components=components,
        metrics=metrics, notes=notes, meaning=meaning,
        assessments={
            "trend_direction": trend_dir, "momentum_strength": mom_strength, "rsi_state": rsi_state,
            "volume_support": vol_support, "up_down_volume_ratio": vol_ratio, "volatility_state": vol_state,
            "atr_pct": atr_now, "price": price,
            "levels": support_resistance(high, low, close),
        },
        extra={"history_days": n},
    )
