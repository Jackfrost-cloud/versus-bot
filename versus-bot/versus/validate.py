"""Validation des données JSON (sans base) : sources, références, doublons, cycles, valeurs."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .config import (FEAT_KINDS, KNOWN_TAGS, RELATIONS, SCALING_CATEGORIES, SOURCE_PRIORITY,
                     STAT_CATEGORIES, WIN_TYPES)
from .models import Relation, Source
from .scaling import ScalingGraph
from .text import norm


@dataclass
class Issue:
    level: str     # error | warn
    where: str
    msg: str

    def __str__(self):
        return f"[{self.level.upper()}] {self.where}: {self.msg}"


def load_dir(root) -> list:
    out = []
    for f in sorted(Path(root).rglob("*.json")) if Path(root).exists() else []:
        out.append((str(f), json.loads(f.read_text(encoding="utf-8"))))
    return out


def _norm_payload(p):
    if isinstance(p, list):
        return {"characters": p}
    if "id" in p and "name" in p:
        return {"characters": [p]}
    return p


def validate_payloads(payloads: list, known_nodes: set | None = None) -> list:
    issues = []
    chars, relations = {}, []
    aliases = defaultdict(set)
    for name, p in payloads:
        p = _norm_payload(p)
        for c in p.get("characters", []):
            if c["id"] in chars:
                issues.append(Issue("error", c["id"], f"doublon de personnage (aussi dans {name})"))
            chars[c["id"]] = c
        relations += [(name, r) for r in p.get("relations", [])]

    for cid, c in chars.items():
        forms = {f["id"] for f in c.get("forms", [])} or {"base"}
        if c.get("default_form", next(iter(forms))) not in forms:
            issues.append(Issue("error", cid, "default_form inexistante"))
        for f in c.get("forms", []):
            for parent in f.get("inherits", []):
                if parent not in forms:
                    issues.append(Issue("error", cid, f"forme {f['id']} hérite d'une forme inconnue : {parent}"))
        for a in {norm(x) for x in c.get("aliases", [])} | {norm(c["name"])}:
            aliases[(a, "")].add(cid)
        for f in c.get("forms", []):
            for a in f.get("aliases", []):
                aliases[(norm(a), f["id"])].add(cid)
        feats = c.get("feats", [])
        if not feats:
            issues.append(Issue("error", cid, "aucun feat"))
        if not any(f.get("source", {}).get("type") for f in feats):
            issues.append(Issue("error", cid, "personnage sans source"))
        seen = set()
        for f in feats:
            w = f"{cid}/{f.get('id', '?')}"
            if f.get("id") in seen:
                issues.append(Issue("error", w, "id de feat dupliqué"))
            seen.add(f.get("id"))
            if not f.get("category"):
                issues.append(Issue("error", w, "feat sans catégorie"))
            elif f["category"] not in STAT_CATEGORIES:
                issues.append(Issue("error", w, f"catégorie inconnue : {f['category']}"))
            if f.get("kind") not in FEAT_KINDS:
                issues.append(Issue("error", w, f"type de feat invalide : {f.get('kind')}"))
            if f.get("form", "*") not in forms and f.get("form", "*") != "*":
                issues.append(Issue("error", w, f"forme inexistante : {f.get('form')}"))
            if not 0 <= f.get("value", -1) <= 100:
                issues.append(Issue("error", w, "valeur hors de [0, 100]"))
            if not 0 <= f.get("confidence", -1) <= 1:
                issues.append(Issue("error", w, "confiance hors de [0, 1]"))
            if not f.get("source", {}).get("type"):
                issues.append(Issue("error", w, "feat sans source"))
            elif f["source"]["type"] not in SOURCE_PRIORITY:
                issues.append(Issue("error", w, f"type de source inconnu : {f['source']['type']}"))
        by_form = defaultdict(dict)
        for f in feats:
            by_form[f.get("form", "*")].setdefault(f.get("category"), []).append(f.get("value", 0))
        for fm, cats in by_form.items():
            s, r = cats.get("speed"), cats.get("reaction_speed")
            if s and r and abs(max(s) - max(r)) > 40:
                issues.append(Issue("warn", f"{cid}/{fm}", "vitesse et réflexes très éloignées (>40)"))
        ab_ids = set()
        for a in c.get("abilities", []):
            w = f"{cid}/ability:{a.get('id', '?')}"
            if a.get("id") in ab_ids:
                issues.append(Issue("error", w, "id de capacité dupliqué"))
            ab_ids.add(a.get("id"))
            if a.get("win_type", "none") not in WIN_TYPES:
                issues.append(Issue("error", w, "win_type invalide"))
            for k in ("potency", "reliability", "confidence"):
                if not 0 <= a.get(k, 0.5) <= 1:
                    issues.append(Issue("error", w, f"{k} hors de [0, 1]"))
            for t in a.get("tags", []) + a.get("bypasses", []):
                if t not in KNOWN_TAGS:
                    issues.append(Issue("error", w, f"tag inconnu : {t}"))
            for fm in a.get("forms", ["*"]):
                if fm != "*" and fm not in forms:
                    issues.append(Issue("error", w, f"forme inexistante : {fm}"))
        for r in c.get("resistances", []):
            w = f"{cid}/resistance:{r.get('tag')}"
            if r.get("tag") not in KNOWN_TAGS:
                issues.append(Issue("error", w, "tag inconnu"))
            if not 0 <= r.get("level", -1) <= 1:
                issues.append(Issue("error", w, "niveau hors de [0, 1]"))
            if r.get("via") and r["via"] not in ab_ids:
                issues.append(Issue("error", w, f"capacité 'via' inexistante : {r['via']}"))
        for wk in c.get("weaknesses", []):
            if wk.get("tag") not in KNOWN_TAGS:
                issues.append(Issue("warn", f"{cid}/weakness", f"tag inconnu : {wk.get('tag')}"))

    for (alias, form), owners in aliases.items():
        if len(owners) > 1 and form:
            issues.append(Issue("error", alias, f"alias de forme contradictoire : {sorted(owners)}"))
        elif len(owners) > 1:
            issues.append(Issue("warn", alias, f"alias partagé entre personnages : {sorted(owners)}"))

    nodes = {f"{cid}:{f['id']}" for cid, c in chars.items() for f in (c.get("forms") or [{"id": "base"}])}
    nodes |= known_nodes or set()
    rels, rel_ids = [], set()
    for name, r in relations:
        w = f"relation:{r.get('id', '?')}"
        if r.get("id") in rel_ids:
            issues.append(Issue("error", w, "id dupliqué"))
        rel_ids.add(r.get("id"))
        for k in ("a", "b"):
            if r.get(k) not in nodes:
                issues.append(Issue("error", w, f"référence inexistante : {r.get(k)}"))
        if r.get("category") not in SCALING_CATEGORIES:
            issues.append(Issue("error", w, f"catégorie inconnue : {r.get('category')}"))
        if r.get("relation", ">") not in RELATIONS:
            issues.append(Issue("error", w, "relation invalide"))
        if not r.get("source", {}).get("type"):
            issues.append(Issue("error", w, "relation sans source"))
        else:
            rels.append(Relation(r["id"], r["a"], r["b"], r["category"], r.get("relation", ">"),
                                 r.get("kind", "statement"), r.get("confidence", 0.5),
                                 r.get("description", ""), Source.from_dict(r["source"])))
    for cat, cyc in ScalingGraph(rels).cycles():
        issues.append(Issue("warn", f"scaling/{cat}", "relation circulaire suspecte : " + " > ".join(cyc)))
    return issues


def validate_dirs(*dirs) -> list:
    payloads = []
    for d in dirs:
        payloads += load_dir(d)
    return validate_payloads(payloads)
