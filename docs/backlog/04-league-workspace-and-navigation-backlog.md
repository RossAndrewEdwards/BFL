# 04 League Workspace and Navigation Backlog

## Scope

This document covers `My League`, league-first hierarchy, navigation rules, header behaviour, and league-oriented admin journeys.

## Items

### BL-007 League-admin assignment workflow inside league management

Priority: `P1`
Related stories: `US-003`, `US-031`
Status: `Implemented`

Scope:

- Support promotion of existing players to league admins from the proper league-management flow.
- Keep detailed promotion actions in the dedicated player-management experience rather than creating a second admin-management area.

### BL-013 Shared homepage with league-aware featured content

Priority: `P1`
Related stories: `US-016`, `US-020`, `US-021`
Status: `Implemented`

Scope:

- Keep one shared homepage.
- Show league-aware featured content for logged-in users.
- Keep logged-out visitors away from player and standings data.

### BL-017 Tests for league isolation and permissions

Priority: `P1`
Related stories: `US-007`, `US-009`, `US-016`
Status: `Implemented`

Scope:

- Cover isolation, permission, league-context, and guest-access scenarios with regression tests.

### BL-023 League workspace and hierarchy polish

Priority: `P2`
Related stories: `US-026`, `US-027`, `US-028`, `US-030`, `US-032`, `US-036`, `US-037`, `US-038`, `US-039`
Status: `Implemented`

Scope:

- Make `My League` the operational home for league admins.
- Improve league-first navigation to fighters, events, players, and teams.
- Remove the redundant top-level `Admin` header path for league admins.
- Keep detailed player participation controls inside the dedicated players experience rather than duplicating them in the dashboard.

### BL-027 Add a shared footer and simplify secondary navigation

Priority: `P2`
Related stories: `US-044`
Status: `Implemented`

Scope:

- Add a shared footer across public and logged-in views.
- Move secondary links out of the primary header where that makes the shell cleaner.
- Preserve private-data boundaries while adding footer navigation.

Definition of done:

- The site has a shared footer visible in the main shell.
- The footer contains safe secondary navigation links.
- Header navigation can be simplified without losing access to important utility pages.

### BL-028 Add contact and footer-level information pages

Priority: `P2`
Related stories: `US-045`
Status: `Implemented`

Scope:

- Add a platform-level `Contact Us` page.
- Make it reachable from the new shared footer.
- Keep the page safe for both guests and logged-in users.

Definition of done:

- `Contact Us` exists as a page.
- Footer navigation links to it.
- The page contains platform-level support or contact information only.

### BL-036 Polish shell actions and logout affordance

Priority: `P2`
Related stories: `US-059`
Status: `Implemented`

Scope:

- Make logout visually distinct from ordinary navigation.
- Keep the shell readable and role-aware across desktop and mobile.

Definition of done:

- Logout looks different from ordinary nav links.
- The control remains accessible and clear on smaller screens.
- Logout still routes back to the homepage.

## Notes

- League-first admin hierarchy is largely in place already.
- The new work here is mostly refinement around space usage and dashboard focus rather than missing navigation foundations.

### BL-045 Reduce repetitive page chrome

Priority: `P3`
Related stories: `US-068`
Status: `Implemented`

Scope:

- Remove low-value descriptive subtitles or repeated explanatory copy from pages where the heading and layout already make the workflow clear.
- Favour screen space for primary working content over repeated intro text.

Definition of done:

- Repetitive page descriptions are removed or reduced across the main app shell.
- Complex workflows can still show targeted guidance where it adds real value.

### BL-046 Simplify the platform-admin dashboard

Priority: `P3`
Related stories: `US-069`
Status: `Implemented`

Scope:

- Move the most-used platform-admin links to the top of the dashboard.
- Remove or reduce low-value sections such as season snapshots, operational signals, recent platform activity, and media shortcuts where they are no longer useful.

Definition of done:

- The platform-admin dashboard reads as a quick oversight and navigation page.
- Removed sections remain reachable from their dedicated pages if still needed elsewhere.
