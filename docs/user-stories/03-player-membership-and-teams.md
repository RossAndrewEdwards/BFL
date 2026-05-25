# 03 Player Membership and Teams

## Epic 4: Player Experience

### US-016 Public access stays restricted

As a platform admin, I want people who are not logged in to have a limited public view so that league and player data is protected.

Acceptance criteria:

- Logged-out visitors can access only the homepage, rules page, and future platform contact content.
- Logged-out visitors cannot access fighters, teams, standings, player pages, or admin pages.
- Logged-out visitors do not see top fighters, top teams, or other league/player performance data on the homepage.
- The shared public header uses platform branding such as `Buhurt Fantasy League` rather than a specific league name.

### US-017 Join a league

As a player, I want to join a specific league so that I can participate in my club's fantasy competition.

Acceptance criteria:

- A player can join a league through a join code, admin assignment, or future equivalent platform flow.
- A player can clearly see which league they are joining.
- A player cannot join a league that is closed, full, or inactive unless permitted by an admin.
- Joining a new league adds membership to the player's account rather than replacing existing valid league memberships.

### US-018 Create a team within quota

As a player, I want to create my own team as long as I have been given enough quota so that I can participate without admin intervention.

Acceptance criteria:

- A player can create a team only if the league has available team quota and the player has permission to create one.
- The platform clearly explains when team creation is blocked by quota, status, or site-wide rules.
- Team creation validates site-wide rules such as budget, roster size, and duplicate restrictions against the selected league's fighter pool.

### US-019 Manage my own team

As a player, I want to manage my own team within site-wide rules so that I can keep my fantasy picks competitive.

Acceptance criteria:

- A player can add, remove, and update fighters on their own team when the league allows it.
- Team changes are validated against the selected league's fighter pool and site-wide rules.
- A player cannot edit another player's team unless granted an admin role.

### US-020 View league standings

As a player, I want to view standings and rankings for my league so that I can track my performance against other members.

Acceptance criteria:

- A player can view league tables, fighter rankings, and event outcomes for their own league.
- Shared views show only the current league context.
- Standings do not mix data from other leagues.
- Players can review event-result groups and grouped event outcomes for their own league when those have been scored.

### US-021 View league-specific content on a shared site

As a player, I want to see my league's own fighters, events, and standings on the shared site experience so that the app stays relevant to my club without needing a separate homepage per league.

Acceptance criteria:

- The shared homepage remains the same across the platform.
- Logged-in users can see which league they are currently in from the shared header.
- Logged-in users can see that league's logo in the shared header when one has been configured.
- Featured league content updates based on the logged-in user's active league.
- Fighters, events, and standings shown to players belong only to that league.
- Navigation makes it clear which league the player is currently in.

### US-033 Manage a league join code

As a league admin, I want to have a reusable join code for my league so that I can give it to players and they can enter it in the app to join the league.

Acceptance criteria:

- Each league has a reusable join code that is tied to that league.
- A league admin can view the current join code for their league.
- A league admin can regenerate the join code when needed.
- A player can enter the join code in the app to join that league.
- The platform validates that the league is active, the code is valid, quota is available, and the player is not already a member before joining them to the league.

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
- The page refreshes into the selected league's fighters, teams, standings, and team-management views.
- Switching league context does not mix data or permissions between leagues.

### US-064 Use one team per player

As a platform owner, I want each player to have exactly one team per league so that the fantasy model is simpler and the old manager-slot concept can be removed.

Acceptance criteria:

- A player can own at most one team in a given league.
- The platform no longer needs a separate manager-slot or multi-team-per-player model for normal league play.
- Team ownership is expressed directly as one player mapped to one team inside the league context.
- Any quota, validation, or admin messaging reflects the one-player-to-one-team rule clearly.

### US-065 Keep My Teams focused and lightweight

As a player, I want `My Teams` to stay simple so that I can get to my team quickly without extra search or filter controls.

Acceptance criteria:

- `My Teams` does not include a search-and-filter section when the page is already scoped to the current player's teams.
- The page prioritises direct access to the player's current league team card and performance details.
- Removing search and filter controls does not hide important team-management actions.

### US-076 View a richer fighter profile

As a player, I want fighter profiles to show meaningful identity and history information so that I can understand the fighter beyond a bare stat block.

Acceptance criteria:

- A fighter profile can show card-style presentation, overall points, descriptive profile fields, and league-relevant current-season information.
- The fighter's collectible-style card can be shown as part of the profile experience rather than living only in popups or summary views.
- The profile does not need a separate performance snapshot when that section duplicates clearer information elsewhere on the page.
- Low-value or confusing summary metrics such as a duplicated fame score or unnecessary K/D emphasis can be removed when better fantasy signals already exist.

### US-077 Separate lifetime fighter history from season fantasy scoring

As a player, I want to see a fighter's lifetime history without confusing it with the current season fantasy model so that I can understand both legacy performance and current scoring.

Acceptance criteria:

- A fighter profile can show lifetime fighter statistics as historical information.
- A fighter profile can show event-by-event history for that fighter when they have participated in scored events.
- Lifetime statistics are visually separated from the current season's fantasy points and trait calculations.
- Historical data does not overwrite or distort the current season scoring model.

### US-078 Request a fighter edit or a new fighter

As a player, I want to request fighter edits or propose a new fighter so that league data can improve even when I do not have direct edit permission.

Acceptance criteria:

- A player can submit a request to edit an existing fighter in their active league.
- A player can submit a request to create a new fighter in their active league.
- The request captures enough detail for a league admin to review it.
- Submitting a request does not directly change live fighter data until a league admin approves it.

### US-079 Receive personal notifications about my requests

As a player, I want a personal notifications view for my submitted requests so that I can see whether a league admin accepted or denied them.

Acceptance criteria:

- A player can view notifications related only to their own submitted requests.
- The notification view shows whether a fighter edit or new-fighter request was accepted, denied, or is still pending.
- Notifications do not expose another player's private request history.
