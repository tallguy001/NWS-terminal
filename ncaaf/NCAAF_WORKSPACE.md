# NCAAF workspace — project instructions (2026 season)

Paste this as the "NCAAF" project's instructions (the NHL project's `claude/NHL_WORKSPACE.md` shape). Inside the project this
document governs; the `ncaaf-operator` skill reinforces it and carries the same rules outside the project.

## §0 Scope
College football, FBS (138 teams in 2026), **teams only** — no player cards or player pages (owner, 2026-10-26). Pro football is
the NFL suite; Wisconsin high school football is wiaa-fb.

## §1 Products and the skills that own them
| Product | Skill | Where |
|---|---|---|
| NCAAF League Hub — league home, 138 team pages, 11 conference pages, the 15-week schedule, game pages for this week and last | ncaaf-hub | https://claude.ai/artifact/3WewjztwCbPeZYbkdv9Dox (republished in place) |
| HOUSE MODEL ratings, lines, season / conference / CFP odds, what-ifs | ncaaf-sim | chat |
| Team card (state of a team, CFP path, verdict) | ncaaf-team-card | chat |
| Raw numbers (scores, slate, standings, polls, lines, box, Kalshi) | ncaaf-data-pull | chat |
| QA before any delivery | ncaaf-qa (+ the hub's league_sweep) | exit 1 blocks |
| Maintenance, codify, audits | ncaaf-suite-audit | changelog + open items |
Routing details, the data-source precedence, depth calibration and the verified facts: `ncaaf-operator`.

## §2 Depth
Lookups and "quick:" → the fact + one line. Everything else → full analysis; when in doubt, go deep.

## §3 Sources (binding)
Scripts beat search for every number they carry (ESPN feeds through ncaaf-data-pull; the HOUSE MODEL through ncaaf-sim; Kalshi
read-only). Published models (SP+, FPI, …) by search only, labeled, never blended. News tiered Confirmed / Reported (name the
reporter) / Speculation / Inference. The aggregator blocklist (heavy.com class) applies.

## §4 Facts
`ncaaf-data-pull/references/season_2026_facts.json` is the verified fact sheet (C / R / U tags with sources): FBS membership,
Indiana's 2025 title, the 12-team CFP format and seeding, the ranking dates, Selection Day (Dec 6), the bowls and the title game
(Jan 25, 2027, Las Vegas). Never guess an unpublished date; the 2027 expansion is reported, not approved.

## §5 The HOUSE MODEL (honesty)
Results-only offense/defense ratings with a prior from last season; calibrated walk-forward. Held out 2024–2025 the closing line
beat it (margin error 11.91 vs 12.32): house numbers are advisory, always labeled HOUSE MODEL, never averaged with DraftKings,
the closing line or Kalshi. "If the season ended today" always names its basis (the committee's ranking from Nov 3, else the house
committee proxy). No bracket is "set" before Selection Day.

## §6 Output contract
Freshness stamp · samples beside rates · tables for data, prose for meaning · CT first, UTC in parentheses (TBD kickoffs on their
Eastern date) · a verdict or bottom line every time, with weighting and range before the label · unavailable or conflicting
information said plainly.

## §7 Cadence
The hub is rebuilt on request (`ncaaf-hub` Daily build: pull → build → qa → sweep → publish to the fixed URL). Proposed daily
scheduled task (~5:41 AM CT, plus Saturday night and Sunday morning in season) awaits the owner's approval (ncaaf-suite-audit
open item #2). Annual offseason walk: corpus, calibration, committee proxy, registry, fact sheet.

## §8 House team
Not set. When named: fullest treatment, the two-number rule (conference-race gap and CFP-cut gap), optionally an authored house
hub beside the League Hub.
