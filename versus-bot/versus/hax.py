"""Capacités spéciales : contre-mesure -> résistance -> probabilité d'efficacité."""
from __future__ import annotations

import math

from .models import Route
from .stats import Profile

NEUTRALIZE_FACTOR = {"standard": 0.85, "deathmatch": 0.70, "bloodlusted": 0.80}


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def speed_blend(p: Profile):
    s, r = p.value("speed"), p.value("reaction_speed")
    if s is not None and r is not None:
        return 0.65 * s + 0.35 * r
    return s if s is not None else r


def hit_chance(att: Profile, dfn: Profile) -> float:
    sa = speed_blend(att)
    rb = dfn.value("reaction_speed")
    rb = rb if rb is not None else dfn.value("speed")
    if sa is None or rb is None:
        return 0.6
    return clamp(0.55 + (sa - rb) / 60.0, 0.15, 1.0)


def neutralize_factor(cond) -> float:
    key = "deathmatch" if cond.deathmatch else "bloodlusted" if cond.bloodlusted else "standard"
    return NEUTRALIZE_FACTOR[key]


def ability_route(ab, att: Profile, dfn: Profile, cond) -> Route:
    tags = [t for t in ab.tags if t not in ab.bypasses]
    res_tag = max(tags, key=lambda t: dfn.resist.get(t, 0), default=None)
    res = dfn.resist.get(res_tag, 0.0) if res_tag else 0.0
    vuln = max((dfn.vuln.get(t, 0.0) for t in ab.tags), default=0.0)
    factor = clamp(1 - res + vuln, 0.0, 1.3)
    p = ab.potency * ab.reliability * factor
    if ab.needs_contact:
        p *= hit_chance(att, dfn)
    if ab.win_type == "neutralize":
        p *= neutralize_factor(cond)
    p *= 0.5 + 0.5 * ab.confidence
    p = min(p, 0.95)
    notes = []
    if res > 0 and res_tag:
        via, note = dfn.resist_via.get(res_tag, ("", ""))
        notes.append(f"contré à {int(res * 100)}% ({res_tag}{', ' + via if via else ''})")
    if ab.bypasses:
        notes.append("ignore " + "/".join(ab.bypasses))
    if vuln > 0:
        notes.append("cible vulnérable")
    return Route(ab.name, "hax", p, "; ".join(notes), ab.id)


def hax_routes(att: Profile, dfn: Profile, cond) -> list:
    return [ability_route(a, att, dfn, cond) for a in att.abilities
            if a.hax and a.win_type in ("kill", "neutralize")]


def resistance_score(p: Profile) -> float:
    miss = 1.0
    for lvl in p.resist.values():
        miss *= 1 - 0.5 * lvl
    return 100 * (1 - miss)


def versatility_score(p: Profile) -> float:
    tags = {"physical"}
    for a in p.abilities:
        tags.update(a.tags)
    return 100 * (1 - math.exp(-len(tags) / 6.0))
