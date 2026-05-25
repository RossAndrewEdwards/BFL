# 02 League Admin Operations Backlog

## Scope

This document covers league-admin tools for fighters, events, imports, scoring workflows, and calendar-backed event setup.

## Items

### BL-008 League quotas for players and teams

Priority: `P1`
Related stories: `US-004`, `US-013`, `US-018`, `US-024`, `US-031`, `US-032`, `US-035`
Status: `Implemented`

Scope:

- Enforce player and team quotas per league.
- Keep quota messaging aligned with the one-team-per-player model, where player participation and team ownership are tightly linked.
- Surface quota usage in league-admin and platform-admin views.

### BL-009 Scope fighters to the active league

Priority: `P1`
Related stories: `US-008`, `US-010`, `US-011`, `US-028`
Status: `Implemented`

Scope:

- Keep fighter management, rankings, imports, and public fighter views scoped to the active league.

### BL-010 Scope event management to the active league

Priority: `P1`
Related stories: `US-012`, `US-029`
Status: `Implemented`

Scope:

- Keep event management scoped to the active league.
- Allow manual event result entry without requiring a scheduled event first.

### BL-022 Bulk import and export per league

Priority: `P2`
Related stories: `US-010`, `US-012`
Status: `Implemented`

Scope:

- Provide league-safe fighter and event import/export tools.
- Keep imports and exports scoped to the selected target league.

### BL-025 Interactive live event scoring workspace

Priority: `P2`
Related stories: `US-012`, `US-029`, `US-042`
Status: `Implemented`

Scope:

- Replace the old event-entry flow with a scoring workspace suited to live or replay review.
- Support named groups inside one event session.
- Support iterative scoring, draft/completion state, and grouped fighter updates.

### BL-026 Sync scheduled events from the Buhurt calendar

Priority: `P2`
Related stories: `US-012`, `US-039`, `US-043`
Status: `Implemented`

Scope:

- Generate scheduled events from the shared Buhurt calendar.
- Attach metadata such as date, location, and source URL.
- Prevent obvious duplicates and keep manual fallback event entry available.

### BL-034 Extend the event workspace to show the full-year calendar

Priority: `P2`
Related stories: `US-056`
Status: `Implemented`

Scope:

- Expand the event workspace so it shows past, current, and upcoming Buhurt calendar events for the full selected year.
- Make historical event selection first-class, not only upcoming-event selection.

Definition of done:

- League admins can start a scoring session from a past calendar event.
- The workspace can browse the full calendar year without hiding already-finished fixtures.
- Historical event visibility works cleanly alongside manual event creation.

### BL-043 Simplify and compact fighter admin

Priority: `P3`
Related stories: `US-011`, `US-066`
Status: `Implemented`

Scope:

- Make the fighter admin page more compact for high-frequency league-admin use.
- Remove low-value display fields such as tier, cost, totals, and verbose season defaults from the main fighter admin workflow when they are not actively helping the task.
- Move support adjustments into the event-scoring workspace where appropriate.

Definition of done:

- League admins can work through fighter updates with less scrolling.
- The fighter admin page prioritises quick maintenance actions over reference-heavy detail.

### BL-044 Make the scoring workspace the primary event-entry flow

Priority: `P3`
Related stories: `US-067`
Status: `Implemented`

Scope:

- Remove or de-emphasise the old `Add Result` flow in favour of the scoring workspace.
- Keep event entry centred on the richer workspace experience.

Definition of done:

- League admins are naturally steered into the scoring workspace as the main event-entry path.
- Legacy direct result entry no longer competes with the workspace as a primary workflow.

### BL-049 Expand fighter records with richer profile fields

Priority: `P3`
Related stories: `US-072`
Status: `Planned`

Scope:

- Extend fighter records with richer descriptive and physical profile fields such as nickname, age, height, weight, fighting style, role or weapon, known for, joined year, and longer profile text.
- Make those fields editable by league admins in a practical fighter-management workflow.
- Ensure the richer fields can be reused by fighter cards and fighter profile pages.

Definition of done:

- League admins can store and update the richer fighter profile model.
- The new fields are available for use in player-facing fighter cards and profile views.

### BL-050 Add review flows for player-submitted fighter changes

Priority: `P3`
Related stories: `US-073`
Status: `Planned`

Scope:

- Provide a league-admin review queue for fighter edit requests and new-fighter requests submitted by players.
- Let league admins accept or deny requests with clear reasoning and audit logging.

Definition of done:

- League admins have a clear place to review pending fighter-related requests.
- Accepted requests update fighter data safely.
- Denied and accepted requests are recorded clearly.

### BL-051 Create a dedicated training attendance workspace

Priority: `P3`
Related stories: `US-074`
Status: `Planned`

Scope:

- Add a dedicated training page separate from the fighter list and event workspace.
- Support persistent, collapsible training groups and fast attendance updates.

Definition of done:

- League admins can manage recurring training groups.
- Training attendance can be updated quickly without a heavy scoring-style submit cycle.

### BL-052 Support ad hoc medals and special awards

Priority: `P3`
Related stories: `US-075`
Status: `Planned`

Scope:

- Let league admins add medals or special awards directly to fighters outside the event workspace.
- Keep the updates league-scoped and auditable.

Definition of done:

- League admins can record ad hoc awards without using event scoring.
- Fighter records show those awards cleanly.

## Notes

- This area already has the multi-league event foundation in place.
- The main remaining work is simplification, richer fighter data, and league-admin workflow ergonomics rather than missing event capability.
