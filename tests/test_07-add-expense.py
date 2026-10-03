"""Tests for Step 7: Add Expense (GET/POST /expenses/add)."""
import datetime

import pytest

import app as app_module
from database import db

URL = "/expenses/add"
ALL_CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client backed by a temporary DB; the real DB is never touched."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.seed_db()
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM expenses")
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other", "other@example.com", "x"),
        )
        conn.commit()
    finally:
        conn.close()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def auth_client(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    return client


def valid_form(**overrides):
    data = {
        "amount": "123.45",
        "category": "Food",
        "date": "2026-03-15",
        "description": "Lunch unique-marker",
    }
    data.update(overrides)
    return data


def all_expenses():
    conn = db.get_db()
    try:
        return conn.execute("SELECT * FROM expenses").fetchall()
    finally:
        conn.close()


# ------------------------------ auth guard ------------------------------ #

class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client):
        r = client.get(URL)
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]

    def test_post_logged_out_redirects_to_login_and_saves_nothing(self, client):
        r = client.post(URL, data=valid_form())
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]
        assert all_expenses() == []


# ------------------------------- GET form ------------------------------- #

class TestForm:
    def test_get_logged_in_returns_200(self, auth_client):
        assert auth_client.get(URL).status_code == 200

    def test_form_lists_all_seven_categories(self, auth_client):
        html = auth_client.get(URL).get_data(as_text=True)
        for cat in ALL_CATEGORIES:
            assert cat in html, f"Missing category {cat}"

    def test_form_has_expected_fields(self, auth_client):
        html = auth_client.get(URL).get_data(as_text=True)
        for name in ("amount", "category", "date", "description"):
            assert f'name="{name}"' in html, f"Missing field {name}"

    def test_form_prefills_todays_date(self, auth_client):
        html = auth_client.get(URL).get_data(as_text=True)
        assert datetime.date.today().isoformat() in html

    def test_form_has_cancel_link_to_profile(self, auth_client):
        html = auth_client.get(URL).get_data(as_text=True)
        assert "/profile" in html


# ----------------------------- happy path ------------------------------ #

class TestSuccess:
    def test_valid_post_redirects_to_profile(self, auth_client):
        r = auth_client.post(URL, data=valid_form())
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/profile")

    def test_row_saved_with_expected_values(self, auth_client):
        auth_client.post(URL, data=valid_form())
        rows = all_expenses()
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == 1
        assert isinstance(row["amount"], float)
        assert row["amount"] == pytest.approx(123.45)
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-15"
        assert row["description"] == "Lunch unique-marker"

    def test_integer_amount_stored_as_float(self, auth_client):
        auth_client.post(URL, data=valid_form(amount="50"))
        row = all_expenses()[0]
        assert isinstance(row["amount"], float)
        assert row["amount"] == 50.0

    @pytest.mark.parametrize("category", ALL_CATEGORIES)
    def test_every_category_accepted(self, auth_client, category):
        r = auth_client.post(URL, data=valid_form(category=category))
        assert r.status_code == 302
        assert all_expenses()[0]["category"] == category

    def test_user_id_comes_from_session_not_form(self, auth_client):
        auth_client.post(URL, data=valid_form(user_id="2"))
        rows = all_expenses()
        assert len(rows) == 1
        assert rows[0]["user_id"] == 1

    def test_new_expense_appears_on_profile(self, auth_client):
        auth_client.post(URL, data=valid_form(amount="777.00"))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "unique-marker" in html
        assert "777" in html
        assert "₹" in html

    def test_follow_redirect_lands_on_profile(self, auth_client):
        r = auth_client.post(URL, data=valid_form(), follow_redirects=True)
        assert r.status_code == 200
        assert "unique-marker" in r.get_data(as_text=True)

    def test_profile_has_link_to_add_expense(self, auth_client):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert URL in html

    def test_blank_description_ok(self, auth_client):
        r = auth_client.post(URL, data=valid_form(description=""))
        assert r.status_code == 302
        assert len(all_expenses()) == 1

    def test_missing_description_field_ok(self, auth_client):
        data = valid_form()
        del data["description"]
        r = auth_client.post(URL, data=data)
        assert r.status_code == 302
        assert len(all_expenses()) == 1

    def test_description_is_stripped(self, auth_client):
        auth_client.post(URL, data=valid_form(description="   padded   "))
        assert all_expenses()[0]["description"] == "padded"

    def test_description_capped_at_200_chars(self, auth_client):
        auth_client.post(URL, data=valid_form(description="x" * 500))
        desc = all_expenses()[0]["description"]
        assert len(desc) == 200

    def test_description_of_exactly_200_chars_kept(self, auth_client):
        auth_client.post(URL, data=valid_form(description="y" * 200))
        assert all_expenses()[0]["description"] == "y" * 200

    def test_sql_injection_in_description_stored_literally(self, auth_client):
        payload = "x'); DROP TABLE expenses;--"
        r = auth_client.post(URL, data=valid_form(description=payload))
        assert r.status_code == 302
        rows = all_expenses()
        assert len(rows) == 1
        assert rows[0]["description"] == payload

    def test_small_amount_accepted(self, auth_client):
        r = auth_client.post(URL, data=valid_form(amount="0.01"))
        assert r.status_code == 302
        assert all_expenses()[0]["amount"] == pytest.approx(0.01)


# ---------------------------- validation errors ---------------------------- #

class TestValidation:
    @pytest.mark.parametrize(
        "amount",
        ["", "   ", "0", "0.0", "-5", "-0.01", "abc", "12abc", "nan", "NaN",
         "inf", "-inf", "Infinity"],
    )
    def test_bad_amount_returns_400_and_saves_nothing(self, auth_client, amount):
        r = auth_client.post(URL, data=valid_form(amount=amount))
        assert r.status_code == 400, f"amount={amount!r}"
        assert all_expenses() == []

    def test_missing_amount_returns_400(self, auth_client):
        data = valid_form()
        del data["amount"]
        r = auth_client.post(URL, data=data)
        assert r.status_code == 400
        assert all_expenses() == []

    @pytest.mark.parametrize(
        "category", ["", "Groceries", "food", "FOOD", "'; DROP TABLE expenses;--"]
    )
    def test_invalid_category_returns_400_and_saves_nothing(
        self, auth_client, category
    ):
        r = auth_client.post(URL, data=valid_form(category=category))
        assert r.status_code == 400, f"category={category!r}"
        assert all_expenses() == []

    def test_missing_category_returns_400(self, auth_client):
        data = valid_form()
        del data["category"]
        r = auth_client.post(URL, data=data)
        assert r.status_code == 400
        assert all_expenses() == []

    @pytest.mark.parametrize(
        "date",
        ["", "not-a-date", "2026-13-01", "2026-02-30", "15-03-2026",
         "2026/03/15", "2026-3-5x", "20260315"],
    )
    def test_malformed_date_returns_400_and_saves_nothing(self, auth_client, date):
        r = auth_client.post(URL, data=valid_form(date=date))
        assert r.status_code == 400, f"date={date!r}"
        assert all_expenses() == []

    def test_missing_date_returns_400(self, auth_client):
        data = valid_form()
        del data["date"]
        r = auth_client.post(URL, data=data)
        assert r.status_code == 400
        assert all_expenses() == []

    def test_error_page_shows_a_message_and_form(self, auth_client):
        r = auth_client.post(URL, data=valid_form(amount="-5"))
        html = r.get_data(as_text=True)
        assert 'name="amount"' in html
        assert "error" in html.lower()

    def test_error_retains_submitted_values(self, auth_client):
        r = auth_client.post(
            URL,
            data=valid_form(amount="-5", category="Health",
                            date="2026-04-02", description="keep-me-please"),
        )
        html = r.get_data(as_text=True)
        assert r.status_code == 400
        assert "-5" in html
        assert "2026-04-02" in html
        assert "keep-me-please" in html
        assert "Health" in html

    def test_error_retains_selected_category(self, auth_client):
        r = auth_client.post(URL, data=valid_form(amount="abc", category="Bills"))
        html = r.get_data(as_text=True)
        assert r.status_code == 400
        # The Bills option should be marked selected.
        idx = html.index('<option value="Bills"')
        option_end = html.index("</option>", idx)
        assert "selected" in html[idx:option_end]

    def test_invalid_date_error_retains_values(self, auth_client):
        r = auth_client.post(
            URL, data=valid_form(date="garbage", description="still-here")
        )
        html = r.get_data(as_text=True)
        assert r.status_code == 400
        assert "still-here" in html
        assert "123.45" in html

    def test_failed_post_does_not_change_profile(self, auth_client):
        auth_client.post(URL, data=valid_form(amount="0", description="never-saved"))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "never-saved" not in html
