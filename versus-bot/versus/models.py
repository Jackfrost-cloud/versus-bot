from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import SOURCE_PRIORITY


@dataclass
class Source:
    type: str = "unverified"
    work: str = ""
    reference: str = ""
    url: str = ""
    verified: bool = False

    @property
    def priority(self) -> int:
        return SOURCE_PRIORITY.get(self.type, 1)

    def label(self) -> str:
        base = " — ".join(p for p in (self.work, self.reference) if p) or self.url or self.type
        flag = "" if self.verified else ", non vérifié"
        return f"{base} [{self.type}, prio {self.priority}{flag}]"

    @classmethod
    def from_dict(cls, d) -> "Source":
        d = d or {}
        return cls(d.get("type", "unverified"), d.get("work", ""),
                   d.get("reference", d.get("ref", "")), d.get("url", ""),
                   bool(d.get("verified", False)))

    def to_dict(self) -> dict:
        return {"type": self.type, "work": self.work, "reference": self.reference,
                "url": self.url, "verified": self.verified}


@dataclass
class Feat:
    id: str
    character: str
    form: str
    category: str
    value: float
    kind: str
    description: str
    source: Source
    confidence: float


@dataclass
class Ability:
    id: str
    character: str
    name: str
    forms: list
    tags: list
    potency: float
    reliability: float
    win_type: str
    hax: bool
    needs_contact: bool
    bypasses: list
    description: str
    confidence: float
    source: Source


@dataclass
class Resistance:
    character: str
    forms: list
    tag: str
    level: float
    via: str
    note: str
    confidence: float


@dataclass
class Weakness:
    character: str
    forms: list
    tag: str
    severity: float
    note: str


@dataclass
class Form:
    id: str
    character: str
    name: str
    inherits: list
    description: str = ""


@dataclass
class Character:
    id: str
    name: str
    short: str
    universe: str
    default_form: str
    data_status: str
    forms: dict
    feats: list = field(default_factory=list)
    abilities: list = field(default_factory=list)
    resistances: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)
    equipment: list = field(default_factory=list)

    def form_chain(self, form_id: str) -> list:
        """[(form_id, profondeur)] de la forme vers ses ancêtres."""
        out, seen, frontier, depth = [], set(), [form_id], 0
        while frontier:
            nxt = []
            for f in frontier:
                if f in seen or f not in self.forms:
                    continue
                seen.add(f)
                out.append((f, depth))
                nxt.extend(self.forms[f].inherits)
            frontier, depth = nxt, depth + 1
        return out

    def available(self, forms: list, form_id: str) -> bool:
        if not forms or "*" in forms:
            return True
        ids = {f for f, _ in self.form_chain(form_id)}
        return any(f in ids for f in forms)


@dataclass
class Relation:
    id: str
    a: str          # "personnage:forme"
    b: str
    category: str
    relation: str   # ">" ou "="
    kind: str
    confidence: float
    description: str
    source: Source


@dataclass
class Route:
    name: str
    kind: str       # physical | attrition | hax
    p: float
    note: str = ""
    via: str = ""


@dataclass
class Conditions:
    mode: str = "standard"      # standard | equalized | equalized_energy
    bloodlusted: bool = False
    deathmatch: bool = False
    detailed: bool = False

    def describe(self) -> str:
        parts = {"standard": "standard (sans égalisation)", "equalized": "stats égalisées",
                 "equalized_energy": "énergie égalisée"}[self.mode]
        if self.bloodlusted:
            parts += ", bloodlusted"
        if self.deathmatch:
            parts += ", combat à mort"
        return parts
