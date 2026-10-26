# NCAAF suite — open items

Standing ledger: identified, not shipped. Read at the start of every audit; re-date at the end. Owner = who decides.

| # | Item | Owner | First raised | Closing condition |
|---|---|---|---|---|
| 1 | **Live scores (#LIVE) and an ncaaf-gameday push.** The NFL / EPL hubs carry live views fed by a gameday push into the page's database (`db` capability). Not in v1. | owner (scope) | 2026-10-26 | ncaaf-gameday skill with a push script and live_view in the shell; land_check-style gate PASS on a live Saturday. |
| 2 | **Daily scheduled build.** The sibling hubs rebuild on a schedule (e.g. "NHL League Hub" daily 5:17 AM CT). Proposed: daily ~5:41 AM CT, plus Saturday evening and Sunday morning in season. | owner (approve) | 2026-10-26 | Scheduled task created after the skills are saved; first unattended run publishes in place with both gates PASS. |
| 3 | **House team.** No house team set (Wisconsin is the natural candidate given the owner's other suites, but not assumed). | owner | 2026-10-26 | Owner names a team or confirms none; operator §1 updated; optional authored house hub. |
| 4 | **On-demand scouting reports** (the `sample` + `db` "Write the scouting report" panel on team and game pages, as in the NFL / EPL hubs). | owner (scope) | 2026-10-26 | Team-report prompt + serializer + db `team_reads/<KEY>`; sweep checks a canned report. |
| 5 | **Player layer.** Excluded by design ("No player cards, just teams"). Recorded so a later request is a scope change, not a bug. | owner | 2026-10-26 | Owner asks for player pages. |
| 6 | **Bowl projections and the transfer portal / recruiting / coaching news layer.** Bowls are fitted but not simulated (opt-outs); no news panel. | suite | 2026-10-26 | A bowl-tie-in model with an opt-out caveat, or an explicit decision not to build. |
| 7 | **Kalshi spread and total ladders** (KXNCAAFSPREAD / KXNCAAFTOTAL), as the NFL hub reads them. v1 reads the game-winner market and futures only. | suite | 2026-10-26 | Ladder medians on game pages beside DraftKings' spread and total; qa sums. |
| 8 | **Conference tiebreakers.** The sim and the standings order use conference record → head-to-head (two-way) → rating; the leagues' published procedures are longer. | suite | 2026-10-26 | Per-conference tiebreak functions validated against ESPN's final standings of 2024–2025, or the approximation kept and re-stated. |
| 9 | **Quarterback / injury adjustments.** The house model is results-only; a starter change moves the market well before it moves the ratings. | suite | 2026-10-26 | A documented, validated adjustment (walk-forward) or a standing note (current state). |
| 10 | **24-team CFP for 2027.** Reported in talks (ESPN 2026-10-15), not approved; a decision is due by Dec 1, 2026. | suite | 2026-10-26 | Fact sheet + ncaaf_sim field rules updated when the CFP announces; else re-dated. |

Re-dated: 2026-10-26 (v1).
