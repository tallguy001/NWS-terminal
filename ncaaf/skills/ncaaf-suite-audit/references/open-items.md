# NCAAF suite — open items

Standing ledger: identified, not shipped. Read at the start of every audit; re-date at the end. Owner = who decides.

| # | Item | Owner | First raised | Closing condition |
|---|---|---|---|---|
| 1 | **Live scores (#LIVE) and an ncaaf-gameday push.** The NFL / EPL hubs carry live views fed by a gameday push into the page's database (`db` capability). Not in v1. | owner (scope) | 2026-10-26 | ncaaf-gameday skill with a push script and live_view in the shell; land_check-style gate PASS on a live Saturday. |
| 2 | **Daily scheduled build.** Owner 2026-10-26: "daily rebuild". **Created 2026-10-26:** scheduled task "NCAAF League Hub", daily 5:41 AM CT in a fresh cloud session (Mondays only in the offseason). Option not taken: extra Saturday-night / Sunday-morning runs in season. | owner | 2026-10-26 | First unattended run publishes in place with both gates PASS → close. |
| 3 | ~~House team.~~ **Closed 2026-10-26:** owner — "House team is Wisconsin". Operator §1, workspace §8, team card default, League Hub house card + highlights + two-number line (v1.1). Remaining option: an authored Badgers hub (the NFL Patriots-hub shape). | owner | 2026-10-26 | Closed; authored hub on request. |
| 4 | **On-demand scouting reports** (the `sample` + `db` "Write the scouting report" panel on team and game pages, as in the NFL / EPL hubs). | owner (scope) | 2026-10-26 | Team-report prompt + serializer + db `team_reads/<KEY>`; sweep checks a canned report. |
| 5 | **Player layer.** Excluded by design ("No player cards, just teams"). Recorded so a later request is a scope change, not a bug. | owner | 2026-10-26 | Owner asks for player pages. |
| 6 | **Bowl projections and the transfer portal / recruiting / coaching news layer.** Bowls are fitted but not simulated (opt-outs); no news panel. | suite | 2026-10-26 | A bowl-tie-in model with an opt-out caveat, or an explicit decision not to build. |
| 7 | **Kalshi spread and total ladders** (KXNCAAFSPREAD / KXNCAAFTOTAL), as the NFL hub reads them. v1 reads the game-winner market and futures only. | suite | 2026-10-26 | Ladder medians on game pages beside DraftKings' spread and total; qa sums. |
| 8 | **Conference tiebreakers.** The sim and the standings order use conference record → head-to-head (two-way) → rating; the leagues' published procedures are longer. | suite | 2026-10-26 | Per-conference tiebreak functions validated against ESPN's final standings of 2024–2025, or the approximation kept and re-stated. |
| 9 | **Quarterback / injury adjustments.** The house model (v1.1: results, team boxes, preseason poll) knows nothing of a starter change; it moves the market well before it moves the ratings. | suite | 2026-10-26 | A documented, validated adjustment (walk-forward) or a standing note (current state). |
| 10 | **24-team CFP for 2027.** Reported in talks (ESPN 2026-10-15), not approved; a decision is due by Dec 1, 2026. | suite | 2026-10-26 | Fact sheet + ncaaf_sim field rules updated when the CFP announces; else re-dated. |
| 11 | **HOUSE MODEL v1.1 season check.** Shipped 2026-10-26 on a modest, consistent gain (leave-one-season-out −0.077 points, 9 of 10 seasons; 2026 Weeks 1–8 −0.16). The 2024–2025 hold-out alone was not significant. | suite | 2026-10-26 | After the 2026 title game: v1.1 vs v1 on all of 2026 (walk-forward); keep if not worse, else revert to v1 params (calibration.json `v11.v1_params`). |

Re-dated: 2026-10-26 (v1.1).
