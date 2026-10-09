"""Simulation déterministe : plusieurs scénarios = plusieurs jeux de pondérations."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .config import SPEC_WEIGHTS
from .matchup import Evaluation, evaluate
from .stats import Profile, StatValue

SCENARIOS = {
    "standard": ("Combat standard, distance moyenne", {}),
    "melee": ("Corps à corps", {"force": 1.3, "durabilite": 1.2, "vitesse": 1.1, "hax": 0.8, "endurance": 1.1}),
    "ranged": ("Longue distance", {"vitesse": 1.2, "puissance": 1.2, "hax": 1.1, "force": 0.7}),
    "tactical": ("Combat tactique", {"battle_iq": 2.0, "experience": 1.8, "versatilite": 1.8,
                                      "hax": 1.2, "force": 0.8}),
    "bloodlusted": ("Bloodlusted (aucune retenue)", {"battle_iq": 0.5, "experience": 0.6, "hax": 1.3,
                                                     "puissance": 1.2, "endurance": 0.8}),
}
PHYS = ("strength", "speed", "reaction_speed", "durability", "attack_power", "range")
ENERGY = ("attack_power", "stamina", "range")


@dataclass
class ScenarioResult:
    name: str
    desc: str
    weight: float
    p_a: float
    evaluation: Evaluation


@dataclass
class Simulation:
    p_a: float
    scenarios: list
    main: Evaluation
    note: str = ""


def scenario_weights(cond) -> dict:
    if cond.bloodlusted:
        return {"bloodlusted": 0.6, "melee": 0.2, "ranged": 0.2}
    if cond.deathmatch:
        return {"standard": 0.4, "melee": 0.2, "ranged": 0.2, "tactical": 0.2}
    return {"standard": 0.4, "melee": 0.2, "ranged": 0.2, "tactical": 0.2}


def _compress(p: Profile, mean: dict, cats, k: float) -> Profile:
    stats = dict(p.stats)
    for c in cats:
        if c in stats and c in mean:
            sv = stats[c]
            stats[c] = StatValue(round(mean[c] + (sv.value - mean[c]) * k, 2), sv.confidence, sv.feats)
    return dataclasses.replace(p, stats=stats)


def equalize(A: Profile, B: Profile, cond):
    if cond.mode == "standard":
        return A, B, ""
    cats, k, note = ((PHYS, 0.4, "Stats égalisées : écarts physiques réduits de 60 %.")
                     if cond.mode == "equalized" else
                     (ENERGY, 0.5, "Énergie égalisée : écarts de puissance/endurance/portée réduits de 50 %."))
    mean = {c: (A.value(c) + B.value(c)) / 2 for c in cats if A.value(c) is not None and B.value(c) is not None}
    return _compress(A, mean, cats, k), _compress(B, mean, cats, k), note


def simulate(A: Profile, B: Profile, cond) -> Simulation:
    A2, B2, note = equalize(A, B, cond)
    results, total = [], 0.0
    for name, w in scenario_weights(cond).items():
        desc, mult = SCENARIOS[name]
        weights = {k: v * mult.get(k, 1.0) for k, v in SPEC_WEIGHTS.items()}
        ev = evaluate(A2, B2, weights, cond)
        results.append(ScenarioResult(name, desc, w, ev.p_a, ev))
        total += w * ev.p_a
    main = max(results, key=lambda r: r.weight).evaluation
    return Simulation(total, results, main, note)
