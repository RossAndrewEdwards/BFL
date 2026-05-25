# 01 Platform and Governance Backlog

## Scope

This document covers platform setup, league governance, permissions, reporting, audit, and structural safety.

## Items

### BL-001 Add a leagues table and seed Invicta as the first league

Priority: `P0`
Related stories: `US-001`, `US-007`
Status: `Implemented`

Scope:

- Add a new `leagues` table.
- Seed the existing Invicta setup as league `1`.
- Include fields such as `name`, `club_name`, `status`, `description`, `contact_email`, `max_players`, `max_teams`, `created_at`, and `updated_at`.

### BL-002 Add league ownership to all league-scoped data

Priority: `P0`
Related stories: `US-007`, `US-008`, `US-010`, `US-012`, `US-013`, `US-014`
Status: `Implemented`

Scope:

- Add `league_id` to league-scoped tables.
- Scope users, fighters, stats, event results, teams, claim tokens, notifications, audit data, share links, and league-facing derived queries.
- Keep `seasons` platform-wide.

### BL-003 Expand roles to support site admin and league admin

Priority: `P0`
Related stories: `US-003`, `US-007`
Status: `Implemented`

Scope:

- Support at least `site_admin`, `league_admin`, and `player`.
- Add role-aware helpers and guards.
- Prepare the permission layer for membership-aware league roles.

### BL-004 Introduce league context helpers and query scoping

Priority: `P0`
Related stories: `US-007`, `US-019`, `US-020`
Status: `Implemented`

Scope:

- Add central helpers for current user, active league, admin guards, and scoped queries.
- Refactor route queries so league-scoped pages always filter by the active `league_id`.

### BL-005 Define migration and rollback plan

Priority: `P0`
Related stories: `US-021`
Status: `Implemented`

Scope:

- Write a migration checklist for converting the current data into the league-based model.
- Include backup steps for `league.db`.
- Include rollback steps if the migration fails.

### BL-006 Site-admin league management screens

Priority: `P1`
Related stories: `US-001`, `US-002`, `US-003`, `US-006`, `US-036`
Status: `Implemented`

Scope:

- Create and edit leagues.
- Manage league branding, quotas, status, and linked league operations from one workspace.
- Promote existing players to league admins from the same league-management flow.
- Reach league players, teams, and league admins from the same league workspace without a separate disconnected admin area.

### BL-014 Site-admin platform dashboard

Priority: `P1`
Related stories: `US-005`, `US-023`, `US-036`, `US-037`, `US-038`, `US-039`
Status: `Implemented`

Scope:

- Show league health, quota usage, activity, and operational signals.
- Keep the dashboard focused on platform oversight rather than day-to-day league operations.

### BL-015 Keep rules and season lifecycle site-admin only

Priority: `P1`
Related stories: `US-009`, `US-015`
Status: `Implemented`

Scope:

- Keep rules and season lifecycle under platform-admin-only control.
- Block league-admin access to those settings.

### BL-016 League-aware audit logging

Priority: `P1`
Related stories: `US-021`, `US-022`, `US-039`
Status: `Implemented`

Scope:

- Keep audit rows tagged to leagues where appropriate.
- Preserve platform-only audit and notice flows separately from league event traffic.

### BL-018 Refactor the app structure to support multi-league delivery

Priority: `P1`
Related stories: `US-025`
Status: `Implemented`

Scope:

- Split app logic into focused modules for auth, DB, routes, scoring, season logic, ops, public helpers, and player helpers.
- Keep behaviour stable while reducing risk for future multi-league work.

### BL-019 League setup template flow

Priority: `P2`
Related stories: `US-001`, `US-002`
Status: `Implemented`

Scope:

- Provide starter templates when creating a new league.
- Apply sensible defaults for status, quotas, and setup fields without copying another league's data.

### BL-020 Better league admin activity reporting

Priority: `P2`
Related stories: `US-005`, `US-022`, `US-023`, `US-039`
Status: `Implemented`

Scope:

- Expand platform reporting with activity feeds, filters, season windows, and operational signals.
- Keep platform notices and reporting focused on oversight rather than league update noise.

### BL-047 Simplify league configuration for the one-team model

Priority: `P3`
Related stories: `US-004`, `US-070`
Status: `Implemented`

Scope:

- Rework league setup so platform admins can focus on maximum players, with team capacity following player capacity in the one-team-per-player model.
- Remove duplicated league-member and team listings from the main league settings form when the same information is already available through league operations.
- Keep page titles and labels concise and aligned with the simplified team model.

Definition of done:

- League configuration reflects the one-player-to-one-team model cleanly.
- League edit pages avoid duplicating data that belongs in linked operations pages.

### BL-048 Separate rules settings from season settings more clearly

Priority: `P3`
Related stories: `US-009`, `US-082`
Status: `Planned`

Scope:

- Move rule-owned values such as scoring values, training/support attendance values, and formula controls into the rules settings area.
- Move season-owned controls such as season lifecycle, rollover, and season-end behaviour into the season settings area.
- Remove confusing overlap between the two settings screens.

Definition of done:

- Platform admins can clearly tell which settings belong to rules and which belong to season control.
- The rules page and season settings page no longer mix responsibilities in a confusing way.

## Notes

- This backlog area is largely complete.
- Future work here is more likely to be polish, reporting refinements, or simplifying configuration and settings ownership around the one-team model.
