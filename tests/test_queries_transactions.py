import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import db
from database.queries import get_recent_transactions


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    c = db.get_db()
    for email in ("a@x.com", "b@x.com", "c@x.com"):
        c.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (email, email, "h"),
        )
    c.commit()
    yield c
    c.close()


def add(conn, user_id, date, amount=10.0, desc="d", cat="Food"):
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, cat, date, desc),
    )
    conn.commit()


def test_newest_first_and_keys(conn):
    add(conn, 1, "2026-01-01", 1.0, "old")
    add(conn, 1, "2026-03-01", 3.0, "new")
    add(conn, 1, "2026-02-01", 2.0, "mid")
    rows = get_recent_transactions(1)
    assert [r["description"] for r in rows] == ["new", "mid", "old"]
    assert set(rows[0]) == {"date", "description", "category", "amount"}
    assert rows[0]["amount"] == 3.0


def test_same_date_newest_id_first(conn):
    add(conn, 1, "2026-01-01", desc="first")
    add(conn, 1, "2026-01-01", desc="second")
    assert get_recent_transactions(1)[0]["description"] == "second"


def test_limit(conn):
    for i in range(1, 6):
        add(conn, 1, f"2026-01-0{i}")
    assert len(get_recent_transactions(1, limit=3)) == 3
    assert len(get_recent_transactions(1)) == 5


def test_empty(conn):
    assert get_recent_transactions(3) == []


def test_excludes_other_users(conn):
    add(conn, 1, "2026-01-01", desc="mine")
    add(conn, 2, "2026-02-01", desc="theirs")
    rows = get_recent_transactions(1)
    assert [r["description"] for r in rows] == ["mine"]


def test_null_description(conn):
    add(conn, 1, "2026-01-01", desc=None)
    assert get_recent_transactions(1)[0]["description"] == ""
