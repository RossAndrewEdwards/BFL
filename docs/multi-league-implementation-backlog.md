# Multi-League Implementation Backlog

> The modular backlog set now lives in `docs/backlog/README.md`. This consolidated file is being kept as a legacy reference while planning documents are moved over.

## Goal

This backlog turns the approved multi-league user stories into a practical implementation plan for the current Flask + SQLite app.

The aim is to evolve the existing Invicta-only product into a shared platform where:

- one site admin controls the platform, rules, and season lifecycle
- each league admin manages only their own league
- each player can belong to multiple leagues and manages teams inside the currently selected league context

## Current State Summary

The current app is still built around a single-league model:

- one `admin` role and one `player` role
- global `fighters`, `event_results`, `fantasy_teams`, and most admin screens
- global homepage rankings and top-team views
- site-wide rules and season management already exist, which is good and should stay centralised
- no league table or league-based access boundary in the data model

Because of that, the first work must focus on data model changes and access scoping before we add league management screens.

## Delivery Principles

- Keep site-wide scoring, budget, roster, and season rules centralised.
- Scope fighter, event, player, team, and standings data to a league.
- Allow a user to hold memberships in multiple leagues while acting in one active league context at a time.
- Apply quotas only to players and teams.
- Keep one shared homepage, but show league-specific featured content only to logged-in users.
- Keep logged-out access limited to the homepage and rules page.
- Use neutral platform branding for logged-out users and league-aware branding for logged-in users.
- Treat the shared Buhurt calendar as the source for scheduled events wherever practical.
- Prefer safe migration steps that preserve the existing Invicta data as the first seeded league.

## MVP Release Target

The smallest release that satisfies the new direction is:

- create leagues
- assign league admins
- scope data to leagues
- enforce team and player quotas
- let league admins manage fighters, events, players, and teams inside their league
- let players join multiple leagues and create teams inside each eligible league context
- keep logged-out users limited to a safe public view with no player data exposure
- let the site admin view all leagues from one dashboard
- keep rules and season lifecycle site-admin only

## Backlog Structure

- `P0`: foundation work required before multi-league features can work safely
- `P1`: MVP features needed for launch
- `P2`: follow-up improvements after MVP is stable

## P0 Foundation

### BL-001 Add a leagues table and seed Invicta as the first league

Priority: `P0`
Related stories: `US-001`, `US-007`

Scope:

- Add a new `leagues` table.
- Seed the existing Invicta setup as league `1`.
- Include fields such as `name`, `club_name`, `status`, `description`, `contact_email`, `max_players`, `max_teams`, `created_at`, and `updated_at`.

Definition of done:

- Existing data migrates safely into a first league record.
- The app can load a current league record from the database.
- No existing pages break after the migration.

Dependencies:

- None

### BL-002 Add league ownership to all league-scoped data

Priority: `P0`
Related stories: `US-007`, `US-008`, `US-010`, `US-012`, `US-013`, `US-014`

Scope:

- Add `league_id` to league-scoped tables.
- At minimum scope: `users`, `fighters`, `baseline_stats`, `attendance_scores`, `fighter_import_totals`, `event_results`, `fantasy_teams`, `claim_tokens`, `notifications`, `audit_logs`, `team_share_links`, and any derived league-facing queries that need league filtering.
- Review whether `seasons` remains platform-wide. Based on the agreed direction, it should remain platform-wide.

Definition of done:

- Existing Invicta rows are backfilled to the seeded league.
- New inserts require a `league_id` where appropriate.
- Foreign keys and indexes support league-scoped filtering.

Dependencies:

- `BL-001`

### BL-003 Expand roles to support site admin and league admin

Priority: `P0`
Related stories: `US-003`, `US-007`

Scope:

- Replace the current two-role model with at least:
  - `site_admin`
  - `league_admin`
  - `player`
- Add role-aware helper functions and guards.
- Prepare the permission layer so league roles can be enforced cleanly even if membership later becomes many-to-many.

Definition of done:

- The permission layer can distinguish site-wide and league-only actions.
- The seeded admin account is converted to `site_admin`.
- League admin users can be created and tied to a league.

Dependencies:

- `BL-001`
- `BL-002`

### BL-004 Introduce league context helpers and query scoping

Priority: `P0`
Related stories: `US-007`, `US-019`, `US-020`

Scope:

- Add central helpers such as:
  - current user
  - current league for user
  - site-admin guard
  - league-admin guard
  - query filters for league-scoped records
- Refactor route queries so they always filter by `league_id` unless the route is explicitly site-wide.

Definition of done:

- League admins and players cannot access another league's records through direct URLs.
- Shared pages show only the current user's league data unless the viewer is a site admin.
- League scoping logic lives in one reusable place, not scattered ad hoc.

Dependencies:

- `BL-002`
- `BL-003`

### BL-005 Define migration and rollback plan

Priority: `P0`
Related stories: `US-021`

Scope:

- Write a migration checklist for converting the current production-style data into the new model.
- Include backup steps for `league.db`.
- Include rollback steps if the migration fails.

Definition of done:

- A clear migration runbook exists.
- We know how to recover the existing Invicta data if something goes wrong.

Dependencies:

- `BL-001`
- `BL-002`

## P1 MVP Features

### BL-006 Site-admin league management screens

Priority: `P1`
Related stories: `US-001`, `US-002`, `US-003`, `US-006`

Scope:

- Add site-admin pages to:
  - create a league
  - edit league details
  - promote existing players to league admins from the same league management flow
  - reassign or remove league-admin access from the same league management flow
  - activate, suspend, or archive a league
  - view league quotas and usage
  - review the league's current players, teams, and league admins
- Include league branding management such as:
  - league logo used in the logged-in shared header
  - league details needed for league-aware presentation

Definition of done:

- A site admin can manage leagues without touching the database manually.
- League admin assignment does not require a separate standalone admin area.
- Existing eligible players are available for later promotion to league admin from league management.
- The league-management flow does not need a separate player-creation path just to assign league admins.
- Suspended or archived leagues behave correctly in UI and permissions.

Dependencies:

- `BL-001`
- `BL-003`
- `BL-004`

### BL-007 League-admin assignment workflow inside league management

Priority: `P1`
Related stories: `US-003`

Scope:

- Allow the site admin to promote existing players as league admins from the main league management screens.
- Allow league admin reassignment if a club changes owner.
- Ensure eligible existing players appear in the promotion flow without needing a separate admin-management area.
- Prevent league admins from switching their own league.

Definition of done:

- Each league can have one or more admins if desired.
- League admin access is restricted to assigned leagues only.
- The user flow for assigning league admins is embedded in league management rather than split across separate sections.

Dependencies:

- `BL-003`
- `BL-004`
- `BL-006`

### BL-008 League quotas for players and teams

Priority: `P1`
Related stories: `US-004`, `US-013`, `US-017`, `US-023`

Scope:

- Add quota fields and usage counters for:
  - maximum players
  - maximum teams
- Enforce quota checks in:
  - player creation and invites
  - team creation
  - any admin override flows that create players or teams

Definition of done:

- Player and team creation is blocked when quota is exceeded.
- League admins can see usage and remaining capacity.
- Error messaging is clear and specific.

Dependencies:

- `BL-001`
- `BL-004`

### BL-009 Scope fighters to the active league

Priority: `P1`
Related stories: `US-008`, `US-010`, `US-011`

Scope:

- Update fighter admin pages so league admins only see and edit fighters in their league.
- Ensure fighter detail, rankings, imports, and totals recalculate only within that league.
- Keep fighter data separate across leagues.

Definition of done:

- League admins can add and edit fighters only in their own league.
- Fighters from one league never appear in another league's drafts, tables, or searches.

Dependencies:

- `BL-002`
- `BL-004`

### BL-010 Scope event management to the active league

Priority: `P1`
Related stories: `US-012`, `US-029`

Scope:

- Update event admin pages so event rows belong to a league.
- Ensure event-result calculations only use fighters from the same league.
- Allow direct event-result entry without requiring a scheduled event first.
- Keep optional scheduled-event linking compatible with league scoping when a league wants to use it.
- Keep event ownership and scoring responsibilities inside the league-admin workflow rather than relying on platform-admin event handling.

Definition of done:

- League admins can create and edit event results only for their league.
- Event scoring updates only that league's standings and fighter totals.
- Event-result entry works whether or not the league has pre-created scheduled events.

Dependencies:

- `BL-002`
- `BL-004`
- `BL-009`

### BL-011 Scope player memberships and update onboarding

Priority: `P1`
Related stories: `US-013`, `US-016`, `US-040`, `US-041`

Scope:

- Replace direct single-league assignment with league membership records.
- Update invite, claim, and join flows to add or update league memberships cleanly.
- Allow one user account to belong to multiple leagues without mixing permissions or data.
- Define one active league context for league-scoped pages after login.
- Keep league-admin onboarding focused on join-code and membership flows rather than direct player creation by league admins.

Definition of done:

- A player can join more than one league when invited or approved.
- Claim links and login flows add or preserve the correct league membership.
- The app can resolve which league context the user is currently acting in.
- League admins do not need a direct player-creation workflow in order to add people to their league.

Dependencies:

- `BL-002`
- `BL-003`
- `BL-004`

### BL-012 Scope teams to one league and enforce league-safe roster building

Priority: `P1`
Related stories: `US-014`, `US-017`, `US-018`

Scope:

- Ensure every team belongs to one league through player membership and direct league scoping.
- Restrict team builder options to fighters from the same league.
- Keep site-wide validation rules for budget, roster size, and duplicates.

Definition of done:

- Teams only contain fighters from the same league.
- League admins only manage teams from their own league.
- Players only manage their own teams within the currently selected league context.

Dependencies:

- `BL-004`
- `BL-009`
- `BL-011`

### BL-013 Shared homepage with league-aware featured content

Priority: `P1`
Related stories: `US-016`, `US-021`

Scope:

- Keep one shared homepage template.
- Make homepage featured sections league-aware for logged-in users:
  - top fighters
  - top teams
  - latest event summary where relevant
- Keep logged-out users on a restricted public version of the homepage with:
  - no top fighters
  - no top teams
  - no league/player performance data
- Use neutral `Buhurt Fantasy League` branding for logged-out users.
- Show league name and league logo in the shared header for logged-in users where configured.

Definition of done:

- Logged-in users see featured league data for their own league.
- Logged-out users do not see fighter, team, or standings data on the homepage.
- Logged-out branding remains neutral and not tied to a specific club league.
- Logged-in users can clearly see which league they are in from the shared header.
- Public and logged-out behaviour is explicit and consistent.

Dependencies:

- `BL-004`
- `BL-009`
- `BL-010`
- `BL-012`

### BL-014 Site-admin platform dashboard

Priority: `P1`
Related stories: `US-005`, `US-022`

Scope:

- Build a site-admin dashboard listing all leagues with summary metrics:
  - status
  - player count
  - team count
  - fighter count
  - recent activity
  - quota usage
- Keep the platform dashboard focused on oversight rather than day-to-day league operations.
- Prefer league-first navigation from the dashboard into a selected league workspace instead of primary top-level shortcuts for league fighters or league teams.

Definition of done:

- A site admin can quickly assess league health in one view.
- Metrics are accurate and filterable enough for operational use.

Dependencies:

- `BL-006`
- `BL-008`
- `BL-009`
- `BL-010`
- `BL-011`
- `BL-012`

### BL-015 Keep rules and season lifecycle site-admin only

Priority: `P1`
Related stories: `US-009`, `US-015`

Scope:

- Confirm `rules`, `settings`, and `seasons` remain platform-wide.
- Keep rules pages site-admin only.
- Keep end-season, reopen-season, and season settings under site-admin only.
- Remove any future path that would accidentally expose these actions to league admins.

Definition of done:

- Only site admins can edit rules or season lifecycle.
- League admins can view relevant outputs but cannot change platform rules.

Dependencies:

- `BL-003`
- `BL-004`

### BL-016 League-aware audit logging

Priority: `P1`
Related stories: `US-021`

Scope:

- Add `league_id` to audit records for league-scoped actions.
- Keep platform-level entries for site-wide changes such as rules and season lifecycle.
- Add league filters to the audit page.
- Keep platform-admin notifications and audit surfacing focused on platform-level changes rather than routine league event-update traffic.

Definition of done:

- Site admins can review activity across all leagues.
- League-specific admin actions are traceable by league.

Dependencies:

- `BL-002`
- `BL-004`

### BL-017 Tests for league isolation and permissions

Priority: `P1`
Related stories: `US-007`, `US-009`, `US-015`, `US-016`, `US-021`

Scope:

- Add route and data tests covering:
  - league admin cannot see another league's fighters
  - player cannot edit another league's team
  - quota limits block creation
  - site admin can manage all leagues
  - league admin cannot edit site-wide rules
  - homepage featured content switches by league context for logged-in users
  - logged-out users can access only the homepage and rules page
  - logged-out users do not see top fighters, top teams, or other player data
  - logged-in headers show league context and optional league logo correctly
  - multi-league members can switch active league context safely
  - league membership does not leak data between joined leagues

Definition of done:

- The core multi-league behaviours are covered by automated tests.
- Regression risk for access control is materially reduced.

Dependencies:

- Depends on the main MVP items it verifies

### BL-018 Refactor the app structure to support multi-league delivery

Priority: `P1`
Related stories: `US-024`

Scope:

- Keep `app.py` as a thin Flask entrypoint.
- Extract database setup and migration helpers into a dedicated module.
- Extract authentication, role checks, and league-context helpers into dedicated modules.
- Begin separating route groups so public, site-admin, league-admin, and player concerns are easier to maintain.
- Preserve behaviour while reducing the risk of adding future multi-league features into one oversized file.

Definition of done:

- `app.py` is materially smaller and easier to navigate.
- Database/bootstrap logic is no longer mixed into the main route file.
- Auth and permission helpers are no longer mixed into the main route file.
- The refactor does not introduce intentional behaviour changes.
- Automated tests still pass.

Dependencies:

- `BL-001`
- `BL-002`
- `BL-003`
- `BL-004`

## P2 Follow-Up Improvements

### BL-019 League setup template flow

Priority: `P2`
Related stories: `US-001`

Scope:

- Allow a new league to be created from a starter template instead of from scratch.
- Optionally copy default structures without copying actual fighter data.

### BL-020 Better league admin activity reporting

Priority: `P2`
Related stories: `US-005`, `US-022`

Scope:

- Add trend views, inactive-league alerts, and richer operational insights.
- Keep platform-level reporting focused on league health, platform operations, and exceptions rather than routine league event-update notifications.

### BL-021 Multi-league membership and context switching

Priority: `P2`
Related stories: `US-040`, `US-041`

Scope:

- Introduce a `league_memberships` model so a single user can belong to multiple leagues.
- Add active league context selection after login and from the shared header.
- Support membership-aware permissions where a user can be a player in one league and a league admin in another.
- Keep `site_admin` as a platform-wide role.

### BL-022 Bulk import and export per league

Priority: `P2`
Related stories: `US-010`, `US-012`

Scope:

- Support league-safe bulk fighter import, event import, and data export tools.

### BL-023 League workspace and hierarchy polish

Priority: `P2`
Related stories: `US-026`, `US-027`, `US-028`, `US-030`, `US-032`, `US-036`, `US-037`, `US-038`, `US-039`

Scope:

- Make `My League` the clear operational home for league admins.
- Improve league-first navigation for fighters, teams, and events.
- Reduce reliance on flat top-level admin entry points where league-first hierarchy is clearer.
- Remove the need for a separate top-level `Admin` header entry for league admins when `My League` already covers league operations.
- Keep `My League` focused on summary information, branding, quota visibility, join-code tools, and links out to dedicated pages rather than duplicating full member-management tables.
- Keep player promotion and other detailed member-management actions on the dedicated players page instead of in the `My League` dashboard.

### BL-024 Join-code and participation flows

Priority: `P2`
Related stories: `US-033`, `US-034`, `US-035`, `US-040`

Scope:

- Add reusable join-code flows that add a player to a league membership.
- Give each league a join code that a league admin can view and regenerate.
- Ensure quotas are checked when join codes are used.
- Support league admins participating as players within their own leagues under normal rules.
- Make join-code entry the normal league-admin-supported path for adding players into a league instead of direct player creation by league admins.

### BL-025 Interactive live event scoring workspace

Priority: `P2`
Related stories: `US-012`, `US-029`, `US-042`

Scope:

- Replace the current single-form event-entry flow with a scoring workspace better suited to reviewing live streams or recorded fights.
- Allow a league admin to create one event session and add grouped sections within it, such as matches, pools, teams, or fight segments.
- Let the admin add fighters from the current league into those groups and update each fighter's result progressively instead of in one large submission.
- Show completion state so the admin can tell which fighters or groups still need review.

Definition of done:

- A league admin can open one event workspace and score multiple fighters inside grouped sections.
- Event scoring can be saved iteratively while the admin is still watching or reviewing footage.
- The UI makes it obvious which results are complete, incomplete, or still in draft.
- Final event scoring still updates only the current league.

### BL-026 Sync scheduled events from the Buhurt calendar

Priority: `P2`
Related stories: `US-012`, `US-039`, `US-043`

Scope:

- Use the shared Buhurt calendar shown on the homepage as the source for scheduled event generation.
- Import or generate scheduled event rows with available metadata such as name, date, location, and source URL.
- Prevent obvious duplicate scheduled events when the same calendar item is synced more than once.
- Let league admins start scoring from these generated events while still allowing manual event entry when a calendar item is missing.

Definition of done:

- Scheduled events can be generated from the shared calendar feed.
- League admins can select one of those generated events when starting event scoring.
- Syncing the calendar does not create duplicate scheduled events for the same real fixture.
- Manual event creation still exists as a fallback when the shared calendar does not include the event.

## Current Backlog Status

- `Implemented`: `BL-001` through `BL-026`
- `Refinement likely after hands-on review`: `BL-025`, `BL-026`
- `Optional cleanup rather than missing product capability`: legacy membership fallbacks that still read from `users.league_id` or `users.role` in a few compatibility paths

The practical takeaway is that the backlog now has an implementation pass end to end. What remains is refinement based on real usage, especially around the richer event-scoring workflow and the exact admin UX you want to keep or simplify.

## User Story Traceability

This section maps every user story to the backlog items that implement or complete it.

Status meanings:

- `Implemented`: already covered by the current app and prior delivery work
- `Planned`: represented in backlog work but not fully complete yet
- `Partial`: some support exists, but additional backlog items are still needed to satisfy the story cleanly

| User story | Coverage | Status |
| --- | --- | --- |
| `US-001 Create a league` | `BL-001`, `BL-006`, `BL-019` | `Implemented` |
| `US-002 Edit league settings` | `BL-006` | `Implemented` |
| `US-003 Assign a league admin` | `BL-003`, `BL-006`, `BL-007` | `Implemented` |
| `US-004 Set league quotas` | `BL-008` | `Implemented` |
| `US-005 Monitor league health` | `BL-014`, `BL-020` | `Implemented` |
| `US-006 Suspend or archive a league` | `BL-006` | `Implemented` |
| `US-007 Keep league data isolated` | `BL-002`, `BL-004`, `BL-017` | `Implemented` |
| `US-008 Support league-specific fighter pools` | `BL-002`, `BL-009` | `Implemented` |
| `US-009 Manage site-wide rules` | `BL-015`, `BL-017` | `Implemented` |
| `US-010 Manage fighters` | `BL-009`, `BL-022` | `Implemented` |
| `US-011 Update fighter stats` | `BL-009` | `Implemented` |
| `US-012 Add and manage event data` | `BL-010`, `BL-022`, `BL-025`, `BL-026` | `Implemented` |
| `US-013 Manage league players` | `BL-008`, `BL-011`, `BL-024` | `Partial` |
| `US-014 Manage league teams` | `BL-012` | `Implemented` |
| `US-015 Manage season lifecycle` | `BL-015` | `Implemented` |
| `US-016 Public access stays restricted` | `BL-013`, `BL-017` | `Implemented` |
| `US-017 Join a league` | `BL-008`, `BL-011`, `BL-024` | `Implemented` |
| `US-018 Create a team within quota` | `BL-008`, `BL-012` | `Implemented` |
| `US-019 Manage my own team` | `BL-004`, `BL-012` | `Implemented` |
| `US-020 View league standings` | `BL-004`, `BL-013` | `Implemented` |
| `US-021 View league-specific content on a shared site` | `BL-005`, `BL-013`, `BL-016`, `BL-017` | `Implemented` |
| `US-022 Audit important changes` | `BL-016`, `BL-020` | `Implemented` |
| `US-023 Report platform usage` | `BL-014`, `BL-020` | `Implemented` |
| `US-024 Handle quota breaches gracefully` | `BL-008` | `Implemented` |
| `US-025 Refactor the application structure for multi-league growth` | `BL-018` | `Implemented` |
| `US-026 Manage a league from one workspace` | `BL-006`, `BL-023` | `Implemented` |
| `US-027 Use My League as a dashboard` | `BL-023` | `Implemented` |
| `US-028 Reach fighter management from My League` | `BL-009`, `BL-023` | `Implemented` |
| `US-029 League admins own event result updates` | `BL-010`, `BL-023`, `BL-025` | `Implemented` |
| `US-030 Reach team management from My League` | `BL-012`, `BL-023` | `Implemented` |
| `US-031 Manage players and player team limits within league quota` | `BL-008`, `BL-011`, `BL-024` | `Implemented` |
| `US-032 See quota usage in My League` | `BL-008`, `BL-023` | `Implemented` |
| `US-033 Manage a league join code` | `BL-024` | `Implemented` |
| `US-034 League admins can also participate as players` | `BL-024` | `Implemented` |
| `US-035 Quotas apply at league level` | `BL-008`, `BL-024` | `Implemented` |
| `US-036 View league quota usage as a platform admin` | `BL-006`, `BL-014`, `BL-023` | `Implemented` |
| `US-037 Use league-first admin hierarchy for teams` | `BL-014`, `BL-023` | `Implemented` |
| `US-038 Use league-first admin hierarchy for fighters` | `BL-014`, `BL-023` | `Implemented` |
| `US-039 Use league-first admin hierarchy for events` | `BL-014`, `BL-016`, `BL-020`, `BL-023`, `BL-026` | `Implemented` |
| `US-040 Join multiple leagues` | `BL-011`, `BL-021`, `BL-024` | `Implemented` |
| `US-041 Switch league context from the header` | `BL-011`, `BL-021` | `Implemented` |
| `US-042 Use an interactive live event entry workflow` | `BL-025` | `Implemented` |
| `US-043 Auto-generate scheduled events from the Buhurt calendar` | `BL-026` | `Implemented` |

## Current Gaps To Watch

- The backlog no longer has mandatory delivery gaps; the remaining work is refinement.
- The most likely refinement area is `BL-025`, especially the speed and ergonomics of the live scoring workspace during real event review.
- The second likely refinement area is `BL-026`, especially how much control league admins should have over synced calendar events versus manual event sessions.
- A few compatibility queries still fall back to `users.league_id` or `users.role`; the product works, but a cleanup pass would make the multi-membership model more internally consistent.
- Future review should focus on product fit, workflow friction, and UI simplification rather than missing core architecture.

## Recommended Delivery Order

### Phase 1: Data and access foundation

- `BL-001`
- `BL-002`
- `BL-003`
- `BL-004`
- `BL-005`

### Phase 2: Core admin operations

- `BL-006`
- `BL-007`
- `BL-008`
- `BL-015`
- `BL-016`

### Phase 3: Structural refactor for safe delivery

- `BL-018`

### Phase 4: League-scoped league-admin tools

- `BL-009`
- `BL-010`
- `BL-011`
- `BL-012`

### Phase 5: User-facing experience and reporting

- `BL-013`
- `BL-014`
- `BL-017`

### Phase 6: Membership expansion and hierarchy polish

- `BL-021`
- `BL-023`
- `BL-024`

### Phase 7: Event workflow upgrades

- `BL-025`
- `BL-026`

## Suggested First Sprint

If we want to start safely, the best first sprint is:

- `BL-001 Add a leagues table and seed Invicta as the first league`
- `BL-002 Add league ownership to all league-scoped data`
- `BL-003 Expand roles to support site admin and league admin`
- `BL-004 Introduce league context helpers and query scoping`

This gives us the minimum architecture to start moving screens over without creating security holes.

## Technical Notes for This Codebase

- `app.py` is currently a large single-file app, so league-scoping helpers should be introduced early to avoid repeating permission logic everywhere.
- The existing `admin_required` guard will likely need to split into `site_admin_required` and `league_admin_or_site_admin_required`.
- Existing seed data should become the first Invicta league instead of being treated as global data.
- Homepage queries, leaderboard queries, fighter totals, team validation, and event scoring should all be reviewed for hidden global assumptions.
- Public navigation and homepage sections should be reviewed carefully so logged-out users do not leak league data through headers, cards, or direct URLs.
- Season data should remain platform-wide based on the product decision already agreed.

## Risks to Watch

- Missed unscoped queries could leak data between leagues.
- Migration mistakes could orphan existing records if `league_id` backfills are incomplete.
- Role changes could accidentally lock out the current admin during migration.
- Homepage and leaderboard logic may appear correct while still using global aggregates underneath.
- Claim-token and player onboarding flows may silently attach users to the wrong league if not tested carefully.

## Exit Criteria for MVP

- A site admin can create and manage multiple leagues.
- A site admin can assign league admins from the same league management area and set player and team quotas.
- League admins can manage only their own fighters, players, teams, and events.
- Players can belong to multiple leagues, but only act within one selected league context at a time.
- Rules and season lifecycle remain site-admin only.
- Logged-out users can access only the homepage and rules page, and do not see player data.
- Homepage featured content responds to the logged-in user's league.
- Core league-isolation scenarios are covered by tests.
