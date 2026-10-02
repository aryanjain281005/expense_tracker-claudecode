# Spec: Login and Logout

## Overview

Make the existing `/login` page functional and implement `/logout`. A registered user signs in with email and password; on success their `user_id` is stored in the Flask session and they are sent to the landing page. Logging out clears the session. This is the second half of authentication, builds directly on registration (Step 2), and gives later steps (profile, expenses) a way to know who the current user is. It also fixes the current "Method Not Allowed" on submitting the login form, which only accepts GET today.

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`)
- Step 2 — Registration (users exist with werkzeug password hashes; `/login?registered=1` success banner)

## Routes

- `GET /login` — render the login form; if already logged in, redirect to `/` — public (exists, modified)
- `POST /login` — validate credentials, start the session, redirect to `/`; on failure re-render the form with an error and HTTP 401 — public
- `GET /register`, `POST /register` — also redirect to `/` when already logged in (the user must log out first) — public (exists, modified)
- `GET /logout` — clear the session and redirect to `/login` — logged-in (harmless if not logged in; it just redirects) (exists as a placeholder, replaced)

`/profile` stays a placeholder (Step 4) and is not used as a redirect target.

## Database changes

No database changes. The existing `users` table already has `email` (unique) and `password_hash`.

## Templates

- **Create:** none
- **Modify:**
  - `templates/login.html` — repopulate the `email` input after a failed attempt (`value="{{ email or '' }}"`); never repopulate the password. The existing `{{ error }}` and `registered` banners stay.
  - `templates/base.html` — navbar: when `session.user_id` is set, show a "Sign out" link to `/logout` instead of "Sign in" / "Get started".

## Files to change

- `app.py` — redirect logged-in users away from `/register`; secret key, session handling, `POST /login`, real `/logout`, import `session`, `check_password_hash`
- `templates/login.html` — repopulate email
- `templates/base.html` — logged-in navbar state

## Files to create

None.

## New dependencies

No new dependencies (`python-dotenv` is already in `requirements.txt`).

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug — verify with `check_password_hash`, never compare plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `get_db()` from `database/db.py` and close the connection in a `try/finally`
- Set `app.secret_key` from the `SECRET_KEY` environment variable (load `.env` with `python-dotenv`; `.env` is already gitignored). Do not commit a real key; fall back to a clearly named dev-only default only when the variable is unset
- Trim and lower-case the email before lookup (registration stores it lower-cased)
- Use one generic error for both unknown email and wrong password: "Invalid email or password." — do not reveal which was wrong
- Both empty-field cases show "Email and password are required." with HTTP 400
- Store only `session["user_id"]` (the integer id) in the session; call `session.clear()` before setting it on login
- `/logout` uses `session.clear()` and redirects to `url_for("login")`
- Do not add route protection or a login-required decorator in this step (Step 4 introduces `/profile`)

## Definition of done

- [ ] `GET /login` renders the form; `POST /login` no longer returns 405
- [ ] Logging in with the seeded demo user (`demo@spendly.com` / `demo123`) redirects to the landing page (`/`)
- [ ] Logging in with a user created through `/register` works
- [ ] Email lookup is case-insensitive (`Demo@Spendly.com` works)
- [ ] A wrong password and an unknown email both show "Invalid email or password." with no session set
- [ ] Submitting with an empty email or password shows a validation error
- [ ] After a failed attempt the email is pre-filled and the password is empty
- [ ] After login the navbar shows "Sign out" instead of "Sign in" / "Get started"
- [ ] Visiting `/login` while logged in redirects to the landing page (`/`)
- [ ] Visiting `/register` (GET or POST) while logged in redirects to `/` and creates no user
- [ ] `/logout` clears the session, redirects to `/login`, and the navbar shows "Sign in" again
- [ ] The session cookie is signed by `SECRET_KEY`; the app starts without errors when the variable is set and when it is unset
