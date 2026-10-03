# Spendly

A personal expense tracker built with **Flask** and **SQLite**. Sign up, log expenses in ₹, and see where your money goes, with a filterable profile dashboard.

**Live demo:** https://spendly-production-2a3b.up.railway.app

> The demo runs on ephemeral storage, so data resets whenever the service redeploys.

## Features

- **Accounts:** register, log in and log out, with passwords hashed using Werkzeug.
- **Add expenses:** amount, category, date and an optional description, validated on the server.
- **Profile dashboard:**
  - Summary cards: total spent, transaction count, top category.
  - Recent transactions table.
  - Category breakdown with percentage bars.
- **Date filters:** presets (This Month, Last 3 Months, Last 6 Months, All Time) or a custom range.
- **Seven fixed categories:** Food, Transport, Bills, Health, Entertainment, Shopping, Other.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Flask 3, raw `sqlite3` (no ORM) |
| Templates | Jinja2, vanilla CSS, Lucide icons |
| Tests | pytest, pytest-flask |
| Hosting | Railway (gunicorn) |

## Getting started

```bash
git clone https://github.com/aryanjain281005/expense_tracker-claudecode.git
cd expense_tracker-claudecode

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python app.py
```

Open http://localhost:5001. On first run the app creates `expense_tracker.db` and seeds a demo account:

| Email | Password |
|---|---|
| `demo@spendly.com` | `demo123` |

### Configuration

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session signing key | `dev-only-change-me` |
| `APP_ENV` | Set to `production` to require `SECRET_KEY` at startup | unset |

Variables can go in a local `.env` file (gitignored).

## Running tests

```bash
pytest                                    # full suite
pytest tests/test_07-add-expense.py       # one file
```

## Project structure

```
app.py               Flask app and routes
database/
  db.py              Connection, schema, seed data, CATEGORIES
  queries.py         Query helpers (stats, transactions, breakdown, insert)
templates/           Jinja2 templates extending base.html
static/              CSS and JS
tests/               pytest suite
.claude/specs/       Numbered feature specs, one per build step
Procfile             Production start command (gunicorn)
```

## Routes

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/` | public | Landing page |
| GET, POST | `/register` | public | Create an account |
| GET, POST | `/login` | public | Sign in |
| GET | `/logout` | logged-in | Sign out |
| GET | `/profile` | logged-in | Dashboard, supports `?date_from=&date_to=` |
| GET, POST | `/expenses/add` | logged-in | Add an expense |
| GET | `/expenses/<id>/edit` | logged-in | Edit expense (coming in Step 8) |
| GET | `/expenses/<id>/delete` | logged-in | Delete expense (coming in Step 9) |

## Deployment (Railway)

```bash
railway init --name spendly
railway variable set SECRET_KEY=<random-hex> APP_ENV=production
railway up
railway domain
```

SQLite lives on the container disk, so attach a Railway volume if you need data to survive redeploys.

## Roadmap

Built step by step from the specs in `.claude/specs/`:

1. Database setup
2. Registration
3. Login and logout
4. Profile page
5. Backend routes for the profile
6. Date filter
7. Add expense
8. Edit expense (next)
9. Delete expense

## Conventions

- Parameterised SQL only, never string-formatted queries.
- Dates are `YYYY-MM-DD`; amounts are floats in ₹.
- Templates extend `base.html`; CSS uses variables, no hardcoded colours.
