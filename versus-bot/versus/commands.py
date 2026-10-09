"""Gestion des commandes, indépendante de Discord : texte -> liste de messages."""
from __future__ import annotations

import json

from . import config, formatter, validate, websearch
from .engine import Engine
from .text import chunk


class CommandHandler:
    def __init__(self, engine: Engine, admin_ids=None, web: bool | None = None):
        self.engine = engine
        self.admin_ids = set(admin_ids if admin_ids is not None else config.ADMIN_IDS)
        self.web = config.WEB_FALLBACK if web is None else web

    # ------------------------------------------------------------ routage
    def handle(self, text: str, user_id: int = 0, attachment: tuple | None = None) -> list:
        text = (text or "").strip()
        if text.startswith(config.PREFIX):
            cmd, _, rest = text[len(config.PREFIX):].partition(" ")
            cmd, rest = cmd.lower(), rest.strip()
            fn = {"versus": self._versus, "analyze": self._analyze, "feats": self._feats,
                  "abilities": self._abilities, "sources": self._sources, "compare": self._compare,
                  "form": self._form, "forms": self._form, "help": lambda r: [formatter.HELP]}.get(cmd)
            if cmd == "admin":
                return self._admin(rest, user_id, attachment)
            if fn:
                return fn(rest)
            return ["Commande inconnue. Tape `!help`."]
        return self._versus(text)

    # ------------------------------------------------------------ helpers
    def _one(self, name: str):
        r = self.engine.resolver.resolve(name)
        if r.status == "ok":
            return self.engine.profile(r.character, r.form), None
        if r.status == "ambiguous":
            return None, self._ambiguous([self.engine.db.get_character(c).name for c in r.candidates])
        return None, self._unknown([name])

    def _ambiguous(self, names):
        return ["Plusieurs personnages correspondent : " + ", ".join(names) + ". Précise lequel."]

    def _unknown(self, names) -> list:
        out = []
        for n in names:
            out.append(f"Information inconnue dans la base : « {n} ».")
            if self.web and n:
                try:
                    hit = websearch.lookup(self.engine.db, n, config.CACHE_TTL_DAYS)
                except Exception:
                    hit = None
                if hit:
                    out.append(f"Piste web (non utilisée dans le calcul, source wiki prio 5) : {hit['title']} "
                               f"{hit['url']}\n{hit['extract']}")
        out.append("Un admin peut l'ajouter avec `!admin add` (fichier JSON).")
        return ["\n".join(out)]

    # ------------------------------------------------------------ commandes
    def _versus(self, rest: str) -> list:
        ans = self.engine.ask(rest)
        if ans.kind == "usage":
            return [ans.message]
        if ans.kind == "unknown":
            return self._unknown(ans.unknown)
        if ans.kind == "ambiguous":
            return self._ambiguous(ans.candidates)
        return formatter.format_versus(ans.result, ans.result.cond.detailed)

    def _simple(self, rest, fmt):
        if not rest:
            return ["Donne un nom de personnage."]
        p, err = self._one(rest)
        return err if err else fmt(p)

    def _analyze(self, rest): return self._simple(rest, formatter.format_analyze)
    def _feats(self, rest): return self._simple(rest, formatter.format_feats)
    def _abilities(self, rest): return self._simple(rest, formatter.format_abilities)

    def _sources(self, rest):
        return self._simple(rest, lambda p: formatter.format_sources(
            p.character, self.engine.db.sources_of(p.character.id)))

    def _form(self, rest):
        return self._simple(rest, lambda p: formatter.format_forms(p.character))

    def _compare(self, rest):
        two = self.engine.resolver.split_two(rest)
        if not two:
            return ["Format : `!compare Naruto Luffy`"]
        pa, e1 = self._one(two[0])
        pb, e2 = self._one(two[1])
        return e1 or e2 or formatter.format_compare(pa, pb)

    # ------------------------------------------------------------ admin
    def _admin(self, rest: str, user_id: int, attachment) -> list:
        if user_id not in self.admin_ids:
            return ["Commande réservée aux administrateurs (variable ADMIN_IDS)."]
        sub = rest.split(" ")[0].lower()
        eng = self.engine
        if sub == "validate":
            issues = validate.validate_dirs(config.DATA_DIR, config.CUSTOM_DIR)
            errs = [i for i in issues if i.level == "error"]
            return chunk(f"{len(errs)} erreur(s), {len(issues) - len(errs)} avertissement(s)\n"
                         + "\n".join(str(i) for i in issues[:25]))
        if sub == "reload":
            eng.db.import_dir(config.DATA_DIR)
            eng.db.import_dir(config.CUSTOM_DIR)
            eng.reload()
            return [f"Base rechargée : {len(eng.db.character_ids())} personnages."]
        if sub == "list":
            return chunk("Personnages : " + ", ".join(eng.db.character_ids()))
        if sub == "add":
            if not attachment:
                return ["Joins un fichier .json (voir README, section « Ajouter un personnage »)."]
            name, raw = attachment
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception as e:
                return [f"JSON invalide : {e}"]
            known = {f"{cid}:{fid}" for cid in eng.db.character_ids()
                     for fid in eng.db.get_character(cid).forms}
            issues = [i for i in validate.validate_payloads([(name, payload)], known) if i.level == "error"]
            if issues:
                return chunk("Refusé :\n" + "\n".join(str(i) for i in issues[:15]))
            config.CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch for ch in name if ch.isalnum() or ch in "._-") or "custom.json"
            (config.CUSTOM_DIR / safe).write_bytes(raw)
            counts = eng.db.import_payload(payload)
            eng.reload()
            return [f"Importé : {counts}"]
        return ["Usage : `!admin validate | reload | list | add` (+ fichier JSON)"]
