import pytest

import app as app_module
from database import db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

# (date, category, amount) — fixed dates so tests don't depend on today.
ROWS = [
    ("2026-01-01", "Food", 100.0),
    ("2026-02-10", "Bills", 300.0),
    ("2026-02-20", "Food", 50.0),
    ("2026-03-05", "Transport", 25.0),
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.seed_db()
    conn = db.get_db()
    try:
        # Seed user is id 1 with its own rows; replace them with fixed ones,
        # and add a second user whose rows must never leak in.
        conn.execute("DELETE FROM expenses")
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other", "other@example.com", "x"),
        )
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (1, ?, ?, ?, 'row')",
            [(a, c, d) for d, c, a in ROWS],
        )
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (2, 9999, 'Shopping', '2026-02-15', 'other user')"
        )
        conn.commit()
    finally:
        conn.close()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def login(client):
    return client.post(
        "/login", data={"email": "demo@spendly.com", "password": "demo123"}
    )


# ---------------------------- query helpers ---------------------------- #

def test_no_range_is_unchanged(client):
    assert get_summary_stats(1)["transaction_count"] == 4
    assert get_summary_stats(1)["total_spent"] == 475.0
    assert len(get_recent_transactions(1)) == 4


def test_range_is_inclusive_on_both_ends(client):
    stats = get_summary_stats(1, "2026-02-10", "2026-02-20")
    assert stats["transaction_count"] == 2
    assert stats["total_spent"] == 350.0
    assert stats["top_category"] == "Bills"


def test_start_only(client):
    stats = get_summary_stats(1, date_from="2026-02-20")
    assert stats["transaction_count"] == 2
    assert stats["total_spent"] == 75.0


def test_end_only(client):
    stats = get_summary_stats(1, date_to="2026-02-10")
    assert stats["transaction_count"] == 2
    assert stats["total_spent"] == 400.0


def test_transactions_filtered_newest_first(client):
    txs = get_recent_transactions(1, date_from="2026-02-01", date_to="2026-03-31")
    assert [t["date"] for t in txs] == ["2026-03-05", "2026-02-20", "2026-02-10"]


def test_transactions_limit_still_applies(client):
    assert len(get_recent_transactions(1, limit=2, date_from="2026-01-01")) == 2


def test_breakdown_filtered_sums_to_100(client):
    result = get_category_breakdown(1, "2026-02-01", "2026-02-28")
    assert [c["name"] for c in result] == ["Bills", "Food"]
    assert sum(c["pct"] for c in result) == 100
    assert sum(c["amount"] for c in result) == 350.0


def test_empty_range_returns_zeros_and_empty(client):
    assert get_summary_stats(1, "2030-01-01", "2030-12-31") == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }
    assert get_recent_transactions(1, date_from="2030-01-01") == []
    assert get_category_breakdown(1, date_from="2030-01-01") == []


def test_other_users_rows_excluded(client):
    stats = get_summary_stats(1, "2026-02-15", "2026-02-15")
    assert stats["transaction_count"] == 0


# ------------------------------- route -------------------------------- #

def test_profile_filter_requires_login(client):
    resp = client.get("/profile?date_from=2026-02-01")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_profile_no_params_shows_everything(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert "₹475.00" in html
    assert "Transaction history" in html


def test_profile_filtered_totals(client):
    login(client)
    resp = client.get("/profile?date_from=2026-02-01&date_to=2026-02-28")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "₹350.00" in html
    assert "Transactions in range" in html
    assert 'value="2026-02-01"' in html
    assert 'value="2026-02-28"' in html
    assert "other user" not in html


def test_profile_blank_params_are_ignored(client):
    login(client)
    html = client.get("/profile?date_from=&date_to=").get_data(as_text=True)
    assert "₹475.00" in html
    assert 'role="alert"' not in html


@pytest.mark.parametrize(
    "qs", ["date_from=abc", "date_from=2026-13-45", "date_to=2026-02-30"]
)
def test_profile_invalid_date_falls_back_silently(client, qs):
    login(client)
    resp = client.get("/profile?" + qs)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'role="alert"' not in html
    assert "₹475.00" in html


def test_profile_start_after_end_falls_back(client):
    login(client)
    resp = client.get("/profile?date_from=2026-03-01&date_to=2026-01-01")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Start date must be before end date." in html
    assert "₹475.00" in html


def test_profile_empty_range_empty_state(client):
    login(client)
    html = client.get("/profile?date_from=2030-01-01&date_to=2030-12-31").get_data(as_text=True)
    assert "₹0.00" in html
    assert "No transactions in this date range." in html
    assert "No spending in this date range." in html


def test_profile_presets_present(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
        assert label in html
    assert "/profile?date_from=" in html
    assert 'href="/profile"' in html


def test_profile_active_preset_highlighted(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert 'class="active" aria-current="true">All Time' in html
