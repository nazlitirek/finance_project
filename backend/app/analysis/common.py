"""Analiz modüllerinin ortak yapıları ve yardımcıları. Saf Python; veritabanına dokunmaz."""

import math
import tomllib
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "scoring.toml"

DISCLAIMER = ("Puanlar belgelenmiş formüllerle hesaplanır, eşikler yapılandırılabilir başlangıç değerleridir. "
              "Yatırım tavsiyesi değildir ve gelecekteki getiriyi garanti etmez.")


@lru_cache
def config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def num(x) -> float | None:
    """NaN / sonsuz / None → None; diğerleri float."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def div(a, b) -> float | None:
    """Güvenli bölme: payda 0 / eksik → None (sonuç uydurulmaz)."""
    a, b = num(a), num(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def scale(value, bounds) -> float | None:
    """[kötü, iyi] aralığına göre 0-100. kötü > iyi ise düşük değer iyidir."""
    v = num(value)
    if v is None:
        return None
    bad, good = float(bounds[0]), float(bounds[1])
    if bad == good:
        return 100.0 if v >= good else 0.0
    t = (v - bad) / (good - bad)
    return max(0.0, min(100.0, t * 100.0))


def weighted(parts: dict[str, float | None], weights: dict[str, float]) -> tuple[float | None, float]:
    """Mevcut parçaların ağırlıklı ortalaması ve kapsama oranı (0-1). Eksik parçalar normalize edilir."""
    total = sum(weights.get(k, 0) for k in parts)
    avail = {k: v for k, v in parts.items() if v is not None and weights.get(k, 0) > 0}
    w = sum(weights[k] for k in avail)
    if not avail or w == 0:
        return None, 0.0
    return sum(v * weights[k] for k, v in avail.items()) / w, (w / total if total else 0.0)


def mean(values) -> float | None:
    vs = [v for v in (num(x) for x in values) if v is not None]
    return sum(vs) / len(vs) if vs else None


def label(score: float | None) -> str | None:
    if score is None:
        return None
    o = config()["overall"]
    return "strong" if score >= o["strong_at"] else "weak" if score < o["weak_below"] else "neutral"


LABEL_TR = {"strong": "Güçlü", "neutral": "Nötr", "weak": "Zayıf"}


@dataclass
class Metric:
    code: str
    name: str
    value: float | None
    previous: float | None = None
    formula: str | None = None
    unit: str | None = None  # "ratio", "%", "TL", "gün", "x"
    signal: str | None = None  # positive / negative / neutral
    comment: str | None = None
    sector_median: float | None = None
    previous_label: str | None = None  # önceki değerin dönemi, ör. "2025/09"
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModuleResult:
    module: str
    score: float | None
    reliability: float  # 0-1
    as_of: str | None
    components: dict[str, float | None] = field(default_factory=dict)  # alt kategori puanları
    metrics: list[Metric] = field(default_factory=list)
    assessments: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    meaning: str = ""  # puanın anlamı

    def to_dict(self) -> dict:
        d = asdict(self)
        d["score"] = round(self.score, 1) if self.score is not None else None
        d["reliability"] = round(self.reliability, 2)
        d["label"] = label(self.score)
        d["components"] = {k: (round(v, 1) if v is not None else None) for k, v in self.components.items()}
        return d


def unavailable(module: str, reason: str, meaning: str = "") -> ModuleResult:
    return ModuleResult(module=module, score=None, reliability=0.0, as_of=None, notes=[reason], meaning=meaning)
