# 06 UX and Interaction Design Backlog

## Scope

This document covers the broader app-like interaction pass: shell continuity, transition behaviour, richer card browsing, dashboard UX, visual leaderboard behaviour, discovery, mobile polish, and accessibility/performance refinement.

## Items

### BL-058 Build an app-like shell and preserve interaction context

Priority: `P3`
Related stories: `US-083`, `US-084`, `US-085`
Status: `Planned`

Scope:

- Make the shared shell feel more app-like through consistent framing, lightweight transitions, and context preservation.
- Preserve useful recent state such as scroll position, open sections, or selected views where practical and safe.

Definition of done:

- Moving around the app feels more continuous and less like bouncing between disconnected pages.
- Useful page context is preserved without leaking data or mixing league contexts.

### BL-059 Make fighter browsing card-led and more immersive

Priority: `P3`
Related stories: `US-086`, `US-087`, `US-088`, `US-089`, `US-090`, `US-091`
Status: `Planned`

Scope:

- Push fighter browsing toward a card-grid experience with richer card-to-profile continuity, tier styling, and stronger on-card fantasy information.

Definition of done:

- Fighter discovery feels card-first rather than row-first.
- Opening a fighter preserves the sense that the user is still inside the same collectible-card system.

### BL-060 Add richer team-building microinteractions

Priority: `P3`
Related stories: `US-092`, `US-093`, `US-094`, `US-095`, `US-096`, `US-097`, `US-098`
Status: `Planned`

Scope:

- Improve team-building interactions with direct card actions, clearer transfer feedback, instant budget updates, invalid-state explanations, and optimistic interaction patterns where safe.

Definition of done:

- Team-building feels responsive, interactive, and easy to understand.
- Players get immediate, clear feedback when roster changes succeed or fail.

### BL-061 Create a stronger player dashboard experience

Priority: `P3`
Related stories: `US-099`, `US-100`, `US-101`, `US-102`, `US-103`
Status: `Planned`

Scope:

- Build a more intentional logged-in player home or dashboard view with rank, team, event, deadline, recent-performance, and next-action emphasis.

Definition of done:

- Players land on a more personal and useful overview after login.
- The dashboard clearly orients the player around what matters next in their active league.

### BL-062 Deepen leaderboard and event-result presentation

Priority: `P3`
Related stories: `US-104`, `US-105`, `US-106`, `US-107`, `US-108`, `US-109`, `US-110`
Status: `Planned`

Scope:

- Push leaderboard and result browsing toward a more visual, competitive, and story-like experience.
- Add stronger rank movement cues, own-team emphasis, rival comparison, readable event-result feeds, and clearer post-event impact summaries.

Definition of done:

- Leaderboard browsing feels dramatic and useful rather than purely tabular.
- Players can understand event outcomes, point breakdowns, and leaderboard shifts more easily.

### BL-063 Improve discovery, mobile UX, and accessibility polish

Priority: `P3`
Related stories: `US-111`, `US-112`
Status: `Planned`

Scope:

- Improve discovery with better search, filter, badge, and empty-state behaviour.
- Refine mobile-friendly patterns for cards, navigation, team editing, and filters.
- Strengthen keyboard access, reduced-motion support, loading states, and accessible feedback behaviour.

Definition of done:

- Fighter discovery feels fast and modern.
- The app remains comfortable on mobile.
- Accessibility and performance polish supports the richer interaction model cleanly.
