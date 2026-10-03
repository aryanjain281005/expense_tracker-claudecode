import pytest

import app as app_module
from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})


def test_profile_requires_login(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_profile_seed_user(client):
    login(client)
    resp = client.get("/profile")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "₹" in html
    assert "₹4,991.24" in html
    assert 'class="stat-value">8<' in html.replace("\n", "").replace("  ", "")
    assert "badge-shopping" in html.split("Top category")[1].split("</section>")[0]


def test_profile_transactions_newest_first(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    dates = [
        part.split("<")[0]
        for part in html.split('<td class="tx-date">')[1:]
    ]
    assert len(dates) == 8
    assert dates == sorted(dates, reverse=True)


def test_profile_breakdown_has_all_categories(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    for name in db.CATEGORIES:
        assert f'<span class="cat-name">{name}</span>' in html
    pcts = [
        int(part.split("%")[0])
        for part in html.split('<span class="cat-percent">')[1:]
    ]
    assert sum(pcts) == 100


def test_profile_new_user_is_empty(client):
    client.post(
        "/register",
        data={
            "name": "New Person",
            "email": "new@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    login(client, "new@example.com", "password123")
    resp = client.get("/profile")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "₹0.00" in html
    assert "New Person" in html
    assert 'class="tx-date"' not in html
    assert 'class="cat-name"' not in html
