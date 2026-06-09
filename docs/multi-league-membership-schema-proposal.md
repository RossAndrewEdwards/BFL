# Multi-League Membership Schema Proposal

## Purpose

This document proposes the schema and application-direction changes required to move from:

- one user -> one league

to:

- one user -> many league memberships
- one active league context at a time

It is intended to be reviewed before any implementation work begins.

## Why This Change Is Needed

The current multi-league MVP assumes:

- `users.league_id` holds the player's or league admin's league
- a logged-in user has exactly one league context
- most permission checks can infer league access from `users.league_id`

That model does not support:

- a player joining multiple leagues
- a user being a player in one league and a league admin in another
- switching active league context from the header

## Proposed Model

## 1. Keep global user identity separate from league membership

`users` should represent the account itself:

- login identity
- password hash
- display name
- platform-wide metadata
- global `site_admin` capability if needed

`users` should no longer be the source of truth for league membership.

## 2. Add a `league_memberships` table

Proposed table:

```sql
league_memberships
- id
- user_id
- league_id
- role
- status
- manager_limit
- joined_at
- invited_at
- left_at
- created_at
- updated_at
```

Suggested meaning:

- `user_id`: the account
- `league_id`: the league membership belongs to
- `role`: `player` or `league_admin`
- `status`: `active`, `invited`, `inactive`, `removed`
- `manager_limit`: how many teams this user may manage in that specific league

Recommended uniqueness:

- unique `(user_id, league_id)`

## 3. Keep `site_admin` as a global account-level capability

Recommended options:

### Option A

Keep `users.role` only for platform-wide role such as:

- `site_admin`
- `user`

And move league-level roles fully into `league_memberships.role`.

### Option B

Keep `users.role` temporarily for compatibility during migration, but treat:

- `site_admin` as global
- `league_admin` and `player` as membership-derived long term

Recommended direction: `Option A`

It is cleaner and better matches the product.

## 4. Add active league context to session state

When a user logs in:

- if they have one active membership, select it automatically
- if they have multiple active memberships, choose a default and allow switching

Recommended session field:

- `session["active_league_id"]`

This becomes the main league context for:

- homepage featured content
- fighters
- teams
- events
- player team management
- league-admin pages

## 5. Update team ownership assumptions

Teams should remain directly league-scoped.

That means:

- `fantasy_teams.league_id` stays
- `fantasy_teams.player_user_id` stays
- permission checks must verify that the user has an active membership in `fantasy_teams.league_id`

This is good because it avoids rebuilding team data around indirect joins only.

## Migration Strategy

## Phase 1: Introduce memberships without removing old fields

1. Create `league_memberships`
2. Backfill one membership per current non-site-admin user from `users.league_id`
3. Preserve current app behavior temporarily

## Phase 2: Switch reads to memberships

1. Move onboarding, login, and permission helpers to use `league_memberships`
2. Introduce active league context in the session
3. Update route scoping to use active membership rather than `users.league_id`

## Phase 3: Clean up legacy assumptions

1. Remove dependence on `users.league_id` for permissions
2. Decide whether `users.league_id` should be dropped or kept only as legacy compatibility during transition
3. Move `manager_limit` to memberships fully if we want per-league player limits

## Permission Model Changes

The permission layer should answer:

1. Is this user a `site_admin`?
2. Does this user have a membership in this league?
3. What role does this user have in this league?
4. Is that membership active?

Recommended helper concepts:

- `memberships_for_user(user_id)`
- `active_membership(user_id, active_league_id)`
- `user_is_league_admin(user_id, league_id)`
- `user_is_player_in_league(user_id, league_id)`

## UI and Flow Changes

This schema change implies:

- login may need a league selector or default active league choice
- the shared header should gain a league switcher for multi-membership users
- invite and join links should create or update memberships, not overwrite a single `league_id`
- claim flow must be membership-aware

## Main Risks

- hidden assumptions on `users.league_id` across existing helpers and templates
- role checks that currently assume one league per user
- onboarding flows accidentally replacing membership instead of adding it
- stale `active_league_id` session values after membership removal or league deactivation

## Recommendation

Recommended next implementation order:

1. approve this schema direction
2. add `league_memberships`
3. backfill existing memberships
4. update auth and league-context helpers
5. add header league switching
6. then update player and league-admin flows on top of the new membership model
