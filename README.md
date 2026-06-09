# Invicta Fantasy League Web App

This is a Flask + SQLite MVP converted from the fantasy league workbook.

## What it does

- Admin login and admin-only edit screens
- Fighter rankings calculated from rules, baseline training/support and event results
- Fighter profile/detail pages
- Fantasy team pages with cost, remaining budget, validity and rank
- Admin controls for:
  - scoring rules
  - budget/team-size settings
  - fighter tier, cost, height, weight and profile fields
  - training/support baseline values
  - event result rows
  - fantasy team rosters
- Player login support with read-only `My Team` view

## Run locally

```bash
cd invicta_fantasy_webapp
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open: http://127.0.0.1:5000

## Testing

The repo keeps a lightweight Python-only test loop for routes, templates and app wiring:

```powershell
.\.venv\Scripts\python.exe scripts\dev_check.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe scripts\smoke_tests.py
```

Public tournament listings are refreshed from the MCSA GB UK events page and cached in SQLite for 12 hours. If the source cannot be reached, the app keeps the previous cached list or falls back to a small built-in list so the homepage still renders.

## Seeded accounts

Admin:

- username: `admin`
- password: `admin123`

Seeded player users are created from the fantasy team manager names. Their starting password is:

- password: `player123`

Change these before putting the app online. For a safer admin password on first run:

```bash
set INV_ADMIN_PASSWORD=your-new-password
python app.py
```

On macOS/Linux:

```bash
export INV_ADMIN_PASSWORD=your-new-password
python app.py
```

## Project Architecture & Modularization

The application is structured modularly:
- `app.py` — Main entrypoint and application wiring.
- `routes_*.py` — Scoped route modules split by role and concern (public, player, admin dashboards, leagues, events, fighters, etc.).
- `*_support.py` — Shared business logic helper modules (auth, database, scoring, quotas, etc.).
- `roster_engine.py` — Roster verification and budget validation.
- `templates/` — HTML pages.
- `static/` — CSS styles and other static assets.

For a detailed walkthrough of the project files and structure, see the [Project Directory Structure](file:///c:/Users/reods/Desktop/invicta_fantasy_webapp/docs/project-directory-structure.md) documentation.

## Running and Seed Data

- `data/seed.json` — Exported seed data from the workbook.
- `league.db` — Generated automatically on first run.

## How the workbook maps to the app

| Workbook area | Web app equivalent |
|---|---|
| Rules | Admin → Rules & Settings |
| Roster | Admin → Fighters |
| Baseline Stats | Fighter training/support fields |
| Event Log | Admin → Event Results |
| Fighter Rankings | Fighters page |
| Fantasy Teams | Teams + Admin Team Editor |
| Fighter Profile | Fighter detail page |

## Calculation notes

The app keeps the same scoring model from the sheet:

```text
Total points = training + competitions + support + medals + kills - deaths - sit-downs - cards
```

The exact values come from the editable rules table. Competitions are counted from event-result rows, while training and support are admin-maintained baseline values.

Fantasy team validity checks:

- minimum team size
- maximum team size
- duplicate fighters
- team budget

Invalid teams are visible but not ranked.
