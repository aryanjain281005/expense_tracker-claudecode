# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"Spendly" — a Flask + SQLite expense tracker built incrementally in numbered steps (see `.claude/specs/`). Step 1 (database setup) is done; most feature routes in `app.py` are placeholders returning "coming in Step N" strings.

## Commands

```bash
source venv/bin/activate
pip install -r requirements.txt
python app.py            # dev server at http://localhost:5001 (debug on)
pytest                   # pytest + pytest-flask are installed; no tests exist yet
pytest path/to/test_file.py::test_name   # single test
```

No linter is configured.

## Architecture

- `app.py` — Flask app and all routes. On import it runs `init_db()` and `seed_db()` inside `app.app_context()`, so the DB is created and seeded as a side effect of starting (or importing) the app.
- `database/db.py` — the whole data layer, using raw `sqlite3` (no ORM). `get_db()` opens a new connection per call (`row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON`); callers must close it (`try/finally`). `DB_PATH` resolves to `expense_tracker.db` in the project root (gitignored). Use `get_db()` rather than hardcoding the filename.
- Schema: `users` (unique `email`, `password_hash`) and `expenses` (`user_id` FK → users, `amount` REAL, `category`, `date` as `YYYY-MM-DD` text, optional `description`).
- `CATEGORIES` in `database/db.py` is the fixed category list: Food, Transport, Bills, Health, Entertainment, Shopping, Other.
- Templates extend `templates/base.html`; static assets in `static/`.

## Conventions (from the specs)

- Parameterised SQL only — never string-format queries.
- Hash passwords with `werkzeug.security.generate_password_hash`.
- Dates are always `YYYY-MM-DD`; amounts are floats (₹).
- `seed_db()` is a no-op once any user exists, so it will not re-seed a populated DB.

## Custom slash commands (`.claude/commands/`)

- `/create-spec <step> <name>` — creates a spec file and feature branch for the next step (requires a clean git working tree).
- `/seeds-user` — inserts one random Indian dummy user (password `password123`).
- `/seed-expense <user_id> <count> <months>` — inserts random dummy expenses for an existing user.
