import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
from versus import config
from versus.commands import CommandHandler
from versus.database import Database
from versus.engine import Engine


@pytest.fixture(scope="session")
def engine():
    db = Database(":memory:")
    db.import_dir(config.DATA_DIR)
    return Engine(db)


@pytest.fixture()
def handler(engine):
    return CommandHandler(engine, admin_ids={1}, web=False)
