from datetime import datetime

from database.db import get_db


def _date_clause(date_from, date_to):
    """Return (sql_fragment, params) restricting `date` to an inclusive range.

    Fragments are fixed strings; values are always passed as parameters.
    """
    clause, params = "", []
    if date_from:
        clause += " AND date >= ?"
        params.append(date_from)
    if date_to:
        clause += " AND date <= ?"
        params.append(date_to)
    return clause, params


# --- transactions ---
def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    clause, extra = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            f"WHERE user_id = ?{clause} ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *extra, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "date": r["date"],
            "description": r["description"] or "",
            "category": r["category"],
            "amount": r["amount"],
        }
        for r in rows
    ]

# --- end transactions ---


# --- stats ---
def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    member_since = datetime.strptime(
        row["created_at"], "%Y-%m-%d %H:%M:%S"
    ).strftime("%B %Y")
    return {"name": row["name"], "email": row["email"], "member_since": member_since}


def get_summary_stats(user_id, date_from=None, date_to=None):
    clause, extra = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            f"FROM expenses WHERE user_id = ?{clause}",
            (user_id, *extra),
        ).fetchone()
        top = conn.execute(
            f"SELECT category FROM expenses WHERE user_id = ?{clause} "
            "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id, *extra),
        ).fetchone()
    finally:
        conn.close()
    if totals["cnt"] == 0:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}
    return {
        "total_spent": round(float(totals["total"]), 2),
        "transaction_count": totals["cnt"],
        "top_category": top["category"],
    }
# --- end stats ---


# --- breakdown ---
def get_category_breakdown(user_id, date_from=None, date_to=None):
    clause, extra = _date_clause(date_from, date_to)
    db = get_db()
    try:
        rows = db.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            f"WHERE user_id = ?{clause} GROUP BY category ORDER BY total DESC",
            (user_id, *extra),
        ).fetchall()
    finally:
        db.close()

    grand = sum(r["total"] for r in rows)
    if not rows or grand <= 0:
        return []

    result = [
        {
            "name": r["category"],
            "amount": round(r["total"], 2),
            "pct": int(round(r["total"] * 100 / grand)),
        }
        for r in rows
    ]
    # make pcts sum to exactly 100 via the largest category
    result[0]["pct"] += 100 - sum(c["pct"] for c in result)
    return result
# --- end breakdown ---
