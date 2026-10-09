"""Agrégation des feats en statistiques + construction du profil d'un combattant."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import INHERIT_DECAY, KIND_WEIGHTS, STAT_CATEGORIES
from .models import Character, Feat


@dataclass
class StatValue:
    value: float
    confidence: float
    feats: list          # [(Feat, poids)]


def feat_weight(f: Feat) -> float:
    """poids = type de preuve x priorité de la source x confiance."""
    return KIND_WEIGHTS.get(f.kind, 0.1) * (f.source.priority / 10.0) * f.confidence


def aggregate(items: list) -> Optional[StatValue]:
    """Moyenne pondérée des 3 meilleures preuves ; confiance = 1 - prod(1 - poids)."""
    scored = []
    for f, factor in items:
        w = feat_weight(f) * factor
        if w > 0:
            scored.append((w * f.value, w, f))
    if not scored:
        return None
    scored.sort(key=lambda t: -t[0])
    top = scored[:3]
    sw = sum(w for _, w, _ in top)
    value = sum(w * f.value for _, w, f in top) / sw
    miss = 1.0
    for _, w, _ in top:
        miss *= 1 - min(w, 0.95)
    return StatValue(round(value, 2), round(1 - miss, 3), [(f, w) for _, w, f in top])


@dataclass
class Profile:
    character: Character
    form_id: str
    stats: dict
    abilities: list
    resist: dict = field(default_factory=dict)
    resist_via: dict = field(default_factory=dict)
    vuln: dict = field(default_factory=dict)
    regen: float = 0.0
    bypass: set = field(default_factory=set)
    derived: list = field(default_factory=list)

    @property
    def node(self) -> str:
        return f"{self.character.id}:{self.form_id}"

    @property
    def form(self):
        return self.character.forms[self.form_id]

    @property
    def label(self) -> str:
        n = self.form.name
        return f"{self.character.name} ({n})" if n else self.character.name

    @property
    def short(self) -> str:
        return self.character.short

    def value(self, cat: str):
        s = self.stats.get(cat)
        return s.value if s else None

    def conf(self, cat: str) -> float:
        s = self.stats.get(cat)
        return s.confidence if s else 0.0


def build_profile(ch: Character, form_id: str, extra_feats=()) -> Profile:
    chain = dict(ch.form_chain(form_id))
    by_cat: dict = {c: [] for c in STAT_CATEGORIES}
    for f in ch.feats:
        if f.category not in by_cat:
            continue
        if f.form == "*":
            by_cat[f.category].append((0, f))
        elif f.form in chain:
            by_cat[f.category].append((chain[f.form], f))
    stats = {}
    derived = list(extra_feats)
    for cat, lst in by_cat.items():
        items = []
        if lst:
            d0 = min(d for d, _ in lst)       # la forme la plus spécifique remplace ses parents
            items = [(f, INHERIT_DECAY ** d0) for d, f in lst if d == d0]
        items += [(f, 1.0) for f in derived if f.category == cat]
        sv = aggregate(items)
        if sv:
            stats[cat] = sv
    abilities = [a for a in ch.abilities if ch.available(a.forms, form_id)]
    p = Profile(ch, form_id, stats, abilities, derived=derived)
    for r in ch.resistances:
        if ch.available(r.forms, form_id) and r.level > p.resist.get(r.tag, 0):
            p.resist[r.tag] = r.level
            p.resist_via[r.tag] = (r.via, r.note)
    for w in ch.weaknesses:
        if ch.available(w.forms, form_id):
            p.vuln[w.tag] = max(p.vuln.get(w.tag, 0), w.severity)
    for a in abilities:
        p.bypass.update(a.bypasses)
        if "regeneration" in a.tags:
            p.regen = max(p.regen, a.potency * a.reliability)
    return p
