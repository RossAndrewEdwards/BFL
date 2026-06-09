# Multi-League User Stories

> The modular user story set now lives in [docs/user-stories/README.md](C:\Users\reods\Desktop\invicta_fantasy_webapp\docs\user-stories\README.md). This consolidated file is being kept as a legacy reference while planning documents are moved over.

## Purpose

This document expands the current Invicta-only app into a multi-club fantasy league platform. The goal is to let a site owner run the platform, allow each club to manage its own league independently, and keep data safely separated between leagues.

## Product Direction

The platform should evolve from a single-league application into a multi-tenant system with three main roles:

- Site Admin: owns the platform and oversees all leagues
- League Admin: manages one club league and its league data
- League Player: joins a specific league and manages their own team inside that league

## Core Assumptions

- A league represents one club's fantasy competition space.
- Each league has its own isolated fighter pool, player list, teams, event data, and standings.
- Scoring, roster, budget, and season rules are managed site-wide by the site admin and applied consistently across leagues.
- A site admin can control the size and limits of each league.
- A league admin can only manage their own league and must not see or edit another club's data.
- A player can belong to more than one league, but uses one active league context at a time when creating or managing a team.
- People who are not logged in can only access the shared homepage and the public rules page.
- People who are not logged in must not see player, fighter, team, or standings data.
- The shared public header should use platform branding such as `Buhurt Fantasy League`, while logged-in users should see which league they are currently in.
- League admins should be able to manage their league branding, including a league logo shown in the shared header for logged-in users in that league.
- Scheduled events should be seeded from the shared Buhurt calendar shown on the homepage so league admins can start from real upcoming fixtures rather than building the event list manually.

## Epic 1: Platform and League Management

### US-001 Create a league

As a site admin, I want to create multiple leagues so that different clubs can host their own fantasy leagues on the same platform.

Acceptance criteria:

- A site admin can create a new league with a name, club name, status, optional descriptive fields, and an optional league logo.
- A new league is provisioned with its own empty league data or a starter template.
- A league can be marked as active, inactive, archived, or pending setup.
- A site admin can assign one or more league admins as part of the same league management workflow.

### US-002 Edit league settings

As a site admin, I want to update league settings so that each club can be configured without developer involvement.

Acceptance criteria:

- A site admin can edit league name, description, logo, and contact details.
- A site admin can enable or disable selected league features.
- Changes apply only to the selected league unless they are explicitly platform-wide.
- When editing a league, a site admin can also see the league's current players, teams, and league admins in the same management area.
- A league logo can be uploaded or assigned so it appears in the shared header for logged-in users of that league.

### US-003 Assign a league admin

As a site admin, I want to assign one or more league admins to a league so that each club can manage its own competition.

Acceptance criteria:

- A site admin can promote an existing user to league admin for a specific league.
- A newly created user appears in the available list for later promotion to league admin.
- A league admin can only access leagues they have been assigned to.
- A site admin can revoke or replace league admin access at any time.
- League-admin assignment is managed from the main league management area rather than in a completely separate admin section.

### US-004 Set league quotas

As a site admin, I want to give a league a quota of teams and members so that league admins can manage their own club within agreed limits.

Acceptance criteria:

- A site admin can set maximum player count and maximum team count for a league.
- The platform warns the site admin when a league is approaching or has reached its quota.
- A league admin can view their remaining quota but cannot increase it themselves.

### US-005 Monitor league health

As a site admin, I want to see how all leagues are doing so that I can monitor adoption, engagement, and operational issues.

Acceptance criteria:

- A site admin dashboard shows summary metrics for every league.
- Metrics include at least active players, teams created, fighters listed, recent activity, and quota usage.
- A site admin can quickly identify inactive, full, or misconfigured leagues.

### US-006 Suspend or archive a league

As a site admin, I want to suspend or archive a league so that I can manage clubs that stop participating without deleting history.

Acceptance criteria:

- A suspended league becomes read-only or inaccessible based on platform rules.
- An archived league is hidden from normal discovery but retains historical data.
- Historical standings, fighters, and teams remain available to the site admin.

## Epic 2: League Isolation and Data Boundaries

### US-007 Keep league data isolated

As a site admin, I want league data to stay isolated so that clubs cannot accidentally see or edit each other's information.

Acceptance criteria:

- Fighters, events, teams, players, and standings are scoped to a league.
- A league admin cannot access another league's data by URL, search, or direct record ID.
- A player only sees leagues they are a member of, and only the currently selected league context is active in league-scoped views.

### US-008 Support league-specific fighter pools

As a league admin, I want my league to have its own fighter pool so that my club can run a fantasy competition with fighters relevant to us.

Acceptance criteria:

- A league admin can create, edit, deactivate, and remove fighters inside their own league.
- A fighter added to one league does not automatically appear in another league.
- Fighter rankings and team eligibility are calculated within that league context.

### US-009 Manage site-wide rules

As a site admin, I want to manage scoring and roster rules centrally so that all leagues follow the same fantasy framework.

Acceptance criteria:

- A site admin can manage platform-wide scoring settings, roster size rules, and budget rules.
- League admins cannot override site-wide rules.
- Rule changes apply consistently across all active leagues.

## Epic 3: League Admin Operations

### US-010 Manage fighters

As a league admin, I want to add as many fighters as I want within my league so that I can maintain a complete and accurate fantasy roster.

Acceptance criteria:

- A league admin can create fighter records with profile, ranking, tier, cost, and status data.
- A league admin can bulk import or manually enter fighters if that feature is enabled.
- Fighter management is not limited by player or team quotas.

### US-011 Update fighter stats

As a league admin, I want to update fighter stats so that rankings and fantasy outcomes stay current for my league.

Acceptance criteria:

- A league admin can update baseline training, support, medals, and other tracked attributes for fighters in their league.
- Changes recalculate league standings and team values where required.
- Updates are logged with timestamp and editor identity.

### US-012 Add and manage event data

As a league admin, I want to add event data for my league so that fantasy scoring reflects real competition outcomes.

Acceptance criteria:

- A league admin can enter event results for their league without first being forced to create a scheduled event.
- Scheduled events may still exist as an optional organisational tool, but they are not required for normal result entry.
- A league admin can enter event results tied to fighters in their league.
- A league admin can create one event-result session for a real fixture and record results for multiple fighters inside that session.
- Event entry supports draft-style data capture so a league admin can update the session while reviewing a live stream or replay before considering it complete.
- Event scoring updates only the affected league tables and rankings.

### US-042 Use an interactive live event entry workflow

As a league admin, I want an interactive event-entry workflow so that I can watch a fight on YouTube, create groups within the event, and enter each fighter's results as I review the action.

Acceptance criteria:

- A league admin can create an event entry workspace for a selected event or a manually named event.
- Within that event workspace, a league admin can create groups such as matches, pools, teams, or fight segments based on how they want to review the event footage.
- A league admin can add fighters from their own league into those groups and enter results for each individual fighter within the group.
- The workflow supports repeated updates while the admin is still reviewing footage and does not require all fighter outcomes to be entered in one form submission.
- The platform clearly shows which fighters in the event have already been scored and which still need review.
- Final scoring still remains scoped to the current league only.

### US-043 Auto-generate scheduled events from the Buhurt calendar

As a league admin, I want scheduled events to come from the shared Buhurt calendar so that real upcoming fixtures already exist in the system before I start entering results.

Acceptance criteria:

- The platform imports or generates scheduled events from the Buhurt calendar shown on the shared homepage.
- Auto-generated scheduled events include at least event name, date, and any available location or source-link details from the calendar feed.
- A league admin can choose one of these generated events as the starting point for scoring and result entry.
- The platform avoids creating obvious duplicate scheduled events when the same calendar item is synced more than once.
- If a real event is missing from the calendar, a league admin can still create a manual event entry for their league.

### US-013 Manage league players

As a league admin, I want to manage all players in my league so that I can help users join, participate, and remain within quota.

Acceptance criteria:

- A league admin can view players already in their league.
- A league admin can invite people to join the league by sharing the league join code.
- A league admin can see how many player slots are used and remaining.
- A league admin can update how many teams an existing player in their league is allowed to manage.
- A league admin cannot create brand new player accounts directly.
- A league admin cannot exceed the site-admin-defined member quota.

### US-014 Manage league teams

As a league admin, I want to manage all teams in my league so that I can correct issues and support players.

Acceptance criteria:

- A league admin can view every team in their league.
- A league admin can edit, lock, unlock, or remove teams when required by league policy.
- A league admin cannot manage teams belonging to another league.

### US-015 Manage season lifecycle

As a site admin, I want to manage the season lifecycle for the platform so that all leagues move through the season consistently.

Acceptance criteria:

- A site admin can mark the season as pre-season, active, completed, or archived.
- A site admin can trigger season rollover actions across the platform.
- Historical season data remains available for league and platform reporting.

## Epic 4: Player Experience

### US-016 Public access stays restricted

As a site admin, I want people who are not logged in to have a limited public view so that league and player data is protected.

Acceptance criteria:

- Logged-out visitors can access only the homepage and the rules page.
- Logged-out visitors cannot access fighters, teams, standings, player pages, or admin pages.
- Logged-out visitors do not see top fighters, top teams, or other league/player performance data on the homepage.
- The shared public header uses platform branding such as `Buhurt Fantasy League` rather than a specific league name.

### US-017 Join a league

As a league player, I want to join a specific league so that I can participate in my club's fantasy competition.

Acceptance criteria:

- A player can join a league through an invite, code, or admin assignment.
- A player can clearly see which league they are joining.
- A player cannot join a league that is closed, full, or inactive unless permitted by an admin.
- Joining a new league adds membership to the player's account rather than replacing existing valid league memberships.

### US-018 Create a team within quota

As a league player, I want to create my own team as long as I have been given enough quota so that I can participate without admin intervention.

Acceptance criteria:

- A player can create a team only if the league has available team quota and the player has permission to create one.
- The platform clearly explains when team creation is blocked by quota, status, or site-wide rules.
- Team creation validates site-wide rules such as budget, roster size, and duplicate restrictions against the selected league's fighter pool.

### US-019 Manage my own team

As a league player, I want to manage my own team within site-wide rules so that I can keep my fantasy picks competitive.

Acceptance criteria:

- A player can add, remove, and update fighters on their own team when the league allows it.
- Team changes are validated against the selected league's fighter pool and site-wide rules.
- A player cannot edit another player's team unless granted an admin role.

### US-020 View league standings

As a league player, I want to view standings and rankings for my league so that I can track my performance against other members.

Acceptance criteria:

- A player can view league tables, fighter rankings, and event outcomes for their own league.
- Shared public views show only the current league context.
- Standings do not mix data from other leagues.

### US-021 View league-specific content on a shared site

As a league player, I want to see my league's own fighters, events, and standings on the shared site experience so that the app stays relevant to my club without needing a separate homepage per league.

Acceptance criteria:

- The shared homepage remains the same across the platform.
- Logged-in users can see which league they are currently in from the shared header.
- Logged-in users can see that league's logo in the shared header when one has been configured.
- The featured top fighters and top teams update based on the logged-in user's league.
- Fighters and events shown to players belong only to that league.
- Navigation makes it clear which league the player is currently in.
- Logged-out visitors do not see top fighters, top teams, or other league/player performance data on the homepage.

## Epic 5: Reporting, Audit, and Safety

### US-022 Audit important changes

As a site admin, I want an audit trail for league changes so that I can investigate mistakes and maintain trust across clubs.

Acceptance criteria:

- Important admin actions are logged, including who changed what and when.
- Audit logs cover league settings, quota changes, fighter edits, event edits, player changes, and team overrides.
- A site admin can filter audit history by league.
- Platform-admin notifications focus on platform-level admin changes rather than league event-update traffic.

### US-023 Report platform usage

As a site admin, I want platform-level reporting so that I can understand growth and decide where to invest next.

Acceptance criteria:

- Reports can summarize leagues, players, teams, and activity over time.
- A site admin can compare league usage and growth trends.
- Reports can be filtered by season, league status, and date range.

### US-024 Handle quota breaches gracefully

As a league admin, I want the platform to handle quota breaches clearly so that I know what action is needed when limits are reached.

Acceptance criteria:

- The platform blocks new records that would exceed quota.
- The user sees a clear explanation of which quota was reached.
- Existing data remains accessible even when quota is full.

## Epic 6: Maintainability and Delivery Safety

### US-025 Refactor the application structure for multi-league growth

As a site owner, I want the application codebase to be split into clear modules so that multi-league features can be delivered more safely, tested more reliably, and maintained more easily over time.

Acceptance criteria:

- The Flask entrypoint remains lightweight and no longer contains most business logic directly.
- Database setup, authentication helpers, permissions, and league-scoping helpers are separated into clearer modules.
- Public routes, site-admin routes, league-admin routes, and player routes can be reasoned about independently.
- The refactor does not change existing user-facing behaviour unless explicitly planned.
- Automated tests still pass after the refactor.

## Non-Functional Requirements

- Security: league data must be securely partitioned by role and league
- Scalability: the platform should support many clubs without manual data separation
- Usability: users should always know which league they are viewing or editing
- Auditability: important changes should be traceable
- Configurability: site-wide rules and per-league quotas should be manageable without code changes

## Suggested MVP Scope

The smallest useful version of this multi-league expansion is likely:

- create and manage leagues
- assign league admins
- isolate league data
- set league member and team quotas
- allow league admins to manage fighters, events, players, and teams within their own league
- allow players to join a league and create teams within site-wide rules
- provide a site-admin dashboard across all leagues

## Confirmed Product Decisions

- A user can belong to multiple leagues, but must act inside one active league context at a time.
- League admins cannot customise scoring, roster, budget, or season rules.
- Fighter data stays inside each league and is not shared platform-wide.
- People who are not logged in can access only the homepage and rules page.
- People who are not logged in must not see top fighters, top teams, or other player/league data.
- The public header should use shared platform branding such as `Buhurt Fantasy League`.
- Logged-in users should always be able to see which league they are currently in.
- League admins should be able to upload or assign a league logo for use in the shared header.
- League admin assignment should happen from the main league management area rather than a separate standalone admin section.
- League admins should not need or use a separate top-level `Admin` area in the shared header. Their normal operational path should be through `My League`.
- When editing a league, the site admin should be able to review the league's players, teams, and league admins in the same place.
- Existing users must be available for later promotion to league admin.
- Platform admins promote existing players into league-admin roles rather than creating player accounts from the league-admin assignment area.
- The platform uses one shared homepage, but featured content such as top fighters and top teams updates based on the logged-in user's league.
- Paid subscription tiers are out of scope for now.

## Epic 7: League Workspace, Navigation, and Admin Hierarchy

### US-026 Manage a league from one workspace

As a league admin, I want one main area to manage my league and my league-admin tasks so that I do not have to jump between disconnected admin sections.

Acceptance criteria:

- A league admin has one clear `My League` workspace as their primary admin home.
- The workspace brings together league overview, branding, quota visibility, and links to league-specific admin tasks.
- A league admin does not need a separate standalone admin-management area to perform normal league operations.
- The shared header does not need a separate `Admin` entry for league admins when `My League` already serves that purpose.

### US-027 Use My League as a dashboard

As a league admin, I want `My League` to act as a dashboard for my league so that I can quickly understand the state of the league and move into the right admin pages.

Acceptance criteria:

- `My League` shows the current league name, status, branding, and high-level summary information.
- `My League` links to the main league-admin pages for fighters, events, players, and teams.
- The dashboard highlights the most important next actions for the league admin.
- `My League` stays focused and does not duplicate full member-management tables that already exist on dedicated pages.
- Player promotion and other detailed management actions should happen inside the relevant dedicated page rather than as a separate dashboard section.

### US-028 Reach fighter management from My League

As a league admin, I want `My League` to include a clear way into fighter management so that I can maintain the league fighter pool without searching through general admin navigation.

Acceptance criteria:

- `My League` includes a dedicated fighters section or shortcut.
- The fighters area opened from `My League` is scoped only to the current league.
- The navigation makes it clear that fighter management belongs to the league-admin workflow rather than the platform-admin workflow.

### US-029 League admins own event result updates

As a league admin, I want to add event updates and fighter stat changes for my own league so that the platform admin does not need to manage day-to-day competition data on behalf of clubs.

Acceptance criteria:

- A league admin can create and update event results for their league.
- A league admin can use a league-owned scoring workspace to enter grouped fighter results while reviewing event footage.
- Event-related fighter stat changes are managed from league-admin event workflows.
- The platform admin can still oversee league health, but normal event scoring responsibility sits with the league admin.

### US-030 Reach team management from My League

As a league admin, I want to manage teams from a dedicated page within my league workspace so that team administration feels like part of one coherent league flow.

Acceptance criteria:

- `My League` includes a dedicated teams section or shortcut.
- The teams page is scoped only to the current league.
- Team actions remain unavailable for other leagues.

### US-031 Manage players and player team limits within league quota

As a league admin, I want to manage players in my league, including how many teams a player can manage, so that I can control participation as long as the league still has enough quota.

Acceptance criteria:

- A league admin can view and manage players assigned to their league.
- A league admin can set or update how many teams a player is allowed to manage within the current rules.
- If a player should become a league admin, that promotion happens from the dedicated player-management flow rather than from the `My League` dashboard itself.
- Player creation and player team management remain blocked when the league quota has been reached.
- The league admin cannot bypass platform-defined quota limits.

### US-032 See quota usage in My League

As a league admin, I want to see my league quota and how much of it has been used inside `My League` so that I can manage invitations, players, and teams confidently.

Acceptance criteria:

- `My League` shows player quota usage and remaining player capacity.
- `My League` shows team quota usage and remaining team capacity.
- Quota information is visible without needing to open a separate reporting page.

### US-033 Manage a league join code

As a league admin, I want to have a reusable join code for my league so that I can give it to players and they can enter it in the app to join the league.

Acceptance criteria:

- Each league has a reusable join code that is tied to that league.
- A league admin can view the current join code for their league.
- A league admin can regenerate the join code when needed.
- A player can enter the join code in the app to join that league.
- The platform validates that the league is active, the code is valid, quota is available, and the player is not already a member before joining them to the league.
- Join-link use still respects league status and quota limits.

### US-034 League admins can also participate as players

As a league admin, I want to be able to play in the league and create a team as well so that club organisers can also take part in the fantasy competition.

Acceptance criteria:

- A league admin can also create and manage their own team within their league.
- A league admin's player participation still follows the same site-wide roster and budget rules as everyone else.
- Administrative permissions do not allow the league admin to bypass player-facing validation unfairly.

### US-035 Quotas apply at league level

As a league admin, I want quotas to apply at the league level so that I can invite players with a join code and assign teams to players as long as the league still has available quota.

Acceptance criteria:

- Player and team quotas are enforced against the league as a whole.
- A league admin can invite or assign players only while player quota remains available.
- A league admin can create or assign teams only while team quota remains available.
- Quota rules do not apply to fighter count unless explicitly changed later.

### US-036 View league quota usage as a platform admin

As a platform admin, I want to see how much of a league's quota has been used when viewing that league so that I can monitor whether clubs are close to their limits.

Acceptance criteria:

- The league admin view for a selected league shows used and remaining player quota.
- The league admin view for a selected league shows used and remaining team quota.
- The platform admin can understand quota health without manually checking players and teams one by one.

### US-037 Use league-first admin hierarchy for teams

As a platform admin, I want team management to be reachable through league management rather than from a top-level `/admin/teams` first so that the admin hierarchy is easier to understand.

Acceptance criteria:

- League-specific team management is clearly reachable from the selected league workspace.
- The platform admin can still reach team data when needed, but the primary hierarchy is league-first.
- Navigation supports a clearer mental model of `platform -> league -> teams`.
- The platform-admin dashboard itself does not need a primary top-level teams link when team operations belong inside league workspaces.

### US-038 Use league-first admin hierarchy for fighters

As a platform admin, I want fighter management to be reachable through league management rather than from a top-level `/admin/fighters` first so that the admin hierarchy is easier to understand.

Acceptance criteria:

- League-specific fighter management is clearly reachable from the selected league workspace.
- The platform admin can still reach fighter data when needed, but the primary hierarchy is league-first.
- Navigation supports a clearer mental model of `platform -> league -> fighters`.
- The platform-admin dashboard itself does not need a primary top-level fighters link when fighter operations belong inside league workspaces.

### US-039 Use league-first admin hierarchy for events

As a platform admin, I want event management to sit primarily with league admins inside their own league area so that platform-level navigation stays focused on oversight rather than day-to-day event entry.

Acceptance criteria:

- Event management is clearly owned by the league-admin area for each league.
- The platform admin can still inspect league event data when necessary.
- Scheduled events sourced from the shared Buhurt calendar flow into league event workflows rather than becoming a separate platform-admin event-maintenance burden.
- Navigation supports a clearer mental model of `platform oversight -> league operations -> events`.
- Platform-admin notification and dashboard space stays focused on platform oversight rather than league event-update traffic.

### US-040 Join multiple leagues

As a player, I want to join multiple leagues so that I can participate in more than one club competition from one account.

Acceptance criteria:

- A player can belong to more than one league at the same time.
- Each league membership remains clearly separated in permissions, teams, and standings.
- The player can tell which league context they are currently using.

### US-041 Switch league context from the header

As a player, I want to switch between leagues I have joined from a header dropdown so that I can move between club competitions without logging out.

Acceptance criteria:

- A logged-in player with multiple league memberships can switch active league context from the shared header.
- The page refreshes into the selected league's fighters, teams, and standings.
- Switching league context does not mix data or permissions between leagues.
 
TODO migrated:

- The modular user story documents have now been created in `docs/user-stories/`.
- The old TODO ideas have been expanded into new user stories `US-044` through `US-059`.
- The canonical entry point for the split story set is `docs/user-stories/README.md`.
- The backlog split is still a separate follow-up task.
