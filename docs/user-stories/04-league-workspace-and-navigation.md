# 04 League Workspace and Navigation

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
- Player promotion and other detailed management actions happen inside the relevant dedicated page rather than as a separate dashboard section.

### US-028 Reach fighter management from My League

As a league admin, I want `My League` to include a clear way into fighter management so that I can maintain the league fighter pool without searching through general admin navigation.

Acceptance criteria:

- `My League` includes a dedicated fighters section or shortcut.
- The fighters area opened from `My League` is scoped only to the current league.
- The navigation makes it clear that fighter management belongs to the league-admin workflow rather than the platform-admin workflow.

### US-030 Reach team management from My League

As a league admin, I want to manage teams from a dedicated page within my league workspace so that team administration feels like part of one coherent league flow.

Acceptance criteria:

- `My League` includes a dedicated teams section or shortcut.
- The teams page is scoped only to the current league.
- Team actions remain unavailable for other leagues.

### US-031 Manage players and player participation within league quota

As a league admin, I want to manage players in my league, including whether a player can own a team, so that I can control participation as long as the league still has enough quota.

Acceptance criteria:

- A league admin can view and manage players assigned to their league.
- A league admin can enable or disable player participation under the one-team-per-player rules.
- If a player should become a league admin, that promotion happens from the dedicated player-management flow rather than from the `My League` dashboard itself.
- Player creation and player team management remain blocked when the league quota has been reached.
- The league admin cannot bypass platform-defined quota limits.

### US-032 See quota usage in My League

As a league admin, I want to see my league quota and how much of it has been used inside `My League` so that I can manage invitations, players, and teams confidently.

Acceptance criteria:

- `My League` shows player quota usage and remaining player capacity.
- `My League` shows team quota usage and remaining team capacity.
- Quota information is visible without needing to open a separate reporting page.

### US-036 View league quota usage as a platform admin

As a platform admin, I want to see how much of a league's quota has been used when viewing that league so that I can monitor whether clubs are close to their limits.

Acceptance criteria:

- The league workspace for a selected league shows used and remaining player quota.
- The league workspace for a selected league shows used and remaining team quota.
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

### US-068 Reduce repetitive page chrome

As a user, I want pages to use space efficiently so that repeated descriptive text does not push useful content too far down the screen.

Acceptance criteria:

- Pages do not need a descriptive subtitle under every page title when the purpose is already obvious from the heading and layout.
- Navigation and page framing should favour space for the main working area over repeated explanatory copy.
- Important guidance can still appear when it is genuinely needed for a complex workflow.
