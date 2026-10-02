# Spec: Registration

## Overview

Make the existing `/register` page functional. Users can create a Spendly account by submitting their name, email, password and password confirmation; the account is stored in the `users` table with a hashed password. This is the first step of authentication and unblocks login (Step 3) and every per-user feature after it.
on the succes user is shown with the success message and then redirect to the login page.this is the entry point of the evry authanticated features that follow

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`)

## Routes

- `GET /register` — render the registration form — public (already exists, unchanged)
- `POST /register` — validate input, create the user, redirect to `/login?registered=1` on success (the login page shows a success message); re-render the form with an error message on failure — public

The existing `register()` view in `app.py` becomes a single view accepting `methods=["GET", "POST"]`.

## Database changes

No database changes. The existing `users` table already has `name`, a `UNIQUE` `email`, `password_hash` and `created_at`.

## Templates

- **Create:** none
- **Modify:**
  - `templates/register.html` — add a `confirm_password` field; repopulate `name` and `email` after a failed submit (`value="{{ name or '' }}"`, `value="{{ email or '' }}"`). Never repopulate either password.
  - `templates/login.html` — show "Account created successfully. Please sign in." when `request.args.registered` is set.

## Files to change

- `app.py` — handle `POST /register`
- `templates/register.html` — confirm-password field; repopulate name/email on error
- `templates/login.html` — success message after registering
- `static/css/style.css` — `.auth-success` style (CSS variables only)

## Files to create

None.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (`generate_password_hash`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `get_db()` from `database/db.py` and close the connection in a `try/finally`
- Trim whitespace from name and email; lower-case the email before checking and storing it
- Validation (server-side, each failure re-renders the form with HTTP 400 and a specific error):
  - name, email, password and confirm password are all required → "All fields are required."
  - email must contain an `@` with text on both sides
  - password must be at least 8 characters (matches the form placeholder)
  - password and confirm password must match → "Passwords do not match."
- Duplicate email: catch `sqlite3.IntegrityError` from the `UNIQUE` constraint (do not rely on a prior SELECT alone) and show "Email already registered"
- On success redirect to `url_for("login", registered=1)`; do not log the user in (sessions arrive in Step 3)
- Do not add a secret key, sessions or flash messages in this step (the success message is driven by the query parameter)

## Definition of done

- [ ] `GET /register` renders the registration form without errors
- [ ] Submitting the form with all valid fields creates a new user in `users` and redirects to `/login`
- [ ] Submitting with mismatched passwords re-renders the form with an error message, no DB insert
- [ ] Submitting with an already-registered email re-renders the form with "Email already registered" error
- [ ] Submitting with any empty field re-renders the form with a validation error
- [ ] Password is stored as a hash — never plaintext — verifiable by inspecting `expense_tracker.db`
- [ ] No duplicate user is created on repeated valid submissions with the same email
