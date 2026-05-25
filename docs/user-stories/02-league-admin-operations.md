# 02 League Admin Operations

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
- Quick support or other event-adjacent adjustments can be made from the event-scoring workflow when that is the natural place to record them.

### US-012 Add and manage event data

As a league admin, I want to add event data for my league so that fantasy scoring reflects real competition outcomes.

Acceptance criteria:

- A league admin can enter event results for their league without first being forced to create a scheduled event.
- Scheduled events may still exist as an optional organisational tool, but they are not required for normal result entry.
- A league admin can enter event results tied to fighters in their league.
- A league admin can create one event-result session for a real fixture and record results for multiple fighters inside that session.
- Event entry supports draft-style data capture so a league admin can update the session while reviewing a live stream or replay before considering it complete.
- Event scoring updates only the affected league tables and rankings.

### US-013 Manage league players

As a league admin, I want to manage all players in my league so that I can help users join, participate, and remain within quota.

Acceptance criteria:

- A league admin can view players already in their league.
- A league admin can invite people to join the league by sharing the league join code.
- A league admin can see how many player slots are used and remaining.
- A league admin can enable or disable whether an existing player in their league can own a team under the one-team-per-player model.
- A league admin can promote a player to league admin from the dedicated players flow when they have platform permission to do so.
- A league admin cannot create brand new player accounts directly.
- A league admin cannot exceed the platform-admin-defined member quota.

### US-014 Manage league teams

As a league admin, I want to manage all teams in my league so that I can correct issues and support players.

Acceptance criteria:

- A league admin can view every team in their league.
- A league admin can edit, lock, unlock, or remove teams when required by league policy.
- A league admin cannot manage teams belonging to another league.

### US-015 Manage season lifecycle

As a platform admin, I want to manage the season lifecycle for the platform so that all leagues move through the season consistently.

Acceptance criteria:

- A platform admin can mark the season as `pre-season`, `active`, `completed`, or `archived`.
- A platform admin can trigger season rollover actions across the platform.
- Historical season data remains available for league and platform reporting.

### US-029 League admins own event result updates

As a league admin, I want to add event updates and fighter stat changes for my own league so that the platform admin does not need to manage day-to-day competition data on behalf of clubs.

Acceptance criteria:

- A league admin can create and update event results for their league.
- A league admin can use a league-owned scoring workspace to enter grouped fighter results while reviewing event footage.
- Event-related fighter stat changes are managed from league-admin event workflows.
- The platform admin can still oversee league health, but normal event scoring responsibility sits with the league admin.

### US-042 Use an interactive live event entry workflow

As a league admin, I want an interactive event-entry workflow so that I can watch a fight on YouTube, create groups within the event, and enter each fighter's results as I review the action.

Acceptance criteria:

- A league admin can create an event entry workspace for a selected event or a manually named event.
- Within that event workspace, a league admin can create groups such as matches, pools, teams, or fight segments based on how they want to review the event footage.
- A league admin can add fighters from their own league into those groups.
- A league admin can enter and update results for all fighters in a group in one batch scoring interaction rather than being forced to score one fighter at a time.
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

### US-066 Keep fighter admin compact and event-focused

As a league admin, I want fighter admin to focus on quick roster upkeep so that I can update training and support data without scrolling through unnecessary detail.

Acceptance criteria:

- The fighter admin page prioritises compact, high-frequency actions such as adding training progress.
- Fighter admin does not need to show low-value league-admin detail such as tier, cost, total points, or verbose season defaults when those fields are not part of the current workflow.
- Support adjustments can be made from the event-scoring workflow when that is the more natural place to record them.
- The page layout is intentionally compact so a league admin can work through many fighters quickly.

### US-072 Use a richer fighter profile model

As a league admin, I want fighter profiles to store richer background and physical details so that fighters feel more distinct and collectible across the app.

Acceptance criteria:

- Fighter profiles can store age, height, weight, nickname, fighting style, role or weapon of choice, known for, description, why they do Buhurt, and joined year.
- A league admin can create and maintain those fields for fighters in their own league.
- These richer fields can be reused in fighter cards and fighter profile views without needing duplicate data entry elsewhere.

### US-073 Review player-submitted fighter changes

As a league admin, I want to review fighter edit and new-fighter requests from players so that league data can improve without giving players direct edit access.

Acceptance criteria:

- A league admin can review requests from players to edit an existing fighter.
- A league admin can review requests from players to create a new fighter.
- A league admin can accept or deny each request.
- Accepting a request applies the approved change to the fighter data or creates the fighter in the current league.
- Request review actions are logged.

### US-074 Show a dedicated training attendance workspace

As a league admin, I want a dedicated training page with reusable groups so that I can update training attendance quickly without using the fighter list or event workspace for everything.

Acceptance criteria:

- The platform provides a dedicated training-attendance page for league admins.
- A league admin can create named training groups that persist across visits.
- A league admin can quickly mark attendance for fighters in those groups without a heavy submit flow.
- Training groups can be collapsed or minimised so the page stays manageable during regular use.
- Training attendance updates only affect the current league.

### US-075 Add medals and special awards outside the scoring workspace

As a league admin, I want to add medals or special awards directly to fighters outside the event workspace so that I can record ad hoc honours without forcing them through event scoring.

Acceptance criteria:

- A league admin can add medals or special awards to a fighter without opening the event-scoring workspace.
- Awards stay scoped to the fighter and league.
- Award changes are visible in the fighter's record and are logged.

### US-067 Use the scoring workspace as the primary event-entry flow

As a league admin, I want the scoring workspace to be the primary event-entry path so that I do not have to maintain two competing result-entry workflows.

Acceptance criteria:

- The event admin area treats the scoring workspace as the main way to record event outcomes.
- Legacy `Add Result` style entry can be removed or clearly de-emphasised if it is no longer needed.
- Event-scoring actions remain easy to find from the league-admin event page.
