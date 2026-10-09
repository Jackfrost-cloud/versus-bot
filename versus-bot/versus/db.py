"""Schéma SQLite + import des données JSON (data/ puis custom/ en surcouche)."""
import json
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, universe TEXT NOT NULL,
  default_form TEXT, holds_back REAL DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS aliases(
  alias TEXT NOT NULL, character_id TEXT NOT NULL, PRIMARY KEY(alias, character_id));
CREATE TABLE IF NOT EXISTS forms(
  character_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, is_default INTEGER DEFAULT 0,
  PRIMARY KEY(character_id, id));
CREATE TABLE IF NOT EXISTS form_aliases(
  character_id TEXT NOT NULL, form_id TEXT NOT NULL, alias TEXT NOT NULL,
  PRIMARY KEY(character_id, form_id, alias));
CREATE TABLE IF NOT EXISTS ambiguous_aliases(
  character_id TEXT NOT NULL, alias TEXT NOT NULL, options TEXT NOT NULL,
  PRIMARY KEY(character_id, alias));
CREATE TABLE IF NOT EXISTS stats(
  character_id TEXT NOT NULL, form_id TEXT NOT NULL, stat TEXT NOT NULL,
  value REAL NOT NULL, confidence REAL NOT NULL, source TEXT NOT NULL,
  PRIMARY KEY(character_id, form_id, stat));
CREATE TABLE IF NOT EXISTS abilities(
  id TEXT NOT NULL, character_id TEXT NOT NULL, form_id TEXT, name TEXT NOT NULL,
  tags TEXT NOT NULL, range TEXT NOT NULL, requires TEXT NOT NULL,
  decisive REAL NOT NULL, cadence REAL NOT NULL, description TEXT,
  PRIMARY KEY(character_id, id));
CREATE TABLE IF NOT EXISTS feats(
  id TEXT PRIMARY KEY, character_id TEXT NOT NULL, form_id TEXT, category TEXT NOT NULL,
  description TEXT NOT NULL, value REAL NOT NULL, kind TEXT NOT NULL,
  source TEXT NOT NULL, confidence REAL NOT NULL);
CREATE TABLE IF NOT EXISTS resistances(
  character_id TEXT NOT NULL, form_id TEXT, tag TEXT NOT NULL, level REAL NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS weaknesses(
  character_id TEXT NOT NULL, form_id TEXT, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scaling(
  id INTEGER PRIMARY KEY AUTOINCREMENT, winner TEXT NOT NULL, loser TEXT NOT NULL,
  categories TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL,
  confidence REAL NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS sources(
  id TEXT PRIMARY KEY, type TEXT NOT NULL, title TEXT, url TEXT, priority INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS cache(
  key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL);
"""

REBUILD_TABLES = [
    "characters", "aliases", "forms", "form_aliases", "ambiguous_aliases", "stats", "abilities",
    "feats", "resistances", "weaknesses", "scaling", "sources",
]


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or config.DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _jload(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_json_dir(data_dir: Path, custom_dir: Path | None = None) -> dict:
    """Lit data/characters/*.json, data/relationships/*.json, data/sources/*.json + overlay custom/overlay.json."""
    out = {"characters": [], "scaling": [], "sources": []}
    for p in sorted((data_dir / "characters").glob("*.json")):
        out["characters"].extend(_jload(p))
    for p in sorted((data_dir / "relationships").glob("*.json")):
        out["scaling"].extend(_jload(p))
    sdir = data_dir / "sources"
    if sdir.exists():
        for p in sorted(sdir.glob("*.json")):
            out["sources"].extend(_jload(p))
    if custom_dir and (custom_dir / "overlay.json").exists():
        apply_overlay(out, _jload(custom_dir / "overlay.json"))
    return out


def apply_overlay(data: dict, ov: dict) -> None:
    """Fusionne un overlay (ajouts admin) dans les données de base."""
    by_id = {c["id"]: c for c in data["characters"]}
    for c in ov.get("characters", []):
        if c["id"] in by_id:
            data["characters"].remove(by_id[c["id"]])
        data["characters"].append(c)
        by_id[c["id"]] = c
    for f in ov.get("feats", []):
        ch = by_id.get(f.get("character"))
        if ch is not None:
            ch.setdefault("feats", []).append({k: v for k, v in f.items() if k != "character"})
    for a in ov.get("abilities", []):
        ch = by_id.get(a.get("character"))
        if ch is not None:
            ch.setdefault("abilities", []).append({k: v for k, v in a.items() if k != "character"})
    for fm in ov.get("forms", []):
        ch = by_id.get(fm.get("character"))
        if ch is not None:
            ch.setdefault("forms", []).append({k: v for k, v in fm.items() if k != "character"})
    data["scaling"].extend(ov.get("scaling", []))
    data["sources"].extend(ov.get("sources", []))


def build_database(path: Path | str | None = None, data_dir: Path | None = None,
                   custom_dir: Path | None = None) -> sqlite3.Connection:
    """(Re)construit les tables de connaissances depuis les JSON. Le cache est conservé."""
    con = connect(path)
    data = load_json_dir(data_dir or config.DATA_DIR, custom_dir if custom_dir is not None else config.CUSTOM_DIR)
    with con:
        for t in REBUILD_TABLES:
            con.execute(f"DELETE FROM {t}")
        for s in data["sources"]:
            con.execute("INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)",
                        (s["id"], s["type"], s.get("title"), s.get("url"),
                         s.get("priority", config.SOURCE_PRIORITY.get(s["type"], 1))))
        for c in data["characters"]:
            _insert_character(con, c)
        for r in data["scaling"]:
            con.execute(
                "INSERT INTO scaling(winner,loser,categories,kind,source,confidence,note) VALUES(?,?,?,?,?,?,?)",
                (r["winner"], r["loser"], json.dumps(r.get("categories", ["overall"])),
                 r.get("kind", "defeated"), json.dumps(r.get("source", {})),
                 r.get("confidence", 0.8), r.get("note")))
    return con


def _insert_character(con, c: dict) -> None:
    forms = c["forms"]
    default = next((f["id"] for f in forms if f.get("default")), forms[0]["id"])
    con.execute("INSERT OR REPLACE INTO characters VALUES(?,?,?,?,?,?)",
                (c["id"], c["name"], c["universe"], default, c.get("holds_back", 0.0), c.get("notes")))
    for a in {c["id"], c["name"], *c.get("aliases", [])}:
        con.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?)" if False else
                    "INSERT OR IGNORE INTO aliases(alias, character_id) VALUES(?,?)", (norm(a), c["id"]))
    for alias, opts in c.get("ambiguous_aliases", {}).items():
        con.execute("INSERT OR REPLACE INTO ambiguous_aliases VALUES(?,?,?)",
                    (c["id"], norm(alias), json.dumps(opts)))
    est_src = {"type": "estimation", "title": "Estimation de l'auteur de la base (à relire)"}
    for f in forms:
        con.execute("INSERT OR REPLACE INTO forms VALUES(?,?,?,?)",
                    (c["id"], f["id"], f["name"], 1 if f["id"] == default else 0))
        for a in {f["id"].replace("_", " "), f["name"], *f.get("aliases", [])}:
            con.execute("INSERT OR IGNORE INTO form_aliases VALUES(?,?,?)", (c["id"], f["id"], norm(a)))
        vals = f.get("stats", [])
        for stat, v in zip(config.STATS, vals):
            if v is None:
                continue
            con.execute("INSERT OR REPLACE INTO stats VALUES(?,?,?,?,?,?)",
                        (c["id"], f["id"], stat, float(v), f.get("stats_confidence", 0.8),
                         json.dumps(f.get("stats_source", est_src))))
    for ab in c.get("abilities", []):
        con.execute("INSERT OR REPLACE INTO abilities VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (ab["id"], c["id"], ab.get("form"), ab["name"], json.dumps(ab.get("tags", [])),
                     ab.get("range", "mid"), ab.get("requires", "none"), ab.get("decisive", 0.0),
                     ab.get("cadence", 0.5), ab.get("description")))
    for ft in c.get("feats", []):
        con.execute("INSERT OR REPLACE INTO feats VALUES(?,?,?,?,?,?,?,?,?)",
                    (ft["id"], c["id"], ft.get("form"), ft["category"], ft["description"],
                     float(ft["value"]), ft.get("kind", "feat"), json.dumps(ft.get("source", {})),
                     ft.get("confidence", 0.8)))
    for tag, level in c.get("resistances", {}).items():
        con.execute("INSERT INTO resistances VALUES(?,?,?,?,?)", (c["id"], None, tag, float(level), None))
    for fid, res in c.get("form_resistances", {}).items():
        for tag, level in res.items():
            con.execute("INSERT INTO resistances VALUES(?,?,?,?,?)", (c["id"], fid, tag, float(level), None))
    for w in c.get("weaknesses", []):
        con.execute("INSERT INTO weaknesses VALUES(?,?,?)", (c["id"], None, w))


def norm(s: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()
