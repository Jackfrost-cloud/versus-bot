"""Parser déterministe : question -> deux côtés + conditions ; résolution des alias."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional

from .models import Conditions
from .text import norm

COND_PATTERNS = [
    ("equalized_energy", r"(?:avec )?(?:egalisation (?:de l )?energie|equali[sz]ed energy|energie egalisee)"),
    ("no_eq", r"(?:sans egalisation|no equali[sz]ation|non equali[sz]ed|unequali[sz]ed)"),
    ("equalized", r"(?:avec )?(?:egalisation(?: des)?(?: pouvoirs| stats| statistiques| puissances)?"
                  r"|equali[sz]ed(?: stats)?|egalise[es]?)"),
    ("bloodlusted", r"blood ?lust(?:ed)?"),
    ("deathmatch", r"(?:dans un )?(?:combat )?(?:a mort|mortel)|to the death|death ?match"),
    ("detailed", r"\b(?:detailed|detaille|detail|details|approfondi|complet)\b"),
]
VS_RE = re.compile(r"^(.*?)\s+(?:vs|versus|contre|v)\s+(.*)$")
ENTRE_RE = re.compile(r"\bentre\s+(.*?)\s+et\s+(.*)$")
OU_RE = re.compile(r"^(.*?)\s+ou\s+(.*)$")


@dataclass
class Question:
    raw: str
    a: str
    b: str
    cond: Conditions


def extract_conditions(text: str):
    t = norm(text)
    cond = Conditions()
    for key, pat in COND_PATTERNS:
        if re.search(pat, t):
            t = re.sub(pat, " ", t)
            if key == "equalized_energy":
                cond.mode = "equalized_energy"
            elif key == "equalized" and cond.mode == "standard":
                cond.mode = "equalized"
            elif key == "bloodlusted":
                cond.bloodlusted = True
            elif key == "deathmatch":
                cond.deathmatch = True
            elif key == "detailed":
                cond.detailed = True
    return re.sub(r"\s+", " ", t).strip(), cond


def parse_question(text: str) -> Optional[Question]:
    t, cond = extract_conditions(text)
    for rx in (ENTRE_RE, VS_RE, OU_RE):
        m = rx.search(t) if rx is ENTRE_RE else rx.match(t)
        if m and m.group(1).strip() and m.group(2).strip():
            return Question(text, m.group(1).strip(), m.group(2).strip(), cond)
    return None


@dataclass
class Resolution:
    status: str                     # ok | unknown | ambiguous
    character: Optional[str] = None
    form: Optional[str] = None
    matched: str = ""
    candidates: list = field(default_factory=list)


class Resolver:
    def __init__(self, index: dict):
        self.index = index
        self.aliases = sorted(index, key=len, reverse=True)
        self._pats = {a: re.compile(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])") for a in self.aliases}

    def matches(self, text: str) -> list:
        out = []
        for a in self.aliases:
            for m in self._pats[a].finditer(text):
                out.append((a, m.start(), m.end()))
        return out

    def resolve(self, text: str) -> Resolution:
        t = norm(text)
        ms = self.matches(t)
        if not ms:
            ms = self._fuzzy(t)
        if not ms:
            return Resolution("unknown", matched=t)
        char_ms = [m for m in ms if any(f is None for _, f in self.index[m[0]])]
        if char_ms:
            best = max(len(m[0]) for m in char_ms)
            chars = {c for m in char_ms if len(m[0]) == best for c, f in self.index[m[0]] if f is None}
            if len(chars) > 1:
                return Resolution("ambiguous", candidates=sorted(chars), matched=t)
            char = next(iter(chars))
            form = None
            fm = [(len(m[0]), f) for m in ms for c, f in self.index[m[0]] if c == char and f]
            if fm:
                form = max(fm)[1]
            return Resolution("ok", char, form, t)
        best = max(len(m[0]) for m in ms)
        entries = {e for m in ms if len(m[0]) == best for e in self.index[m[0]]}
        chars = {c for c, _ in entries}
        if len(chars) > 1:
            return Resolution("ambiguous", candidates=sorted(chars), matched=t)
        c, f = sorted(entries, key=lambda e: e[1] or "")[0]
        return Resolution("ok", c, f, t)

    def _fuzzy(self, t: str) -> list:
        toks = t.split()
        best = None
        for n in (1, 2, 3):
            for i in range(len(toks) - n + 1):
                w = " ".join(toks[i:i + n])
                if len(w) < 4:
                    continue
                for cand in difflib.get_close_matches(w, self.aliases, n=1, cutoff=0.84):
                    r = difflib.SequenceMatcher(None, w, cand).ratio()
                    if best is None or (r, len(cand)) > best[0]:
                        best = ((r, len(cand)), cand)
        return [(best[1], 0, 0)] if best else []

    def split_two(self, text: str):
        """Pour !compare : deux personnages dans une chaîne sans séparateur."""
        t = norm(text)
        parts = re.split(r"\s+(?:vs|versus|contre|et|and)\s+", t)
        if len(parts) == 2:
            return parts[0], parts[1]
        char_ms = sorted((m for m in self.matches(t) if any(f is None for _, f in self.index[m[0]])),
                         key=lambda m: m[1])
        firsts = []
        for m in char_ms:
            if not any(m[1] < e and m[2] > s for _, s, e in firsts):
                firsts.append(m)
        if len(firsts) >= 2:
            cut = firsts[1][1]
            return t[:cut].strip(), t[cut:].strip()
        return None
