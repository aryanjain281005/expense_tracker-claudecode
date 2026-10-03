# Spec: Add Expense

## Overview

Step 7 replaces the `/expenses/add` placeholder with a working form that lets a
logged-in user record a new expense (amount, category, date, optional
description). Until now the only expenses came from seed or dummy data; this step
lets users create their own, which then appear on the profile page's summary
stats, recent transactions and category breakdown. On success the user is
redirected to `/profile`.

## Depends on

- Step 1: Database setup (`expenses` table, `CATEGORIES` in `database/db.py`)
- Step 3: Login and logout (`session["user_id"]`)
- Step 4/5: Profile page and its queries (to see the new expense after saving)

## Routes

- `GET /expenses/add` — render the add-expense form — logged-in
- `POST /expenses/add` — validate and insert the expense, then redirect to `/profile` — logged-in

Unauthenticated requests to either method redirect to `/login`.

## Database changes

No database changes. The existing `expenses` table (`user_id`, `amount REAL`,
`category`, `date TEXT`, `description`) is sufficient.

A new helper `add_expense(user_id, amount, category, date, description)` is added
to `database/queries.py` (a function, not a schema change).

## Templates

- **Create:** `templates/add_expense.html` — form with fields `amount`
  (number, step 0.01, min 0.01), `category` (select from `CATEGORIES`), `date`
  (`<input type="date">`, defaults to today), `description` (optional text).
  Shows an inline error message and re-populates the submitted values on failure.
  Cancel link back to `/profile`.
- **Modify:** `templates/profile.html` — add an "Add Expense" link/button to
  `url_for("add_expense")`.
- **Modify:** `templates/base.html` — only if the navbar for logged-in users
  should also link to Add Expense (optional, keep consistent with existing nav).

## Files to change

- `app.py` — implement `add_expense` view with `methods=["GET", "POST"]`; import
  `CATEGORIES` and the new query helper
- `database/queries.py` — add `add_expense(...)` insert helper
- `templates/profile.html` — add entry-point link
- `static/css/style.css` — styles for the form, using existing CSS variables

## Files to create

- `templates/add_expense.html`
- `tests/test_add_expense.py` (via `/test-feature`)

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (no password handling in this step; do not alter existing auth)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `get_db()` and close the connection in `try/finally`
- `user_id` comes from `session` only — never from form input
- Validation (server-side, return 400 with the form re-rendered and an error):
  - `amount` must parse as a float, be finite, and be > 0; store as float
  - `category` must be one of `CATEGORIES`
  - `date` must be a real `YYYY-MM-DD` date (reuse `_parse_date`); reject future dates is NOT required
  - `description` is optional, stripped, and capped at 200 characters
- Redirect to `/profile` after a successful insert (Post/Redirect/Get)
- Amounts are displayed in ₹

## Definition of done

- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Logged in, `/expenses/add` shows the form with all 7 categories and today's date pre-filled
- [ ] Submitting a valid expense redirects to `/profile` and the expense appears in Recent Transactions
- [ ] Profile total spent, transaction count and category breakdown reflect the new expense
- [ ] The saved row has the logged-in user's `user_id`, the amount stored as a float, and `YYYY-MM-DD` date
- [ ] Submitting an empty, zero, negative, or non-numeric amount shows an error and saves nothing
- [ ] Submitting an invalid category (tampered form) or malformed date shows an error and saves nothing
- [ ] On a validation error, previously entered values remain in the form
- [ ] Description is optional; leaving it blank saves successfully
- [ ] Profile page has a working link to the add-expense form
- [ ] No hardcoded hex colours are introduced
