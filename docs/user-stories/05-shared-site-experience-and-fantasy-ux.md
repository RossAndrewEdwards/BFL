# 05 Shared Site Experience and Fantasy UX

## Epic 8: Shared Site Navigation and Public Structure

### US-044 Add a shared footer

As a user, I want the site to have a consistent footer so that important platform pages remain easy to find without overcrowding the main header.

Acceptance criteria:

- The shared site layout includes a footer on public and logged-in views.
- The footer includes links for `Home`, `Rules`, `Contact Us`, and `Hall of Fame`.
- Primary navigation in the header can be simplified once footer links exist.
- Footer links do not expose private league data to logged-out users.

### US-045 Create a Contact Us page

As a visitor, I want a `Contact Us` page so that I know how to reach the platform owner or organisers when I need help.

Acceptance criteria:

- The site has a dedicated `Contact Us` page linked from the footer.
- The page contains platform-level contact details or a clear support route.
- The page does not expose private league or player data.
- The page is available to both logged-out and logged-in users.

### US-046 Replace separate fighters and teams pages with a league leaderboard

As a logged-in user, I want a single league leaderboard page instead of separate fighters and teams pages so that I can quickly understand league performance in one place.

Acceptance criteria:

- The old separate fighters and teams browsing flow is replaced by a league-specific leaderboard experience.
- The leaderboard shows one fighter table and one team table for the active league.
- Each table focuses on points-first ranking rather than large profile-heavy layouts.
- Logged-out users cannot access the leaderboard.

### US-047 Open fighter and team cards from leaderboard rows

As a logged-in user, I want to click a fighter or team name and open a compact in-page card so that I can inspect more detail without leaving the leaderboard.

Acceptance criteria:

- Clicking a fighter name opens an in-page popup or overlay card.
- Clicking a team name opens an in-page popup or overlay card.
- The interaction does not navigate away from the leaderboard page by default.
- The card uses the same shared collectible-card template used elsewhere on the site rather than a one-off modal layout.
- The card shows concise league-relevant information rather than a full separate management page.

### US-048 Highlight the top three leaderboard entries

As a logged-in user, I want the top three fighters and top three teams to stand out visually so that the strongest performers are immediately clear.

Acceptance criteria:

- The leaderboard visually highlights first, second, and third place in the fighters table.
- The leaderboard visually highlights first, second, and third place in the teams table.
- The highlight treatment stays readable on desktop and mobile.

## Epic 9: Team Creation, Trait Display, and Team Feedback

### US-049 Create an interactive team-building experience

As a player, I want team creation to feel like collecting fighters into my roster so that building a team is more visual and engaging.

Acceptance criteria:

- Team creation uses selectable fighter cards rather than only plain form rows.
- The interface makes it clear which fighters are already selected.
- The player can review the current roster while still browsing available fighters.
- The interaction supports a more tactile, collected-fighter feel.

### US-050 Use a two-step team creation wizard

As a player, I want team creation to happen in clear steps so that naming my team and choosing fighters feel organised instead of crowded.

Acceptance criteria:

- Team creation starts with a team-details step for items such as team name and any other metadata.
- The next step is fighter selection.
- The player can move back and forward without losing progress unexpectedly.
- Validation is shown at the right step rather than all at once.

### US-051 Standardise fighter and team cards around six traits

As a player, I want fighter and team cards to focus on the six core fantasy traits so that the scoring model is easier to understand.

Acceptance criteria:

- Fighter-facing cards use these six traits only: `Glory`, `Discipline`, `Lethality`, `Resilience`, `Crowd Favourite`, and `Synergy`.
- The primary team-facing stat presentation can use those same six traits in detailed team views without forcing every compact team card to show all six totals.
- Extra low-value profile fields do not crowd the main player-facing cards.

### US-052 Show six-trait team totals on My Team

As a player, I want `My Team` to show my team's combined six-trait totals so that I can understand the strengths of my squad at a glance.

Acceptance criteria:

- `My Team` shows combined totals for `Glory`, `Discipline`, `Lethality`, `Resilience`, `Crowd Favourite`, and `Synergy`.
- Totals update when the roster changes.
- The presentation is easy to compare visually across the six traits.

### US-053 Show event-by-event team point gains

As a player, I want to see how many points my team gained from each event so that I can understand where my ranking changes came from.

Acceptance criteria:

- `My Team` shows points gained from each scored event.
- Event updates can show which fighters contributed those points.
- The view helps a player understand recent scoring changes without reading raw admin data.

### US-054 Keep team scoring cumulative across events

As a player, I want event scoring to add to my team's running total rather than overwrite it so that season performance reflects every event played.

Acceptance criteria:

- When a new event is scored, the team's total points increase cumulatively.
- Editing one event recalculates the cumulative total correctly.
- The system does not replace the full season score with only the latest event score.

### US-055 Remove the build summary from My Team

As a player, I want `My Team` to focus on useful league performance information so that the page feels cleaner and more relevant.

Acceptance criteria:

- The old build summary is removed from `My Team`.
- The page prioritises current roster, team trait totals, and event-based scoring updates instead.
- Removing the build summary does not remove essential validation or rules feedback from the team-creation flow where it is still needed.

## Epic 10: Calendar, Rules Clarity, and Formula Administration

### US-056 Show the full-year Buhurt calendar in the event workspace

As a league admin, I want the event workspace to show all Buhurt events for the year, including past ones, so that I can score historical fixtures as well as upcoming ones.

Acceptance criteria:

- The event workspace shows past, current, and upcoming calendar events for the selected year.
- League admins can start a scoring session from a past event as well as a future or current event.
- Historical calendar visibility does not require the event to be manually recreated first.

### US-057 Explain the six-trait formulas on the rules page

As a player, I want the rules page to explain how the six traits are calculated so that the scoring system feels transparent and understandable.

Acceptance criteria:

- The rules page explains how `Glory`, `Discipline`, `Lethality`, `Resilience`, `Crowd Favourite`, and `Synergy` are derived.
- Explanations are written in player-friendly language.
- The rules page stays platform-wide and consistent across leagues.

### US-058 Let the platform admin manage six-trait formulas

As a platform admin, I want to manage the six-trait formulas centrally so that I can tune the fantasy model without code changes.

Acceptance criteria:

- A platform admin can update the formula settings that drive the six core traits.
- Formula changes are platform-wide, not league-specific.
- Formula changes are auditable.
- Dependent fighter, team, and leaderboard values can be recalculated safely after a formula update.

### US-059 Make the logout action visually distinct

As a logged-in user, I want the logout action to stand out clearly so that I can leave the app quickly without confusing it with ordinary navigation links.

Acceptance criteria:

- The logout control is visually distinct from normal header navigation.
- The styling remains clear and accessible on desktop and mobile.
- The control still routes the user back to the homepage after logout.

### US-060 Remove duplicate guest calls to action on the homepage

As a logged-out visitor, I want the homepage calls to action to be clear and non-repetitive so that the page does not repeat the same `Rules` and `Login` actions in multiple places.

Acceptance criteria:

- The guest homepage does not repeat the same login and rules links in multiple adjacent sections when one clear set of actions is already present.
- The members-only explanation stays informative without duplicating controls that are already visible higher on the page.
- The guest hero actions remain visually balanced and not overly stretched.

### US-061 Make the rules page layout consistent

As a visitor, I want the rules page to use a consistent layout so that the scoring system is easier to read and does not feel uneven from section to section.

Acceptance criteria:

- Rule sections use a consistent visual structure rather than mixing awkward side-by-side blocks with full-width tables in a jarring way.
- The page remains readable on desktop and mobile.
- Platform-wide rules and formula explanations still stay clear after the layout is simplified.

### US-062 Use one shared team card template everywhere

As a user, I want team cards to always look like the same trading-card style component so that the experience feels consistent across the site.

Acceptance criteria:

- Team cards use one shared visual template across homepage, leaderboard, team pages, event views, and future card-based surfaces.
- When the shared team card template is updated, all team-card displays update with it.
- The team card style should feel like a trading card rather than a collection of unrelated layouts.
- The visual design should feel recognisably close to real-world collectible sports cards such as baseball or match-attax style cards.
- Team cards use stronger card-like framing such as a featured hero image area, headline name treatment, rank or rarity badge treatment, and a clear stat panel layout.
- Compact team cards do not need to show six-trait totals when those totals would make the card feel cluttered.
- Team cards prioritise recognisable identity details such as team name, owner, featured image, and a small number of high-value fantasy cues.
- Overlay or popup versions of team cards should still feel like the same collectible card, not like a plain modal with team data dropped into it.

### US-063 Use one shared fighter card template everywhere

As a user, I want fighter cards to always look like the same trading-card style component so that the experience feels consistent across the site.

Acceptance criteria:

- Fighter cards use one shared visual template across homepage, leaderboard, fighter pages, event views, and future card-based surfaces.
- When the shared fighter card template is updated, all fighter-card displays update with it.
- The fighter card style should feel like a trading card rather than a collection of unrelated layouts.
- The visual design should feel recognisably close to real-world collectible sports cards such as baseball or match-attax style cards.
- Fighter cards use one consistent baseline card size and aspect ratio across the site rather than being stretched or resized differently on different pages.
- The baseline fighter card size should feel close to a real trading card, with surrounding layouts adapting to the card rather than shrinking the card to fit awkward page space.
- Fighter cards use stronger card-like framing such as a featured portrait area, headline name treatment, rank or rarity badge treatment, and a clear stat panel layout.
- Fighter cards can use rich descriptor fields such as nickname, fighting style, role or weapon, known for, and joined year when those details help the card feel personal and collectible.
- Fighter cards show a fallback image when a dedicated fighter image is missing.
- Overlay or popup versions of fighter cards should still feel like the same collectible card, not like a plain modal with fighter data dropped into it.

### US-071 Use a true collectible-card visual language

As a user, I want fighter and team cards to look like real collectible sports cards so that opening a card feels exciting and premium rather than like opening a plain information panel.

Acceptance criteria:

- Card designs use a recognisable collectible-card visual language inspired by sports trading cards such as baseball cards, sticker albums, or match-attax style designs.
- Cards have a clear visual hierarchy with a hero image, bold name area, prominent ranking or rarity treatment, and structured stats.
- The design should feel intentionally framed and decorative rather than like a generic website panel with rounded corners.
- Fighter cards and team cards should feel like part of the same collectible system while still being visually distinct from each other.
- This visual language is applied consistently on homepage cards, leaderboard popups, and any future card-based surfaces.
- Fighter cards should read as true trading-card objects with a stable, recognisable footprint that stays visually consistent across different pages and contexts.

### US-080 Rank and search the leaderboard by the most useful fantasy signals

As a player, I want the leaderboard to rank and filter by the most useful fantasy information so that I can find people quickly and trust the ordering.

Acceptance criteria:

- Fighter and team leaderboard ordering is based on points rather than trait totals.
- The leaderboard supports searching by fighter name.
- The leaderboard supports searching by team name.
- Search and ranking stay scoped to the active league.

### US-081 Let users choose dark or light mode

As a user, I want to choose dark mode or light mode so that I can use the app in the visual style that feels best for me.

Acceptance criteria:

- Logged-in users can choose between dark mode and light mode.
- The chosen theme persists when the user moves between pages.
- Theme selection applies to shared public, player, league-admin, and platform-admin surfaces.
- The selected theme keeps text, cards, tables, and overlays readable and accessible.
