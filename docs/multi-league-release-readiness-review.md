# Multi-League Release Readiness Review

## Purpose

This document marks the transition from implementation backlog work into release-readiness review for the multi-league version of the app.

It summarizes:

- what is complete now
- what still needs polish before a wider release
- what belongs in a later phase rather than blocking launch

## Overall Assessment

The app is now in a strong multi-league MVP state.

The core architecture, permissions, data isolation, role model, and league management workflows are in place. The product has moved beyond "single-league with patches" and now behaves like a shared platform with:

- platform-level ownership
- league-level administration
- player-level participation inside one assigned league

The multi-league work should now be treated as release hardening and product polish, not foundational architecture work.

## Complete Now

### Platform and league model

- `leagues` table exists and existing Invicta data is seeded into the first league
- league-scoped records carry `league_id`
- `site_admin`, `league_admin`, and `player` roles are implemented
- migration and rollback runbook exists

### Access control and league isolation

- league context helpers and route scoping are in place
- league admins cannot access another league's fighters, teams, players, or events
- players belong to one league only
- team building is restricted to the current league's fighter pool
- audit logging tracks league-scoped changes

### Site-admin league management

- site admin can create, edit, and manage leagues
- league admin assignment is handled from league management rather than a separate primary workflow
- league quotas for players and teams are enforced
- league edit view shows players, teams, and league admins together
- league starter templates are supported for new league creation

### League-admin operations

- league admins can manage fighters within their own league
- league admins can manage event results within their own league
- league admins can manage players and teams within their own league
- league admins can manage league branding, including header logo

### Player and public experience

- logged-out users are limited to homepage and rules
- logged-out users do not see top fighters, top teams, or other player/league data
- logged-in users see league-aware branding and league context in the header
- homepage featured content changes by logged-in user's league
- claim and login flows preserve league context

### Site-admin visibility and operations

- site admin dashboard shows league health and operational signals
- rules and season lifecycle remain site-admin only
- audit logs can be reviewed with league context
- league-safe bulk fighter import/export and event import/export now exist

### Engineering safety

- `app.py` has been refactored into a thinner entrypoint
- route groups and support modules are separated
- automated regression coverage exists for key multi-league rules
- current automated suite passes at `144` tests

## Needs Polish Before Wider Release

These are not blockers to the core multi-league model, but they are the highest-value polish items before broader rollout.

### Bulk import/export UX

- the new import panels are functional, but still feel quite raw
- CSV guidance could be clearer with downloadable examples or column help
- validation feedback could become more row-specific instead of generic failure messaging

### Site-admin dashboard depth

- the operational signals section is useful, but still a first pass
- trend reporting is not yet a full reporting view
- league comparison is good for operations but not yet strong for business reporting

### Page-level league context cues

- header context is in place
- some deeper pages could still reinforce league context more explicitly in headings or supporting text

### Live workflow QA

- the app needs a final end-to-end smoke pass using realistic league-admin and player journeys
- especially important areas:
  - invite and claim flow
  - quota edge cases
  - CSV import feedback
  - inactive or archived league behavior

## Future Phase Items

These should not block the current MVP release.

### BL-021 Future league reassignment flexibility

- future-proofing for league switching or reassignment can stay deferred
- current product direction is still one user to one league

### Richer reporting and analytics

- trend reports
- date-range comparisons
- more advanced league health reporting
- adoption and growth reporting for the platform owner

### More advanced import/export workflows

- downloadable CSV templates
- file upload import instead of paste-only flow
- richer import preview and validation reporting
- broader export coverage beyond current fighter and event slices

## Story and Backlog Status Summary

### User stories

- Core MVP stories are effectively implemented through the current app structure and test coverage.
- The main remaining gaps are polish-oriented rather than structural.

### Backlog

- `P0` items: complete
- `P1` items: complete
- `P2` items:
  - `BL-019`: implemented
  - `BL-020`: partially implemented through dashboard operational signals
  - `BL-021`: intentionally deferred
  - `BL-022`: first practical implementation completed

## Recommended Next Step

The best next move is not another architecture backlog item.

The best next move is a short release-hardening pass:

1. run a structured browser QA sweep across site-admin, league-admin, and player journeys
2. capture any UI or wording issues as polish tickets
3. decide whether the current MVP is ready for internal club testing

## Release Recommendation

Recommended status: `Ready for internal multi-league testing`

Reason:

- the platform model is now implemented
- core security and isolation behaviors are covered
- admin workflows exist for real operation
- remaining work is mostly UX polish and broader reporting depth rather than missing product foundations
