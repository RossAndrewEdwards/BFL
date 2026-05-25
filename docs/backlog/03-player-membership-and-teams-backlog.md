# 03 Player Membership and Teams Backlog

## Scope

This document covers player onboarding, memberships, league switching, team safety, join codes, and player-facing fantasy management.

## Items

### BL-011 Scope player memberships and update onboarding

Priority: `P1`
Related stories: `US-013`, `US-017`, `US-031`, `US-040`, `US-041`
Status: `Implemented`

Scope:

- Move from single-league assignment toward membership-based onboarding.
- Keep player creation platform-admin only.
- Keep league-admin player participation and management tied to memberships.

### BL-012 Scope teams to one league and enforce league-safe roster building

Priority: `P1`
Related stories: `US-014`, `US-018`, `US-019`, `US-030`
Status: `Implemented`

Scope:

- Keep team records tied to one league.
- Enforce league-safe fighter selection and roster validation.

### BL-021 Multi-league membership and context switching

Priority: `P2`
Related stories: `US-040`, `US-041`
Status: `Implemented`

Scope:

- Support users belonging to more than one league.
- Let users choose and switch their active league context.
- Make permissions membership-aware rather than only user-row-aware.

### BL-024 Join-code and participation flows

Priority: `P2`
Related stories: `US-013`, `US-017`, `US-033`, `US-034`, `US-035`, `US-040`
Status: `Implemented`

Scope:

- Support reusable join codes per league.
- Let league admins share join codes instead of creating player accounts directly.
- Support league-admin participation as players under standard rules.

### BL-041 Move to a one-team-per-player model

Priority: `P3`
Related stories: `US-064`
Status: `Implemented`

Scope:

- Remove the old multi-team-per-player and manager-slot assumptions.
- Express team ownership directly as one player mapped to one team within a league.
- Update quotas, joins, and admin flows to match the simpler model.

Definition of done:

- Players can own only one team per league.
- Manager-slot concepts are removed from normal workflow and messaging.
- Team ownership and validation reflect the simpler one-to-one model.

### BL-042 Simplify the My Teams page

Priority: `P3`
Related stories: `US-065`
Status: `Implemented`

Scope:

- Remove search and filter controls from `My Teams` if the page is already scoped tightly enough that they add little value.
- Keep the page focused on direct access to the player's current team data.

Definition of done:

- `My Teams` no longer shows low-value search/filter chrome.
- Core team-management and performance content remains easy to reach.

### BL-053 Redesign the fighter profile around richer identity and history

Priority: `P3`
Related stories: `US-076`, `US-077`
Status: `Planned`

Scope:

- Redesign fighter profiles to emphasise card-style identity, overall points, richer descriptor fields, and clear separation between current-season fantasy signals and lifetime history.
- Add fighter event history views so players can inspect how that fighter performed across scored events.

Definition of done:

- Fighter profiles feel richer and more useful than a bare stat page.
- Lifetime history and current-season fantasy scoring are clearly separated.
- Players can inspect event history for the fighter without reading admin tables.

### BL-054 Add player request and personal notification flows

Priority: `P3`
Related stories: `US-078`, `US-079`
Status: `Planned`

Scope:

- Let players submit fighter edit and new-fighter requests from player-facing flows.
- Provide a personal notifications page showing pending, accepted, and denied outcomes for that player's own requests.

Definition of done:

- Players can submit fighter-related requests without direct edit access.
- Players can view request outcomes in a private personal-notification area.

## Notes

- The membership and join-code foundation is already in place.
- The main remaining work here is richer player-facing fighter context, request flows, and continued simplification of player-facing controls.
