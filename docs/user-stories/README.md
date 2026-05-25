# User Stories Index

This folder is the canonical source for the platform user stories.

The older consolidated file at `docs/multi-league-user-stories.md` is being kept as a legacy planning reference, but new story expansion should happen in this folder.

## Document Map

- [01 Platform and Governance](./01-platform-and-governance.md)
- [02 League Admin Operations](./02-league-admin-operations.md)
- [03 Player Membership and Teams](./03-player-membership-and-teams.md)
- [04 League Workspace and Navigation](./04-league-workspace-and-navigation.md)
- [05 Shared Site Experience and Fantasy UX](./05-shared-site-experience-and-fantasy-ux.md)

## Product Direction

The platform is a shared fantasy-league system for multiple clubs.

It supports three main user types:

- `Platform Admin`: owns the platform, rules, reporting, and league oversight
- `League Admin`: runs one or more club leagues from `My League`
- `Player`: joins leagues, creates teams, and tracks performance inside an active league context

## Core Assumptions

- Users can belong to multiple leagues, but only one active league context is used at a time.
- Fighter pools, teams, players, standings, and event scoring stay league-scoped.
- Scoring rules, season rules, and formula definitions are platform-wide.
- Logged-out users can access only the homepage, rules page, and future platform contact content.
- Logged-out users must not see league standings, fighter data, team data, or player performance data.
- Shared platform branding uses `Buhurt Fantasy League`.
- Logged-in users should always be able to tell which league they are currently acting in.

## Story Coverage

- `US-001` to `US-009`, `US-022` to `US-025`, `US-069`, `US-070`, `US-082`: platform setup, governance, reporting, and settings ownership
- `US-010` to `US-015`, `US-029`, `US-042`, `US-043`, `US-066`, `US-067`, `US-072` to `US-075`: league-admin operations, scoring workflows, fighter maintenance, training, and awards
- `US-016` to `US-021`, `US-033` to `US-035`, `US-040`, `US-041`, `US-064`, `US-065`, `US-076` to `US-079`: player membership, teams, fighter profiles, requests, and personal notifications
- `US-026` to `US-028`, `US-030` to `US-032`, `US-036` to `US-039`, `US-068`: workspaces, admin hierarchy, and navigation
- `US-044` to `US-063`, `US-071`, `US-080`, `US-081`: shared-site UX, leaderboard redesign, shared card templates, collectible-card direction, ranking/search, and theme choice

## Follow-Up Planning Note

The user-story split is now complete.
