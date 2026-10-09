"""Base SQLite : schéma, import JSON idempotent, chargement des modèles, cache."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .models import (Ability, Character, Feat, Form, Relation, Resistance, Source, Weakness)
from .text import norm

SCHEMA = """
CREATE TABLE IF NOT EXISTS universes(id TEXT PRIMARY KEY, name TEXT, energy TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS characters(id TEXT PRIMARY KEY, name TEXT, short TEXT, universe TEXT,
  default_form TEXT, data_status TEXT, equipment TEXT);
CREATE TABLE IF NOT EXISTS forms(character TEXT, id TEXT, name TEXT, inherits TEXT, description TEXT,
  PRIMARY KEY(character, id));
CREATE TABLE IF NOT EXISTS aliases(alias TEXT, character TEXT, form TEXT DEFAULT '',
  PRIMARY KEY(alias, character, form));
CREATE TABLE IF NOT EXISTS abilities(id TEXT, character TEXT, name TEXT, forms TEXT, tags TEXT,
  potency REAL, reliability REAL, win_type TEXT, hax INTEGER, needs_contact INTEGER, bypasses TEXT,
  description TEXT, confidence REAL, source TEXT, PRIMARY KEY(character, id));
CREATE TABLE IF NOT EXISTS feats(id TEXT, character TEXT, form TEXT, category TEXT, value REAL,
  kind TEXT, description TEXT, confidence REAL, source TEXT, PRIMARY KEY(character, id));
CREATE TABLE IF NOT EXISTS resistances(character TEXT, forms TEXT, tag TEXT, level REAL, via TEXT,
  note TEXT, confidence REAL);
CREATE TABLE IF NOT EXISTS weaknesses(character TEXT, forms TEXT, tag TEXT, severity REAL, note TEXT);
CREATE TABLE IF NOT EXISTS scaling(id TEXT PRIMARY KEY, a TEXT, b TEXT, category TEXT, relation TEXT,
  kind TEXT, confidence REAL, description TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS sources(character TEXT, type TEXT, priority INTEGER, work TEXT,
  reference TEXT, url TEXT, verified INTEGER);
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, payload TEXT, fetched_at REAL);
"""


def _j(v):
    return json.dumps(v if v is not None else [], ensure_ascii=False)


class Database:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.conn.executescript(SCHEMA)
        self._chars: dict = {}

    # ---------------------------------------------------------------- import
    def import_payload(self, payload) -> dict:
        counts = {"characters": 0, "relations": 0, "universes": 0}
        with self.lock, self.conn:
            if isinstance(payload, list):
                payload = {"characters": payload}
            if "id" in payload and "name" in payload:
                payload = {"characters": [payload]}
            for c in payload.get("characters", []):
                self._import_character(c)
                counts["characters"] += 1
            for r in payload.get("relations", []):
                self._import_relation(r)
                counts["relations"] += 1
            for u in payload.get("universes", []):
                self.conn.execute("INSERT OR REPLACE INTO universes VALUES(?,?,?,?)",
                                  (u["id"], u.get("name", u["id"]), u.get("energy", ""), u.get("note", "")))
                counts["universes"] += 1
        self._chars.clear()
        return counts

    def import_file(self, path) -> dict:
        return self.import_payload(json.loads(Path(path).read_text(encoding="utf-8")))

    def import_dir(self, root) -> dict:
        total = {"characters": 0, "relations": 0, "universes": 0}
        root = Path(root)
        if not root.exists():
            return total
        for f in sorted(root.rglob("*.json")):
            for k, v in self.import_file(f).items():
                total[k] += v
        return total

    def _import_character(self, c: dict):
        cid, cx = c["id"], self.conn
        for t in ("forms", "aliases", "abilities", "feats", "resistances", "weaknesses", "sources"):
            cx.execute(f"DELETE FROM {t} WHERE character=?", (cid,))
        forms = c.get("forms") or [{"id": "base", "name": ""}]
        default = c.get("default_form") or forms[0]["id"]
        cx.execute("INSERT OR REPLACE INTO characters VALUES(?,?,?,?,?,?,?)",
                   (cid, c["name"], c.get("short", c["name"]), c.get("universe", ""), default,
                    c.get("data_status", "draft"), _j(c.get("equipment"))))
        aliases = {(norm(c["name"]), ""), (norm(cid.replace("_", " ")), "")}
        aliases |= {(norm(a), "") for a in c.get("aliases", [])}
        for f in forms:
            cx.execute("INSERT INTO forms VALUES(?,?,?,?,?)",
                       (cid, f["id"], f.get("name", ""), _j(f.get("inherits")), f.get("description", "")))
            aliases |= {(norm(a), f["id"]) for a in f.get("aliases", [])}
        for a, f in aliases:
            if a:
                cx.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?)", (a, cid, f))
        seen_src = set()

        def reg(src: dict):
            s = Source.from_dict(src)
            key = (s.type, s.work, s.reference, s.url)
            if key not in seen_src:
                seen_src.add(key)
                cx.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?)",
                           (cid, s.type, s.priority, s.work, s.reference, s.url, int(s.verified)))

        for a in c.get("abilities", []):
            cx.execute("INSERT INTO abilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (a["id"], cid, a["name"], _j(a.get("forms", ["*"])), _j(a.get("tags")),
                        a.get("potency", 0.5), a.get("reliability", 0.5), a.get("win_type", "none"),
                        int(a.get("hax", False)), int(a.get("needs_contact", False)),
                        _j(a.get("bypasses")), a.get("description", ""), a.get("confidence", 0.5),
                        json.dumps(a.get("source", {}))))
            reg(a.get("source", {}))
        for f in c.get("feats", []):
            cx.execute("INSERT INTO feats VALUES(?,?,?,?,?,?,?,?,?)",
                       (f["id"], cid, f.get("form", "*"), f["category"], f["value"], f["kind"],
                        f.get("description", ""), f.get("confidence", 0.5), json.dumps(f.get("source", {}))))
            reg(f.get("source", {}))
        for r in c.get("resistances", []):
            cx.execute("INSERT INTO resistances VALUES(?,?,?,?,?,?,?)",
                       (cid, _j(r.get("forms", ["*"])), r["tag"], r["level"], r.get("via", ""),
                        r.get("note", ""), r.get("confidence", 0.5)))
        for w in c.get("weaknesses", []):
            cx.execute("INSERT INTO weaknesses VALUES(?,?,?,?,?)",
                       (cid, _j(w.get("forms", ["*"])), w["tag"], w.get("severity", 0.3), w.get("note", "")))

    def _import_relation(self, r: dict):
        self.conn.execute("INSERT OR REPLACE INTO scaling VALUES(?,?,?,?,?,?,?,?,?)",
                          (r["id"], r["a"], r["b"], r["category"], r.get("relation", ">"),
                           r.get("kind", "statement"), r.get("confidence", 0.5),
                           r.get("description", ""), json.dumps(r.get("source", {}))))

    # ---------------------------------------------------------------- lecture
    def character_ids(self) -> list:
        with self.lock:
            return [r["id"] for r in self.conn.execute("SELECT id FROM characters ORDER BY id")]

    def get_character(self, cid: str):
        if cid in self._chars:
            return self._chars[cid]
        with self.lock:
            cx = self.conn
            row = cx.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone()
            if not row:
                return None
            forms = {r["id"]: Form(r["id"], cid, r["name"], json.loads(r["inherits"]), r["description"])
                     for r in cx.execute("SELECT * FROM forms WHERE character=?", (cid,))}
            ch = Character(cid, row["name"], row["short"], row["universe"], row["default_form"],
                           row["data_status"], forms, equipment=json.loads(row["equipment"]))
            for r in cx.execute("SELECT * FROM feats WHERE character=?", (cid,)):
                ch.feats.append(Feat(r["id"], cid, r["form"], r["category"], r["value"], r["kind"],
                                     r["description"], Source.from_dict(json.loads(r["source"])),
                                     r["confidence"]))
            for r in cx.execute("SELECT * FROM abilities WHERE character=?", (cid,)):
                ch.abilities.append(Ability(r["id"], cid, r["name"], json.loads(r["forms"]),
                                            json.loads(r["tags"]), r["potency"], r["reliability"],
                                            r["win_type"], bool(r["hax"]), bool(r["needs_contact"]),
                                            json.loads(r["bypasses"]), r["description"], r["confidence"],
                                            Source.from_dict(json.loads(r["source"]))))
            for r in cx.execute("SELECT * FROM resistances WHERE character=?", (cid,)):
                ch.resistances.append(Resistance(cid, json.loads(r["forms"]), r["tag"], r["level"],
                                                 r["via"], r["note"], r["confidence"]))
            for r in cx.execute("SELECT * FROM weaknesses WHERE character=?", (cid,)):
                ch.weaknesses.append(Weakness(cid, json.loads(r["forms"]), r["tag"], r["severity"], r["note"]))
        self._chars[cid] = ch
        return ch

    def alias_index(self) -> dict:
        idx: dict = {}
        with self.lock:
            for r in self.conn.execute("SELECT alias, character, form FROM aliases"):
                idx.setdefault(r["alias"], set()).add((r["character"], r["form"] or None))
        return idx

    def relations(self) -> list:
        with self.lock:
            return [Relation(r["id"], r["a"], r["b"], r["category"], r["relation"], r["kind"],
                             r["confidence"], r["description"], Source.from_dict(json.loads(r["source"])))
                    for r in self.conn.execute("SELECT * FROM scaling")]

    def sources_of(self, cid: str) -> list:
        with self.lock:
            return [Source(r["type"], r["work"], r["reference"], r["url"], bool(r["verified"]))
                    for r in self.conn.execute(
                        "SELECT * FROM sources WHERE character=? ORDER BY priority DESC, work, reference", (cid,))]

    # ---------------------------------------------------------------- cache
    def cache_get(self, key: str, ttl_days: int):
        with self.lock:
            r = self.conn.execute("SELECT payload, fetched_at FROM cache WHERE key=?", (key,)).fetchone()
        if r and time.time() - r["fetched_at"] < ttl_days * 86400:
            return json.loads(r["payload"])
        return None

    def cache_set(self, key: str, payload):
        with self.lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)",
                              (key, json.dumps(payload, ensure_ascii=False), time.time()))
