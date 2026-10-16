import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_tickets.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app.db.init_db import init_db

    init_db(db_path)
    return db_path
