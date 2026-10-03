import pytest

import database.db as db
from database.queries import get_summary_stats, get_user_by_id


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    c = db.get_db()
    c.execute(
        "INSERT INTO users (id, name, email, password_hash, created_at) "
        "VALUES (1, 'Asha', 'asha@example.com', 'x', '2026-01-15 10:30:00')"
    )
    c.execute(
        "INSERT INTO users (id, name, email, password_hash, created_at) "
        "VALUES (2, 'Ravi', 'ravi@example.com', 'x', '2026-02-01 09:00:00')"
    )
    c.commit()
    yield c
    c.close()


def test_get_user_by_id_valid(conn):
    assert get_user_by_id(1) == {
        "name": "Asha",
        "email": "asha@example.com",
        "member_since": "January 2026",
    }


def test_get_user_by_id_missing(conn):
    assert get_user_by_id(999) is None


def test_summary_stats_with_expenses(conn):
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)",
        [
            (1, 100.10, "Food", "2026-03-01"),
            (1, 50.20, "Food", "2026-03-02"),
            (1, 200.00, "Bills", "2026-03-03"),
            (2, 999.00, "Shopping", "2026-03-03"),
        ],
    )
    conn.commit()
    assert get_summary_stats(1) == {
        "total_spent": 350.3,
        "transaction_count": 3,
        "top_category": "Bills",
    }


def test_summary_stats_no_expenses(conn):
    assert get_summary_stats(1) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }
