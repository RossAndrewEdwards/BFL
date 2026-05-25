# 01 Platform and Governance

## Epic 1: Platform and League Management

### US-001 Create a league

As a platform admin, I want to create multiple leagues so that different clubs can host their own fantasy leagues on the same platform.

Acceptance criteria:

- A platform admin can create a new league with a name, club name, status, optional descriptive fields, and an optional league logo.
- A new league is provisioned with its own empty league data or a starter template.
- A league can be marked as `active`, `inactive`, `archived`, or `pending setup`.
- A platform admin can assign one or more league admins as part of the same league management workflow.

### US-002 Edit league settings

As a platform admin, I want to update league settings so that each club can be configured without developer involvement.

Acceptance criteria:

- A platform admin can edit league name, description, logo, and contact details.
- A platform admin can enable or disable selected league features.
- Changes apply only to the selected league unless they are explicitly platform-wide.
- When editing a league, a platform admin can reach the league's current players, teams, and league admins from the same league workspace without needing a separate disconnected admin section.
- The main settings form does not need to duplicate full player or team tables when those are already available through league operations links.
- A league logo can be uploaded or assigned so it appears in the shared header for logged-in users of that league.

### US-003 Assign a league admin

As a platform admin, I want to assign one or more league admins to a league so that each club can manage its own competition.

Acceptance criteria:

- A platform admin can promote an existing user to league admin for a specific league.
- A newly created user appears in the available list for later promotion to league admin.
- A league admin can only access leagues they have been assigned to.
- A platform admin can revoke or replace league admin access at any time.
- League-admin assignment is managed from the main league management area rather than in a completely separate admin section.

### US-004 Set league quotas

As a platform admin, I want to give a league a quota of teams and members so that league admins can manage their own club within agreed limits.

Acceptance criteria:

- A platform admin can set maximum player count for a league.
- In the one-team-per-player model, team capacity can follow player capacity rather than requiring a separate team-quota input in normal league setup.
- The platform warns the platform admin when a league is approaching or has reached its quota.
- A league admin can view their remaining quota but cannot increase it themselves.

### US-005 Monitor league health

As a platform admin, I want to see how all leagues are doing so that I can monitor adoption, engagement, and operational issues.

Acceptance criteria:

- A platform admin dashboard shows summary metrics for every league.
- Metrics include at least active players, teams created, fighters listed, recent activity, and quota usage.
- A platform admin can quickly identify inactive, full, misconfigured, or stale leagues.

### US-006 Suspend or archive a league

As a platform admin, I want to suspend or archive a league so that I can manage clubs that stop participating without deleting history.

Acceptance criteria:

- A suspended league becomes read-only or inaccessible based on platform rules.
- An archived league is hidden from normal discovery but retains historical data.
- Historical standings, fighters, and teams remain available to the platform admin.

## Epic 2: League Isolation and Rules Governance

### US-007 Keep league data isolated

As a platform admin, I want league data to stay isolated so that clubs cannot accidentally see or edit each other's information.

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

As a platform admin, I want to manage scoring and roster rules centrally so that all leagues follow the same fantasy framework.

Acceptance criteria:

- A platform admin can manage platform-wide scoring settings, roster size rules, budget rules, and trait-formula definitions.
- League admins cannot override site-wide rules.
- Rule changes apply consistently across all active leagues.
- Rule settings include platform-wide values such as training and support attendance values when those are part of the scoring model.

### US-082 Keep rules settings and season settings clearly separated

As a platform admin, I want rules settings and season settings to have clear responsibilities so that configuration stays easy to understand and hard to misuse.

Acceptance criteria:

- Rule-related controls such as scoring values, roster logic, and trait formulas live in the rules settings area.
- Season-related controls such as season lifecycle actions, rollover, and season-end processes live in the season settings area.
- Platform-admin pages do not mix rule ownership and season ownership in a confusing way.

## Epic 5: Reporting, Audit, and Safety

### US-022 Audit important changes

As a platform admin, I want an audit trail for league changes so that I can investigate mistakes and maintain trust across clubs.

Acceptance criteria:

- Important admin actions are logged, including who changed what and when.
- Audit logs cover league settings, quota changes, fighter edits, event edits, player changes, team overrides, and formula changes.
- A platform admin can filter audit history by league.
- Platform-admin notifications focus on platform-level admin changes rather than league event-update traffic.

### US-023 Report platform usage

As a platform admin, I want platform-level reporting so that I can understand growth and decide where to invest next.

Acceptance criteria:

- Reports can summarize leagues, players, teams, and activity over time.
- A platform admin can compare league usage and growth trends.
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
- Public routes, platform-admin routes, league-admin routes, and player routes can be reasoned about independently.
- The refactor does not change existing user-facing behaviour unless explicitly planned.
- Automated tests still pass after the refactor.

### US-069 Keep the platform dashboard focused on platform oversight

As a platform admin, I want the main dashboard to show only the most useful platform-level information so that it stays focused and quick to scan.

Acceptance criteria:

- The main platform dashboard can prioritise direct links to the most-used platform-admin areas such as leagues, players, rules, season settings, and audit.
- Low-value sections such as season snapshots, operational signals, recent platform activity, or media shortcuts can be removed when they do not help the day-to-day platform-admin workflow.
- Platform-admin notifications remain focused on platform-level changes rather than league event traffic.

### US-070 Simplify league quotas and league edit views for the one-team model

As a platform admin, I want league setup to reflect the one-player-to-one-team model so that league configuration stays simple.

Acceptance criteria:

- League configuration can focus on maximum players without needing a separate maximum-teams setting when team count is implied by player count.
- Platform-admin league editing does not need to duplicate league members or teams inside the main settings form when those are already reachable through league operations links.
- Platform-admin page titles and labels stay concise and accurate to the simplified model.
