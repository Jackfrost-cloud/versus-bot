"""Importe des fichiers JSON (personnages, relations, univers) : python scripts/import_data.py f1.json f2.json"""
import sys
from versus.__main__ import main
sys.exit(main(["import", *sys.argv[1:]]))
