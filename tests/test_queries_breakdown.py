import pytest

from database import db as dbmod
from database.queries import get_category_breakdown


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "test.db"))
    dbmod.init_db()
    c = dbmod.get_db()
    for i in (1, 2):
        c.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (f"U{i}", f"u{i}@x.com", "h"),
        )
    c.commit()
    yield c
    c.close()


def add(c, user_id, category, amount):
    c.execute(
        "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)",
        (user_id, amount, category, "2026-01-01"),
    )
    c.commit()


def test_ordered_desc(conn):
    add(conn, 1, "Food", 10)
    add(conn, 1, "Bills", 70)
    add(conn, 1, "Food", 20)
    res = get_category_breakdown(1)
    assert [r["name"] for r in res] == ["Bills", "Food"]
    assert res[0]["amount"] == 70.0 and res[1]["amount"] == 30.0
    assert [r["pct"] for r in res] == [70, 30]


def test_pct_sums_to_100_equal_thirds(conn):
    for cat in ("Food", "Bills", "Health"):
        add(conn, 1, cat, 10)
    res = get_category_breakdown(1)
    assert all(isinstance(r["pct"], int) for r in res)
    assert sum(r["pct"] for r in res) == 100


def test_pct_sums_to_100_rounding_up(conn):
    for cat in ("Food", "Bills", "Health", "Other", "Shopping", "Transport"):
        add(conn, 1, cat, 10)
    assert sum(r["pct"] for r in get_category_breakdown(1)) == 100


def test_empty(conn):
    assert get_category_breakdown(1) == []


def test_excludes_other_users(conn):
    add(conn, 1, "Food", 10)
    add(conn, 2, "Bills", 500)
    res = get_category_breakdown(1)
    assert res == [{"name": "Food", "amount": 10.0, "pct": 100}]
