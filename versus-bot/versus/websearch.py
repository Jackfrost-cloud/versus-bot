"""Recherche web classique, SANS IA : Wikipedia (API publique). Information seulement,
jamais utilisée dans le calcul sans validation (priorité de source 5 = wiki)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "VersusBot/1.0 (open-source versus analysis; no AI)"}


def _get(url: str, timeout: float = 5.0):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(name: str):
    q = urllib.parse.quote(name)
    for lang in ("fr", "en"):
        try:
            data = _get(f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
                        f"&srsearch={q}&srlimit=1&format=json")
            hits = data.get("query", {}).get("search", [])
            if not hits:
                continue
            title = hits[0]["title"]
            s = _get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
                     f"{urllib.parse.quote(title.replace(' ', '_'))}")
            return {"title": title, "url": s.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "extract": (s.get("extract") or "")[:300], "source_type": "wiki", "priority": 5}
        except Exception:
            continue
    return None


def lookup(db, name: str, ttl_days: int = 30, fetcher=fetch):
    key = f"web:{name.lower().strip()}"
    hit = db.cache_get(key, ttl_days)
    if hit is not None:
        return hit or None
    res = fetcher(name)
    db.cache_set(key, res or {})
    return res
