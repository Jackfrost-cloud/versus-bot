"""Niveau de confiance : qualité des données x netteté du résultat."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import CONFIDENCE_BANDS, STAT_CATEGORIES


def band(x: float) -> str:
    for thr, label in CONFIDENCE_BANDS:
        if x >= thr:
            return label
    return "insuffisant"


@dataclass
class Confidence:
    value: float
    label: str
    data: float
    notes: list = field(default_factory=list)


def compute(A, B, p_a: float) -> Confidence:
    confs, missing = [], []
    for c in STAT_CATEGORIES:
        a, b = A.stats.get(c), B.stats.get(c)
        if a and b:
            confs.append(min(a.confidence, b.confidence))
        else:
            confs.append(0.0)
            missing.append(c)
    stat_part = sum(confs) / len(confs)
    ab = [x.confidence for p in (A, B) for x in p.abilities if x.hax and x.win_type != "none"]
    ab_part = sum(ab) / len(ab) if ab else 0.5
    data = 0.75 * stat_part + 0.25 * ab_part
    closeness = abs(2 * p_a - 1) * 0.5 + 0.5
    value = round(data * closeness, 3)
    notes = []
    if missing:
        notes.append("Données manquantes : " + ", ".join(missing))
    if closeness < 0.6:
        notes.append("Résultat très serré : la confiance est réduite.")
    return Confidence(value, band(value), round(data, 3), notes)
