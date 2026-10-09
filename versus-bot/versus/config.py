"""Configuration et constantes du moteur."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("VERSUS_DATA_DIR", ROOT / "data"))
STATE_DIR = Path(os.getenv("VERSUS_STATE_DIR", ROOT / "state"))
DB_PATH = Path(os.getenv("VERSUS_DB", STATE_DIR / "versus.db"))
CUSTOM_DIR = STATE_DIR / "custom"
WEB_FALLBACK = os.getenv("VERSUS_WEB_FALLBACK", "1") == "1"
CACHE_TTL_DAYS = int(os.getenv("VERSUS_CACHE_TTL_DAYS", "30"))
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
PREFIX = os.getenv("VERSUS_PREFIX", "!")

STAT_CATEGORIES = ["strength", "speed", "reaction_speed", "durability", "attack_power",
                   "stamina", "range", "battle_iq", "experience"]
SCALING_CATEGORIES = STAT_CATEGORIES + ["outcome"]
CAT_LABELS = {"strength": "Force", "speed": "Vitesse", "reaction_speed": "Réflexes",
              "durability": "Durabilité", "attack_power": "Puissance d'attaque",
              "stamina": "Endurance", "range": "Portée", "battle_iq": "Battle IQ",
              "experience": "Expérience"}

FEAT_KINDS = ("direct", "statement", "scaling", "estimation", "interpretation", "hypothesis")
KIND_WEIGHTS = {"direct": 1.0, "scaling": 0.7, "statement": 0.6, "interpretation": 0.5,
                "estimation": 0.4, "hypothesis": 0.15}
SOURCE_PRIORITY = {"original_work": 10, "official": 10, "databook": 9, "interview": 8,
                   "secondary": 7, "wiki": 5, "forum": 3, "unverified": 1}
INHERIT_DECAY = 0.85

# Pondérations du score final (somme = 100)
SPEC_WEIGHTS = {"force": 10, "vitesse": 15, "durabilite": 10, "puissance": 10, "endurance": 5,
                "battle_iq": 8, "experience": 5, "hax": 15, "resistances": 8,
                "versatilite": 5, "matchup": 9}

WIN_TYPES = ("kill", "neutralize", "none")
RELATIONS = (">", "=")
KNOWN_TAGS = {
    "physical", "energy_blast", "area_attack", "illusion", "mind_control", "sealing",
    "space_manipulation", "time_manipulation", "teleportation", "intangibility",
    "regeneration", "immortality", "soul", "erasure", "absorption", "causality",
    "precognition", "reality", "poison", "cellular_damage", "nullification", "clones",
    "sensing", "utility", "flight", "gravity", "durability_negation", "barrier",
    "reflection", "summoning", "curse", "domain", "adaptation", "armament_haki",
    "attrition", "disease",
}

CONFIDENCE_BANDS = [(0.95, "très documenté"), (0.80, "fortement établi"), (0.60, "probable"),
                    (0.40, "controversé"), (0.20, "spéculatif"), (0.0, "insuffisant")]
