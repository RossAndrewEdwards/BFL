# Project Directory Structure

This document gives a lightweight view of the current app structure so user-story review can be grounded in the real codebase layout.

## Top-Level Shape

```text
invicta_fantasy_webapp/
|-- app.py
|-- auth_support.py
|-- db_support.py
|-- form_support.py
|-- league_data_support.py
|-- ops_support.py
|-- player_support.py
|-- public_support.py
|-- quota_support.py
|-- scoring_support.py
|-- season_support.py
|-- tournament_support.py
|-- ui_support.py
|-- routes_admin_dashboard.py
|-- routes_admin_events.py
|-- routes_admin_fighters.py
|-- routes_admin_leagues.py
|-- routes_admin_league_admins.py
|-- routes_admin_ops.py
|-- routes_admin_players.py
|-- routes_admin_season_rules.py
|-- routes_admin_teams.py
|-- routes_player.py
|-- routes_public.py
|-- data/
|-- docs/
|-- scripts/
|-- static/
|-- templates/
|-- tests/
`-- README.md
```

## Key Areas

### Entry and Core Support

- `app.py`
  Main Flask entrypoint and application wiring.
- `*_support.py`
  Shared business logic for auth, scoring, league data, player logic, quotas, operations, and public payloads.

### Route Modules

- `routes_admin_*.py`
  Platform-admin and league-admin route groups split by feature area.
- `routes_player.py`
  Player auth, membership, join-code, and `My Team` flows.
- `routes_public.py`
  Shared public and logged-in non-admin browsing flows.

### Templates and Styling

- `templates/`
  Shared HTML templates for public pages, admin workflows, workspaces, cards, and player views.
- `static/styles.css`
  Main shared stylesheet, including workspace, leaderboard, and collectible-card styling.

### Planning and Product Docs

- `docs/user-stories/`
  Canonical modular user stories grouped by epic area.
- `docs/backlog/`
  Canonical modular backlog grouped by epic area.
- `docs/*.md`
  Supporting planning docs such as migration notes, release-readiness review, and schema proposals.

### Data and Testing

- `data/`
  Seed and supporting app data.
- `tests/`
  Unittest-based coverage for routes, templates, permissions, league scoping, and regressions.
- `scripts/`
  Utility scripts for checks and smoke testing.

## Review Focus

For product review, the most relevant folders are:

- `docs/user-stories/`
- `docs/backlog/`
- `templates/`
- `routes_admin_events.py`
- `routes_admin_leagues.py`
- `routes_player.py`
