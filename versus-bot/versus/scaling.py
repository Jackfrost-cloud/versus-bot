"""Graphe de scaling par catégorie : A > B en vitesse n'implique rien en force."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .config import SCALING_CATEGORIES, STAT_CATEGORIES
from .models import Feat, Relation

HOP_DECAY = 0.85
MAX_HOPS = 3
MARGIN = 3.0


@dataclass
class ClosureItem:
    conf: float
    strict: bool
    hops: int
    rels: list


class ScalingGraph:
    def __init__(self, relations: list):
        self.by_cat = defaultdict(list)
        for r in relations:
            self.by_cat[r.category].append(r)
        self._cl: dict = {}

    def closure(self, cat: str) -> dict:
        if cat in self._cl:
            return self._cl[cat]
        adj = defaultdict(list)
        for r in self.by_cat.get(cat, []):
            adj[r.a].append((r.b, r.confidence, r.relation == ">", r))
            if r.relation == "=":
                adj[r.b].append((r.a, r.confidence, False, r))
        out: dict = {}

        def dfs(start, node, conf, strict, hops, seen, rels):
            for nxt, c, st, r in adj.get(node, []):
                if nxt in seen:
                    continue
                cc = conf * c * (HOP_DECAY if hops else 1.0)
                key = (start, nxt)
                cur = out.get(key)
                if cur is None or cc > cur.conf:
                    out[key] = ClosureItem(cc, strict or st, hops + 1, rels + [r])
                if hops + 1 < MAX_HOPS:
                    dfs(start, nxt, cc, strict or st, hops + 1, seen | {nxt}, rels + [r])

        nodes = {r.a for r in self.by_cat.get(cat, [])} | {r.b for r in self.by_cat.get(cat, [])}
        for s in nodes:
            dfs(s, s, 1.0, False, 0, {s}, [])
        self._cl[cat] = out
        return out

    def derived_feats(self, character: str, form: str, base_lookup) -> list:
        """Feats implicites : si A > B en catégorie c, A >= valeur(B)+marge en c."""
        node, feats = f"{character}:{form}", []
        for cat in STAT_CATEGORIES:
            for (a, b), item in self.closure(cat).items():
                if a != node:
                    continue
                base = (base_lookup(b) or {}).get(cat)
                if not base:
                    continue
                rel = item.rels[0]
                feats.append(Feat(
                    f"scaling:{a}>{b}:{cat}", character, form, cat,
                    min(100.0, base.value + (MARGIN if item.strict else 0.0)), "scaling",
                    f"Scale à {b} ({cat}) via {len(item.rels)} relation(s)", rel.source,
                    round(item.conf * base.confidence, 3)))
        return feats

    def between(self, a: str, b: str) -> list:
        """[(catégorie, texte, conf, hops, relations)] entre deux nœuds (directs ou transitifs)."""
        out = []
        for cat in SCALING_CATEGORIES:
            cl = self.closure(cat)
            for x, y in ((a, b), (b, a)):
                it = cl.get((x, y))
                if it:
                    sym = ">" if it.strict else "="
                    out.append((cat, f"{x} {sym} {y}", it.conf, it.hops, it.rels))
                    if sym == "=":
                        break
        return out

    def cycles(self) -> list:
        res = []
        for cat, rels in self.by_cat.items():
            adj = defaultdict(list)
            for r in rels:
                if r.relation == ">":
                    adj[r.a].append(r.b)
            state: dict = {}

            def visit(n, stack):
                state[n] = 1
                for m in adj.get(n, []):
                    if state.get(m) == 1:
                        res.append((cat, stack[stack.index(m):] + [m] if m in stack else [n, m]))
                    elif state.get(m) is None:
                        visit(m, stack + [m])
                state[n] = 2

            for n in list(adj):
                if state.get(n) is None:
                    visit(n, [n])
        return res
