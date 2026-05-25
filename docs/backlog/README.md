# Backlog Index

This folder is the canonical source for the modular implementation backlog.

The older consolidated file at `docs/multi-league-implementation-backlog.md` is being kept as a legacy planning reference, but new backlog planning should happen in this folder.

## Document Map

- [01 Platform and Governance Backlog](./01-platform-and-governance-backlog.md)
- [02 League Admin Operations Backlog](./02-league-admin-operations-backlog.md)
- [03 Player Membership and Teams Backlog](./03-player-membership-and-teams-backlog.md)
- [04 League Workspace and Navigation Backlog](./04-league-workspace-and-navigation-backlog.md)
- [05 Shared Site Experience and Fantasy UX Backlog](./05-shared-site-experience-and-fantasy-ux-backlog.md)
- [06 UX and Interaction Design Backlog](./06-ux-and-interaction-design-backlog.md)

## Goal

This backlog turns the approved modular user stories into a practical implementation plan for the current Flask + SQLite app.

The platform direction remains:

- `Platform Admin` owns platform governance, reporting, rules, and season control
- `League Admin` manages league-scoped fighters, events, players, and teams through `My League`
- `Player` can belong to multiple leagues and acts inside one active league context at a time

## Delivery Principles

- Keep scoring, formulas, roster rules, budget rules, and season rules platform-wide.
- Scope fighters, events, teams, players, standings, and score history to a league.
- Keep logged-out access limited to safe public content.
- Keep one shared shell, but make active league context obvious for logged-in users.
- Prefer league-first admin navigation over flat global admin destinations.
- Treat the shared Buhurt calendar as the source for scheduled event generation wherever practical.

## Current State Summary

- `BL-001` through `BL-047` now have explicit coverage in the modular backlog.
- `BL-001` through `BL-047` are mostly implemented, with remaining gaps concentrated in deeper card polish and newer UX-heavy work.
- `BL-048` through `BL-063` capture the latest story expansion around settings ownership, richer fighter flows, player request handling, leaderboard/search polish, theme choice, and app-like interaction design.
- The main remaining work is now product-fit refinement, player-facing richness, and higher-touch UX polish rather than missing multi-league foundations.

## Status Meanings

- `Implemented`: already delivered in the app
- `Partial`: some support exists, but more work is still needed
- `Planned`: backlog item exists but has not yet been implemented

## Current Delivery Snapshot

- `Implemented`: `BL-001` through `BL-047` except the still-deepening card-template items
- `Partial`: `BL-039`, `BL-040`
- `Planned`: `BL-048` through `BL-063`
- `Likely refinement areas even after implementation`: collectible-card depth, richer fighter profiles, player request flows, dashboard UX, and interaction polish

## User Story Traceability

- `US-001` to `US-009`, `US-022` to `US-025`, `US-069`, `US-070`, `US-082`: `BL-001`, `BL-003`, `BL-004`, `BL-006`, `BL-014`, `BL-015`, `BL-016`, `BL-018`, `BL-019`, `BL-020`, `BL-047`, `BL-048`
- `US-010` to `US-015`, `US-029`, `US-042`, `US-043`, `US-066`, `US-067`, `US-072` to `US-075`: `BL-008`, `BL-009`, `BL-010`, `BL-022`, `BL-025`, `BL-026`, `BL-034`, `BL-043`, `BL-044`, `BL-049`, `BL-050`, `BL-051`, `BL-052`
- `US-016` to `US-021`, `US-033` to `US-035`, `US-040`, `US-041`, `US-064`, `US-065`, `US-076` to `US-079`: `BL-011`, `BL-012`, `BL-013`, `BL-021`, `BL-024`, `BL-041`, `BL-042`, `BL-053`, `BL-054`
- `US-026` to `US-028`, `US-030` to `US-032`, `US-036` to `US-039`, `US-068`: `BL-007`, `BL-017`, `BL-023`, `BL-027`, `BL-028`, `BL-036`, `BL-045`, `BL-046`
- `US-044` to `US-063`, `US-071`, `US-080`, `US-081`: `BL-027`, `BL-028`, `BL-029`, `BL-030`, `BL-031`, `BL-032`, `BL-033`, `BL-035`, `BL-037`, `BL-038`, `BL-039`, `BL-040`, `BL-055`, `BL-056`, `BL-057`
- `US-083` to `US-112`: `BL-058`, `BL-059`, `BL-060`, `BL-061`, `BL-062`, `BL-063`
