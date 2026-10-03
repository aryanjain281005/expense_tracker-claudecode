import calendar
import os
import sqlite3
from datetime import date, datetime

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

load_dotenv()

app = Flask(__name__)
if os.environ.get("APP_ENV") == "production" and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY must be set when APP_ENV=production.")
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    def fail(message):
        return render_template("register.html", error=message, name=name, email=email), 400

    if not name or not email or not password or not confirm_password:
        return fail("All fields are required.")
    local, _, domain = email.partition("@")
    if not local or not domain or "@" in domain:
        return fail("Enter a valid email address.")
    if len(password) < 8:
        return fail("Password must be at least 8 characters.")
    if password != confirm_password:
        return fail("Passwords do not match.")

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return fail("Email already registered")
    finally:
        conn.close()

    return redirect(url_for("login", registered=1))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template(
            "login.html", error="Email and password are required.", email=email
        ), 400

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, name, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html", error="Invalid email or password.", email=email
        ), 401

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("landing"))


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _parse_date(value):
    """Return value normalised to YYYY-MM-DD if it is a real date, else None."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _months_ago(today, months):
    """Same day-of-month `months` earlier, clamped to the month's last day."""
    year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
    month += 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _format_range_label(date_from, date_to):
    def fmt(value):
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")

    if date_from and date_to:
        return f"{fmt(date_from)} – {fmt(date_to)}"
    if date_from:
        return f"From {fmt(date_from)}"
    return f"Up to {fmt(date_to)}"


def _build_date_filter(date_from, date_to, today):
    """Template context for the filter bar: presets, active state and label."""
    preset_ranges = [
        ("This Month", today.replace(day=1), today),
        ("Last 3 Months", _months_ago(today, 3), today),
        ("Last 6 Months", _months_ago(today, 6), today),
        ("All Time", None, None),
    ]
    presets = []
    for label, p_from, p_to in preset_ranges:
        p_from = p_from.isoformat() if p_from else None
        p_to = p_to.isoformat() if p_to else None
        presets.append(
            {
                "label": label,
                # All Time passes no params, giving a clean /profile URL.
                "url": url_for("profile", date_from=p_from, date_to=p_to),
                "active": (date_from, date_to) == (p_from, p_to),
            }
        )
    is_filtered = bool(date_from or date_to)
    return {
        "date_from": date_from or "",
        "date_to": date_to or "",
        "presets": presets,
        "is_filtered": is_filtered,
        "custom_active": is_filtered and not any(p["active"] for p in presets),
        "label": _format_range_label(date_from, date_to) if is_filtered else "",
    }


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user_row = get_user_by_id(user_id)
    if user_row is None:
        session.clear()
        return redirect(url_for("login"))

    user = dict(user_row)
    user["initials"] = "".join(w[0] for w in user["name"].split()[:2]).upper()

    # Malformed dates are treated as absent (silent fallback to unfiltered).
    date_from = _parse_date(request.args.get("date_from", "").strip())
    date_to = _parse_date(request.args.get("date_to", "").strip())
    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = date_to = None

    date_filter = _build_date_filter(date_from, date_to, date.today())

    summary = get_summary_stats(user_id, date_from, date_to)
    stats = {
        "total_spent": summary["total_spent"],
        "count": summary["transaction_count"],
        "top_category": summary["top_category"],
    }
    transactions = get_recent_transactions(
        user_id, date_from=date_from, date_to=date_to
    )
    breakdown = [
        {
            "name": row["name"],
            "total": row["amount"],
            "percent": row["pct"],
            # Bar widths are CSS classes (pct-0 … pct-100) so templates need no inline styles.
            "bar_class": "pct-{}".format(5 * round(row["pct"] / 5)),
        }
        for row in get_category_breakdown(user_id, date_from, date_to)
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        breakdown=breakdown,
        date_filter=date_filter,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
