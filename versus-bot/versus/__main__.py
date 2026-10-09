"""Point d'entrée : `python -m versus` (bot), `ask "A vs B"`, `validate`, `import f.json`."""
from __future__ import annotations

import logging
import os
import sys

from . import config, validate
from .commands import CommandHandler
from .database import Database
from .engine import Engine


def build() -> tuple:
    db = Database(config.DB_PATH)
    db.import_dir(config.DATA_DIR)
    db.import_dir(config.CUSTOM_DIR)
    return db, Engine(db)


def main(argv: list) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cmd = argv[0] if argv else "bot"
    if cmd == "validate":
        issues = validate.validate_dirs(config.DATA_DIR, config.CUSTOM_DIR)
        for i in issues:
            print(i)
        errs = [i for i in issues if i.level == "error"]
        print(f"{len(errs)} erreur(s), {len(issues) - len(errs)} avertissement(s)")
        return 1 if errs else 0
    if cmd == "import":
        db = Database(config.DB_PATH)
        for f in argv[1:]:
            print(f, db.import_file(f))
        return 0
    db, engine = build()
    handler = CommandHandler(engine)
    if cmd == "ask":
        for m in handler.handle(" ".join(argv[1:])):
            print(m)
        return 0
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        print("DISCORD_TOKEN manquant : ajoute-le dans les variables d'environnement.", file=sys.stderr)
        return 1
    logging.getLogger("versus").info("%d personnages chargés", len(db.character_ids()))
    from . import discord_bot
    discord_bot.run(handler, token)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
