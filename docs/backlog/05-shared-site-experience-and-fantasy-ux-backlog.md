# 05 Shared Site Experience and Fantasy UX Backlog

## Scope

This document covers the newer fantasy UX work: public-site structure, leaderboard redesign, popup cards, six-trait presentation, and formula transparency.

## Items

### BL-029 Replace separate fighters and teams browsing with a league leaderboard

Priority: `P2`
Related stories: `US-046`
Status: `Implemented`

Scope:

- Replace the old separate fighters and teams browsing pages with one league leaderboard experience.
- Show one fighter table and one team table for the active league.
- Focus on points-first ranking rather than profile-heavy page layouts.

Definition of done:

- Logged-in users can access one leaderboard page for their active league.
- The leaderboard contains separate fighters and teams tables.
- Logged-out users cannot access the leaderboard or see points data.

### BL-030 Add popup cards and top-three leaderboard highlighting

Priority: `P2`
Related stories: `US-047`, `US-048`
Status: `Implemented`

Scope:

- Let users click fighter or team names in the leaderboard to open an in-page card.
- Add a visual highlight treatment for first, second, and third place in fighters and teams.

Definition of done:

- Clicking a leaderboard name opens an in-page popup card.
- The interaction does not navigate away from the leaderboard by default.
- Top-three entries are visually highlighted in both tables.

### BL-031 Build an interactive two-step team creation flow

Priority: `P2`
Related stories: `US-049`, `US-050`
Status: `Implemented`

Scope:

- Replace plain team-creation forms with a two-step wizard.
- Use a details step first, then fighter selection.
- Make fighter selection feel more visual and collected-card driven.

Definition of done:

- Team creation has a separate team-details step and fighter-selection step.
- Players can move back and forward without losing progress unexpectedly.
- Fighter selection shows clear selected-state feedback and keeps the roster visible while browsing.

### BL-032 Standardise player-facing stat cards around six traits

Priority: `P2`
Related stories: `US-051`, `US-052`
Status: `Implemented`

Scope:

- Standardise fighter and team cards around `Glory`, `Discipline`, `Lethality`, `Resilience`, `Crowd Favourite`, and `Synergy`.
- Show team-level combined totals for those six traits on `My Team`.

Definition of done:

- Fighter cards use the six-trait model as their main player-facing presentation.
- Team cards and `My Team` use the same six traits consistently.
- Team totals update from the current roster.

### BL-033 Show event-by-event team gains and cumulative season scoring

Priority: `P2`
Related stories: `US-053`, `US-054`, `US-055`
Status: `Implemented`

Scope:

- Show players how many points their team gained from each event.
- Keep team scoring cumulative across the season.
- Remove the old build summary from `My Team` and replace it with more relevant scoring feedback.

Definition of done:

- `My Team` shows per-event point gains.
- Team totals remain cumulative across all scored events.
- Editing one event safely recalculates cumulative totals.
- The old build summary is removed from the player-facing page.

### BL-035 Explain and manage six-trait formulas

Priority: `P2`
Related stories: `US-057`, `US-058`
Status: `Implemented`

Scope:

- Explain the six-trait formulas clearly on the rules page.
- Let platform admins manage those formulas centrally.
- Keep formula changes audited and safe to recalculate.

Definition of done:

- The rules page explains the six traits in player-friendly language.
- Platform admins can manage the formula definitions without code changes.
- Formula changes are auditable and trigger safe recalculation behaviour.

### BL-037 Remove duplicate guest homepage calls to action

Priority: `P3`
Related stories: `US-060`
Status: `Implemented`

Scope:

- Remove repeated `Login` and `Rules` links from lower guest-homepage sections when those actions are already clearly available higher on the page.
- Tighten guest hero-action sizing so buttons do not appear overly stretched.

Definition of done:

- The guest homepage has one clear login/rules CTA cluster without unnecessary duplication.
- Guest-facing action buttons feel visually balanced.

### BL-038 Make the rules page layout consistent

Priority: `P3`
Related stories: `US-061`
Status: `Implemented`

Scope:

- Refactor the rules page into a more consistent layout rhythm.
- Avoid awkward mixtures of side-by-side rule blocks and full-width tables unless the structure clearly calls for it.

Definition of done:

- The rules page uses a more coherent visual structure across all sections.
- The page remains readable on both desktop and mobile.

### BL-039 Standardise the shared team card template

Priority: `P3`
Related stories: `US-062`
Status: `Partial`

Scope:

- Use one shared team-card template across homepage, leaderboard, event surfaces, and team-related pages.
- Make shared team-card updates propagate to all team-card contexts.

Definition of done:

- Team cards use one shared trading-card style component wherever team cards appear.
- Updating the template updates all team-card surfaces consistently.

### BL-040 Standardise the shared fighter card template

Priority: `P3`
Related stories: `US-063`
Status: `Partial`

Scope:

- Use one shared fighter-card template across homepage, leaderboard, event surfaces, and fighter-related pages.
- Make shared fighter-card updates propagate to all fighter-card contexts.

Definition of done:

- Fighter cards use one shared trading-card style component wherever fighter cards appear.
- Updating the template updates all fighter-card surfaces consistently.

### BL-055 Improve leaderboard ranking and search

Priority: `P3`
Related stories: `US-080`
Status: `Planned`

Scope:

- Ensure leaderboard ordering is driven by points-first ranking.
- Add useful search for fighter and team names.
- Keep the interaction scoped to the active league.

Definition of done:

- Users can find fighters and teams quickly from the leaderboard.
- Ranking behaviour matches the most useful fantasy signal, not incidental trait totals.

### BL-056 Add user-selectable light and dark mode

Priority: `P3`
Related stories: `US-081`
Status: `Planned`

Scope:

- Let users choose between dark and light mode.
- Persist the chosen theme across pages and sessions where practical.

Definition of done:

- Users can switch theme intentionally.
- The chosen theme applies consistently across the app shell and major card/table surfaces.

### BL-057 Deepen the collectible-card design system

Priority: `P3`
Related stories: `US-047`, `US-062`, `US-063`, `US-071`
Status: `Planned`

Scope:

- Push fighter and team cards closer to a true collectible sports-card feel across homepage, leaderboard popups, and future card-led surfaces.
- Improve framing, hero imagery, rank or rarity treatment, descriptor layout, and consistency between popup and embedded versions.

Definition of done:

- Fighter and team cards feel like part of one premium collectible-card system.
- Popup cards no longer feel like plain modals with card data dropped into them.

## Notes

- The core fantasy UX phase is now largely implemented.
- The main remaining work here is consistency, search, theme selection, and deeper collectible-card polish.
