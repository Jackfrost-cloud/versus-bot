"""Évaluation d'un matchup : routes de victoire + score pondéré par catégories."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import hax
from .models import Route
from .stats import Profile

SIGMA = 9.0


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def noisy_or(ps) -> float:
    q = 1.0
    for p in ps:
        q *= 1 - min(max(p, 0.0), 0.95)
    return 1 - q


@dataclass
class Evaluation:
    p_a: float
    s_a: float
    s_b: float
    cats: dict
    excluded: list
    routes_a: list
    routes_b: list
    pa: float
    pb: float
    stalemate: bool = False


def burst_route(A: Profile, B: Profile) -> Route | None:
    ap, dur = A.value("attack_power"), B.value("durability")
    if ap is None or dur is None:
        return None
    dur_eff = dur + 10 * B.regen
    p = sigmoid((ap - dur_eff) / 6.0)
    res = 0.0
    for tag in ("physical", "intangibility"):
        if tag not in A.bypass:
            res = max(res, B.resist.get(tag, 0.0))
    p *= (1 - res) * (0.6 + 0.4 * hax.hit_chance(A, B))
    note = f"puissance {ap:.0f} vs durabilité effective {dur_eff:.0f}"
    if res:
        note += f", réduit de {int(res * 100)}% (défense physique)"
    return Route("Dégâts physiques bruts", "physical", p, note)


def attrition_route(A: Profile, B: Profile, burst_a, burst_b) -> Route | None:
    sa, sb = A.value("stamina"), B.value("stamina")
    if sa is None or sb is None:
        return None
    ba = burst_a.p if burst_a else 0.0
    bb = burst_b.p if burst_b else 0.0
    p = 0.3 * hax_sigmoid((sa + 10 * A.regen - sb) / 12.0) * (1 - max(ba, bb))
    return Route("Usure / endurance", "attrition", p, f"endurance {sa:.0f} vs {sb:.0f}")


def hax_sigmoid(x):
    return sigmoid(x)


def routes_for(A: Profile, B: Profile, cond):
    ba, bb = burst_route(A, B), burst_route(B, A)
    r = [x for x in (ba, attrition_route(A, B, ba, bb)) if x]
    r += hax.hax_routes(A, B, cond)
    return sorted(r, key=lambda x: -x.p)


def evaluate(A: Profile, B: Profile, weights: dict, cond) -> Evaluation:
    ra, rb = routes_for(A, B, cond), routes_for(B, A, cond)
    pa, pb = noisy_or(r.p for r in ra), noisy_or(r.p for r in rb)
    cats, excluded = {}, []

    def add(key, a, b):
        if a is None or b is None:
            excluded.append(key)
        else:
            cats[key] = (a, b)

    add("force", A.value("strength"), B.value("strength"))
    add("vitesse", hax.speed_blend(A), hax.speed_blend(B))
    add("durabilite", A.value("durability"), B.value("durability"))
    add("puissance", A.value("attack_power"), B.value("attack_power"))
    add("endurance", A.value("stamina"), B.value("stamina"))
    add("battle_iq", A.value("battle_iq"), B.value("battle_iq"))
    add("experience", A.value("experience"), B.value("experience"))
    cats["hax"] = (100 * noisy_or(r.p for r in ra if r.kind == "hax"),
                   100 * noisy_or(r.p for r in rb if r.kind == "hax"))
    cats["resistances"] = (hax.resistance_score(A), hax.resistance_score(B))
    cats["versatilite"] = (hax.versatility_score(A), hax.versatility_score(B))
    tot = pa + pb
    cats["matchup"] = (100 * pa / tot, 100 * pb / tot) if tot > 0 else (50.0, 50.0)
    wsum = sum(weights[k] for k in cats)
    sa = sum(weights[k] * v[0] for k, v in cats.items()) / wsum
    sb = sum(weights[k] * v[1] for k, v in cats.items()) / wsum
    return Evaluation(sigmoid((sa - sb) / SIGMA), sa, sb, cats, excluded, ra, rb, pa, pb, tot < 0.2)
