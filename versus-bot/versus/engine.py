"""Façade du moteur : indépendante de Discord (utilisable en CLI, API, site)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import confidence as conf
from .database import Database
from .models import Conditions
from .parser import Resolution, Resolver, parse_question
from .scaling import ScalingGraph
from .simulation import Simulation, simulate
from .stats import Profile, build_profile


@dataclass
class VersusResult:
    a: Profile
    b: Profile
    a_default: bool
    b_default: bool
    cond: Conditions
    sim: Simulation
    confidence: conf.Confidence
    relations: list = field(default_factory=list)

    @property
    def p_a(self) -> float:
        return self.sim.p_a

    @property
    def winner(self) -> Profile:
        return self.a if self.p_a >= 0.5 else self.b


@dataclass
class Answer:
    kind: str                  # result | ambiguous | unknown | usage
    result: VersusResult | None = None
    unknown: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    message: str = ""


class Engine:
    def __init__(self, db: Database):
        self.db = db
        self.reload()

    def reload(self):
        self.db._chars.clear()
        self.resolver = Resolver(self.db.alias_index())
        self.graph = ScalingGraph(self.db.relations())
        self._base: dict = {}

    # -------------------------------------------------------------- profils
    def _pure(self, node: str):
        if node not in self._base:
            cid, fid = node.split(":")
            ch = self.db.get_character(cid)
            self._base[node] = build_profile(ch, fid).stats if ch and fid in ch.forms else {}
        return self._base[node]

    def profile(self, cid: str, form_id: str | None = None) -> Profile | None:
        ch = self.db.get_character(cid)
        if not ch:
            return None
        fid = form_id if form_id in ch.forms else ch.default_form
        extra = self.graph.derived_feats(cid, fid, self._pure)
        return build_profile(ch, fid, extra)

    # -------------------------------------------------------------- versus
    def versus(self, ra: Resolution, rb: Resolution, cond: Conditions) -> VersusResult:
        a, b = self.profile(ra.character, ra.form), self.profile(rb.character, rb.form)
        sim = simulate(a, b, cond)
        return VersusResult(a, b, ra.form is None, rb.form is None, cond, sim,
                            conf.compute(a, b, sim.p_a), self.graph.between(a.node, b.node))

    def ask(self, text: str) -> Answer:
        q = parse_question(text)
        if not q:
            return Answer("usage", message="Format : « Naruto vs Luffy » (options : bloodlusted, "
                                           "avec égalisation, combat à mort, detailed).")
        ra, rb = self.resolver.resolve(q.a), self.resolver.resolve(q.b)
        unknown = [r.matched or s for r, s in ((ra, q.a), (rb, q.b)) if r.status == "unknown"]
        if unknown:
            return Answer("unknown", unknown=unknown)
        for r in (ra, rb):
            if r.status == "ambiguous":
                return Answer("ambiguous", candidates=[self.db.get_character(c).name for c in r.candidates])
        if ra.character == rb.character and ra.form == rb.form:
            return Answer("usage", message="Choisis deux personnages (ou deux formes) différents.")
        return Answer("result", result=self.versus(ra, rb, q.cond))
