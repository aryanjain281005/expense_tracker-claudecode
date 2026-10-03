"""Tests for Step 6: date-range filter on GET /profile.

Written from .claude/specs/06-date-filter-for-profile-page.md.
Expense rows are inserted by the tests with fixed dates; seed totals are never used.
"""
import html as html_lib
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from database import db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

ERROR_MSG = "Start date must be before end date."
PRESETS = ["This Month", "Last 3 Months", "Last 6 Months", "All Time"]

# (date, category, amount, description) for the demo user
FIXED = [
    ("2024-01-10", "Food", 10.00, "jan-food-a"),
    ("2024-01-15", "Transport", 20.00, "jan-transport"),
    ("2024-01-20", "Food", 30.00, "jan-food-b"),
    ("2024-02-01", "Bills", 40.00, "feb-bills"),
]
OTHER_USER_ROW = ("2024-01-15", "Health", 999.00, "other-user-row")


# ------------------------------------------------------------------ #
# Fixtures / helpers                                                  #
# ------------------------------------------------------------------ #

def _insert(user_id, rows):
    conn = db.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(user_id, amt, cat, d, desc) for d, cat, amt, desc in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _reset_expenses_and_fill(rows, other_rows=()):
    """Remove all seeded expenses, then insert known rows for demo (and another user)."""
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM expenses")
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other Person", "other@example.com", generate_password_hash("otherpass1")),
        )
        other_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("other@example.com",)
        ).fetchone()["id"]
        conn.commit()
    finally:
        conn.close()
    _insert(demo_id, rows)
    _insert(other_id, other_rows)
    return demo_id, other_id


@pytest.fixture
def ids(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.seed_db()
    return _reset_expenses_and_fill(FIXED, [OTHER_USER_ROW])


@pytest.fixture
def client(ids):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def auth_client(client):
    resp = client.post(
        "/login", data={"email": "demo@spendly.com", "password": "demo123"}
    )
    assert resp.status_code == 302, "demo login should succeed"
    return client


def _html(resp):
    return resp.get_data(as_text=True)


def _tx_dates(page):
    return [p.split("<")[0].strip() for p in page.split('<td class="tx-date">')[1:]]


def _total(page):
    m = re.search(r'class="stat-value">\s*₹([\d,]+\.\d{2})\s*<', page)
    assert m, "total spent stat with rupee symbol not found"
    return float(m.group(1).replace(",", ""))


def _count(page):
    m = re.search(r"Transactions</p>\s*<p class=\"stat-value\">\s*(\d+)\s*<", page)
    assert m, "transaction count stat not found"
    return int(m.group(1))


def _cat_names(page):
    return re.findall(r'<span class="cat-name">([^<]+)</span>', page)


def _preset_anchor(page, label):
    """Return (href, full_open_tag) of the preset link with this label."""
    for m in re.finditer(r"(<a\b[^>]*>)\s*" + re.escape(label) + r"\s*</a>", page):
        tag = m.group(1)
        href = re.search(r'href="([^"]*)"', tag)
        if href:
            return html_lib.unescape(href.group(1)), tag
    raise AssertionError("preset link %r not found" % label)


def _preset_active(page, label):
    _, tag = _preset_anchor(page, label)
    return "active" in tag or "aria-current" in tag


def _link_params(page, label):
    href, _ = _preset_anchor(page, label)
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    return parsed.path, {k: v[0] for k, v in qs.items()}


def _months_back(today, months):
    idx = today.year * 12 + today.month - 1 - months
    year, month = divmod(idx, 12)
    month += 1
    day = today.day
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


# ------------------------------------------------------------------ #
# Unfiltered / baseline                                               #
# ------------------------------------------------------------------ #

class TestUnfiltered:
    def test_no_params_shows_all_expenses(self, auth_client):
        resp = auth_client.get("/profile")
        page = _html(resp)
        assert resp.status_code == 200
        assert sorted(_tx_dates(page)) == sorted(d for d, *_ in FIXED)
        assert _total(page) == pytest.approx(100.00)
        assert _count(page) == 4

    def test_no_params_shows_no_error(self, auth_client):
        assert ERROR_MSG not in _html(auth_client.get("/profile"))

    def test_no_params_all_time_is_active(self, auth_client):
        page = _html(auth_client.get("/profile"))
        assert _preset_active(page, "All Time")
        for label in PRESETS[:3]:
            assert not _preset_active(page, label), label + " should not be active"

    def test_filter_bar_has_all_presets_and_date_inputs(self, auth_client):
        page = _html(auth_client.get("/profile"))
        for label in PRESETS:
            assert label in page, label + " preset missing"
        assert re.search(r'<input[^>]*type="date"[^>]*name="date_from"', page)
        assert re.search(r'<input[^>]*type="date"[^>]*name="date_to"', page)
        assert "Apply" in page


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuth:
    @pytest.mark.parametrize(
        "qs",
        ["", "?date_from=2024-01-01&date_to=2024-01-31", "?date_from=garbage"],
    )
    def test_unauthenticated_redirects_to_login(self, client, qs):
        resp = client.get("/profile" + qs)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# Custom range                                                        #
# ------------------------------------------------------------------ #

class TestCustomRange:
    def test_valid_range_filters_transactions(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-12&date_to=2024-01-31")
        )
        assert sorted(_tx_dates(page)) == ["2024-01-15", "2024-01-20"]

    def test_valid_range_filters_summary_stats(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-12&date_to=2024-01-31")
        )
        assert _total(page) == pytest.approx(50.00)
        assert _count(page) == 2

    def test_valid_range_filters_category_breakdown(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-12&date_to=2024-01-31")
        )
        names = _cat_names(page)
        # Bills (Feb) is outside the range and has no spend in range.
        assert "Transport" in names and "Food" in names
        page_bills = re.search(r'cat-name">Bills</span>\s*<span class="cat-amount">\s*₹([\d,.]+)', page)
        if page_bills:
            assert float(page_bills.group(1).replace(",", "")) == 0.0

    def test_bounds_are_inclusive(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-15&date_to=2024-01-20")
        )
        assert sorted(_tx_dates(page)) == ["2024-01-15", "2024-01-20"]
        assert _total(page) == pytest.approx(50.00)

    def test_single_day_range(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-02-01&date_to=2024-02-01")
        )
        assert _tx_dates(page) == ["2024-02-01"]
        assert _total(page) == pytest.approx(40.00)

    def test_equal_dates_do_not_flash_error(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-02-01&date_to=2024-02-01")
        )
        assert ERROR_MSG not in page

    def test_transactions_still_newest_first_when_filtered(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
        )
        dates = _tx_dates(page)
        assert dates == sorted(dates, reverse=True)

    def test_custom_range_reflected_in_date_inputs(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-12&date_to=2024-01-31")
        )
        assert re.search(r'name="date_from"[^>]*value="2024-01-12"', page)
        assert re.search(r'name="date_to"[^>]*value="2024-01-31"', page)

    def test_custom_range_no_preset_active(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-12&date_to=2024-01-31")
        )
        for label in PRESETS:
            assert not _preset_active(page, label), label + " wrongly active"

    def test_amounts_keep_rupee_symbol_when_filtered(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-01&date_to=2024-01-31")
        )
        assert "₹" in page
        assert "₹60.00" in page

    def test_only_date_from_is_given(self, auth_client):
        resp = auth_client.get("/profile?date_from=2024-01-20")
        assert resp.status_code == 200
        assert ERROR_MSG not in _html(resp)

    def test_only_date_to_is_given(self, auth_client):
        resp = auth_client.get("/profile?date_to=2024-01-20")
        assert resp.status_code == 200
        assert ERROR_MSG not in _html(resp)


# ------------------------------------------------------------------ #
# Blank / malformed / reversed                                        #
# ------------------------------------------------------------------ #

class TestValidation:
    @pytest.mark.parametrize(
        "qs",
        [
            "date_from=&date_to=",
            "date_from=not-a-date",
            "date_to=not-a-date",
            "date_from=not-a-date&date_to=also-bad",
            "date_from=2024-13-45&date_to=2024-14-01",
            "date_from=2024-02-30",
            "date_from=01/10/2024&date_to=01/31/2024",
            "date_from=%27%3B+DROP+TABLE+expenses%3B--",
        ],
    )
    def test_bad_or_blank_params_fall_back_silently(self, auth_client, qs):
        resp = auth_client.get("/profile?" + qs)
        page = _html(resp)
        assert resp.status_code == 200
        assert ERROR_MSG not in page, "malformed input must not flash the range error"
        assert _count(page) == 4
        assert _total(page) == pytest.approx(100.00)

    def test_malformed_from_with_valid_to_does_not_crash(self, auth_client):
        resp = auth_client.get("/profile?date_from=not-a-date&date_to=2024-01-31")
        assert resp.status_code == 200
        assert ERROR_MSG not in _html(resp)

    def test_reversed_range_flashes_error(self, auth_client):
        resp = auth_client.get("/profile?date_from=2024-02-01&date_to=2024-01-01")
        assert resp.status_code == 200
        assert ERROR_MSG in _html(resp)

    def test_reversed_range_falls_back_to_unfiltered(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-02-01&date_to=2024-01-01")
        )
        assert _count(page) == 4
        assert _total(page) == pytest.approx(100.00)
        assert len(_tx_dates(page)) == 4

    def test_reversed_range_marks_all_time_active(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-02-01&date_to=2024-01-01")
        )
        assert _preset_active(page, "All Time")

    def test_error_not_shown_on_following_request(self, auth_client):
        auth_client.get("/profile?date_from=2024-02-01&date_to=2024-01-01")
        page = _html(auth_client.get("/profile"))
        assert ERROR_MSG not in page


# ------------------------------------------------------------------ #
# Empty range                                                         #
# ------------------------------------------------------------------ #

class TestEmptyRange:
    URL = "/profile?date_from=2020-01-01&date_to=2020-01-31"

    def test_empty_range_returns_200(self, auth_client):
        assert auth_client.get(self.URL).status_code == 200

    def test_empty_range_zero_total_and_count(self, auth_client):
        page = _html(auth_client.get(self.URL))
        assert "₹0.00" in page
        assert _total(page) == 0.0
        assert _count(page) == 0

    def test_empty_range_has_no_transactions(self, auth_client):
        page = _html(auth_client.get(self.URL))
        assert _tx_dates(page) == []

    def test_empty_range_has_no_category_spend(self, auth_client):
        page = _html(auth_client.get(self.URL))
        for amt in re.findall(r'cat-amount">\s*₹([\d,.]+)', page):
            assert float(amt.replace(",", "")) == 0.0


# ------------------------------------------------------------------ #
# Per-user isolation                                                  #
# ------------------------------------------------------------------ #

class TestIsolation:
    def test_other_users_expenses_never_included(self, auth_client):
        page = _html(
            auth_client.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
        )
        assert "other-user-row" not in page
        assert "999.00" not in page
        assert _total(page) == pytest.approx(100.00)

    def test_other_user_sees_only_own_filtered_data(self, client):
        resp = client.post(
            "/login", data={"email": "other@example.com", "password": "otherpass1"}
        )
        assert resp.status_code == 302
        page = _html(client.get("/profile?date_from=2024-01-01&date_to=2024-01-31"))
        assert _count(page) == 1
        assert _total(page) == pytest.approx(999.00)


# ------------------------------------------------------------------ #
# Presets                                                             #
# ------------------------------------------------------------------ #

class TestPresets:
    @pytest.fixture
    def preset_client(self, ids):
        today = date.today()
        rows = [
            (today.isoformat(), "Food", 5.00, "p-today"),
            ((today - timedelta(days=45)).isoformat(), "Bills", 7.00, "p-45"),
            ((today - timedelta(days=100)).isoformat(), "Health", 11.00, "p-100"),
            ((today - timedelta(days=200)).isoformat(), "Shopping", 13.00, "p-200"),
            ((today - timedelta(days=400)).isoformat(), "Other", 17.00, "p-400"),
        ]
        _reset_expenses_and_fill(rows)
        app_module.app.config["TESTING"] = True
        c = app_module.app.test_client()
        c.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
        return c, rows

    def test_all_time_link_has_no_query_params(self, preset_client):
        c, _ = preset_client
        path, params = _link_params(_html(c.get("/profile")), "All Time")
        assert path == "/profile"
        assert params == {}, "All Time must be a clean /profile URL"

    def test_this_month_link_params(self, preset_client):
        c, _ = preset_client
        today = date.today()
        _, params = _link_params(_html(c.get("/profile")), "This Month")
        assert params == {
            "date_from": today.replace(day=1).isoformat(),
            "date_to": today.isoformat(),
        }

    def test_last_3_months_link_params(self, preset_client):
        c, _ = preset_client
        today = date.today()
        _, params = _link_params(_html(c.get("/profile")), "Last 3 Months")
        assert params == {
            "date_from": _months_back(today, 3).isoformat(),
            "date_to": today.isoformat(),
        }

    def test_last_6_months_link_params(self, preset_client):
        c, _ = preset_client
        today = date.today()
        _, params = _link_params(_html(c.get("/profile")), "Last 6 Months")
        assert params == {
            "date_from": _months_back(today, 6).isoformat(),
            "date_to": today.isoformat(),
        }

    @pytest.mark.parametrize("label", PRESETS[:3])
    def test_preset_links_point_to_profile(self, preset_client, label):
        c, _ = preset_client
        path, _ = _link_params(_html(c.get("/profile")), label)
        assert path == "/profile"

    @pytest.mark.parametrize("label", ["This Month", "Last 3 Months", "Last 6 Months"])
    def test_following_preset_filters_all_sections(self, preset_client, label):
        c, rows = preset_client
        _, params = _link_params(_html(c.get("/profile")), label)
        resp = c.get("/profile", query_string=params)
        page = _html(resp)
        lo, hi = params["date_from"], params["date_to"]
        expected = [r for r in rows if lo <= r[0] <= hi]
        assert resp.status_code == 200
        assert sorted(_tx_dates(page)) == sorted(r[0] for r in expected)
        assert _count(page) == len(expected)
        assert _total(page) == pytest.approx(sum(r[2] for r in expected))

    @pytest.mark.parametrize("label", ["This Month", "Last 3 Months", "Last 6 Months"])
    def test_active_preset_is_highlighted_after_click(self, preset_client, label):
        c, _ = preset_client
        _, params = _link_params(_html(c.get("/profile")), label)
        page = _html(c.get("/profile", query_string=params))
        assert _preset_active(page, label), label + " should be active"
        assert not _preset_active(page, "All Time")

    def test_last_6_months_excludes_old_and_includes_recent(self, preset_client):
        c, rows = preset_client
        _, params = _link_params(_html(c.get("/profile")), "Last 6 Months")
        page = _html(c.get("/profile", query_string=params))
        dates = _tx_dates(page)
        assert rows[0][0] in dates, "today's expense must be included"
        assert rows[4][0] not in dates, "400-day-old expense must be excluded"

    def test_all_time_after_filter_shows_everything(self, preset_client):
        c, rows = preset_client
        path, params = _link_params(_html(c.get("/profile?date_from=2020-01-01&date_to=2020-01-02")), "All Time")
        page = _html(c.get(path, query_string=params))
        assert _count(page) == len(rows)
        assert _total(page) == pytest.approx(sum(r[2] for r in rows))
        assert _preset_active(page, "All Time")


# ------------------------------------------------------------------ #
# Query helpers                                                       #
# ------------------------------------------------------------------ #

class TestQueryHelpers:
    def test_summary_unfiltered_matches_all(self, ids):
        uid, _ = ids
        s = get_summary_stats(uid)
        assert s["total_spent"] == pytest.approx(100.00)
        assert s["transaction_count"] == 4

    def test_summary_keyword_args_filter(self, ids):
        uid, _ = ids
        s = get_summary_stats(uid, date_from="2024-01-12", date_to="2024-01-31")
        assert s["total_spent"] == pytest.approx(50.00)
        assert s["transaction_count"] == 2

    def test_summary_inclusive_bounds(self, ids):
        uid, _ = ids
        s = get_summary_stats(uid, date_from="2024-01-10", date_to="2024-01-10")
        assert s["total_spent"] == pytest.approx(10.00)
        assert s["transaction_count"] == 1

    def test_summary_empty_range(self, ids):
        uid, _ = ids
        s = get_summary_stats(uid, date_from="2020-01-01", date_to="2020-01-31")
        assert s["total_spent"] == 0
        assert s["transaction_count"] == 0

    def test_summary_top_category_respects_range(self, ids):
        uid, _ = ids
        s = get_summary_stats(uid, date_from="2024-02-01", date_to="2024-02-28")
        assert s["top_category"] == "Bills"

    def test_summary_other_user_isolated(self, ids):
        _, oid = ids
        s = get_summary_stats(oid, date_from="2024-01-01", date_to="2024-12-31")
        assert s["total_spent"] == pytest.approx(999.00)

    def test_transactions_unfiltered(self, ids):
        uid, _ = ids
        assert len(get_recent_transactions(uid)) == 4

    def test_transactions_keyword_args_filter(self, ids):
        uid, _ = ids
        txs = get_recent_transactions(uid, date_from="2024-01-12", date_to="2024-01-31")
        assert [t["date"] for t in txs] == ["2024-01-20", "2024-01-15"]

    def test_transactions_inclusive_bounds(self, ids):
        uid, _ = ids
        txs = get_recent_transactions(uid, date_from="2024-01-15", date_to="2024-02-01")
        assert [t["date"] for t in txs] == ["2024-02-01", "2024-01-20", "2024-01-15"]

    def test_transactions_limit_still_applies_with_filter(self, ids):
        uid, _ = ids
        txs = get_recent_transactions(
            uid, limit=2, date_from="2024-01-01", date_to="2024-12-31"
        )
        assert [t["date"] for t in txs] == ["2024-02-01", "2024-01-20"]

    def test_transactions_empty_range(self, ids):
        uid, _ = ids
        assert get_recent_transactions(uid, date_from="2020-01-01", date_to="2020-01-31") == []

    def test_transactions_other_user_isolated(self, ids):
        uid, _ = ids
        txs = get_recent_transactions(uid, date_from="2024-01-01", date_to="2024-12-31")
        assert all(t["description"] != "other-user-row" for t in txs)

    def test_breakdown_unfiltered(self, ids):
        uid, _ = ids
        rows = {r["name"]: r["amount"] for r in get_category_breakdown(uid)}
        assert rows["Food"] == pytest.approx(40.00)
        assert rows["Transport"] == pytest.approx(20.00)
        assert rows["Bills"] == pytest.approx(40.00)

    def test_breakdown_keyword_args_filter(self, ids):
        uid, _ = ids
        rows = {
            r["name"]: r
            for r in get_category_breakdown(
                uid, date_from="2024-01-01", date_to="2024-01-31"
            )
        }
        assert rows["Food"]["amount"] == pytest.approx(40.00)
        assert rows["Transport"]["amount"] == pytest.approx(20.00)
        assert "Bills" not in rows or rows["Bills"]["amount"] == 0

    def test_breakdown_percentages_recalculated_for_range(self, ids):
        uid, _ = ids
        rows = {
            r["name"]: r["pct"]
            for r in get_category_breakdown(
                uid, date_from="2024-01-01", date_to="2024-01-31"
            )
        }
        # Jan: Food 40 of 60, Transport 20 of 60
        assert rows["Food"] == pytest.approx(67, abs=1)
        assert rows["Transport"] == pytest.approx(33, abs=1)

    def test_breakdown_empty_range_no_error(self, ids):
        uid, _ = ids
        rows = get_category_breakdown(uid, date_from="2020-01-01", date_to="2020-01-31")
        assert all(r["amount"] == 0 for r in rows)


class TestReviewFollowUps:
    def test_unpadded_date_is_normalised(self, auth_client):
        padded = _html(auth_client.get("/profile?date_from=2024-01-15"))
        unpadded = _html(auth_client.get("/profile?date_from=2024-1-15"))
        assert _tx_dates(unpadded) == _tx_dates(padded)
        assert 'value="2024-01-15"' in unpadded

    @pytest.mark.parametrize(
        "today, months, expected",
        [
            (date(2024, 5, 31), 3, date(2024, 2, 29)),
            (date(2023, 5, 31), 3, date(2023, 2, 28)),
            (date(2024, 8, 31), 6, date(2024, 2, 29)),
            (date(2024, 1, 15), 3, date(2023, 10, 15)),
        ],
    )
    def test_months_ago_clamps_to_month_end(self, today, months, expected):
        assert app_module._months_ago(today, months) == expected

    def test_non_error_flash_not_shown_on_profile(self, auth_client):
        with auth_client.session_transaction() as sess:
            sess["_flashes"] = [("info", "unrelated-message")]
        page = _html(auth_client.get("/profile"))
        assert "unrelated-message" not in page

    def test_inactive_preset_has_no_empty_class(self, auth_client):
        page = _html(auth_client.get("/profile"))
        assert 'class=""' not in page

    def test_secret_key_required_in_production(self, monkeypatch):
        import importlib

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError):
            importlib.reload(app_module)
        monkeypatch.delenv("APP_ENV")
        importlib.reload(app_module)
