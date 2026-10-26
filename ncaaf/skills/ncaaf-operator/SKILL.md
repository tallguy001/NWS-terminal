---
name: ncaaf-operator
description: "Route any college football (NCAAF, FBS) question to the right workspace skill, enforce the data-source precedence, apply depth calibration, carry the house team (Wisconsin Badgers: my team, the Badgers) and the verified 2026-27 college football facts (138 FBS teams, conference membership, the 12-team CFP format and calendar, last season's champion) and the output contract. Use for ANY college football question that does not clearly match a more specific ncaaf-* skill: scores, standings, polls, CFP rankings and format, conference title races, bowl eligibility, TV, schedules, realignment, predictions, multi-part questions, or anything prefixed \"quick:\". Also consult it when unsure which ncaaf-* skill owns a request. This is the router and rulebook for the NCAAF suite, not a product. Do NOT use for the NFL (nfl-*), Wisconsin high school football (wiaa-fb) or other sports."
---

# ncaaf-operator

The glue skill for the 2026 college football workspace: routing, precedence, depth, facts, contract. Inside the "NCAAF" project,
the project doc `NCAAF_WORKSPACE.md` governs and this skill reinforces it; outside the project, this skill IS the workspace.
Section numbers (§) follow the NFL / NHL workspaces' so cross-references port.

## Routing table

| Request smells like | Route to |
|---|---|
| "League hub", "NCAAF hub", "CFB hub", "[team] page", "conference page", "week slate page", "game page", refresh / rebuild the hub | **ncaaf-hub** |
| Model line, win chance, "who does the model like", power ratings, projected wins, CFP / conference / title odds, bowl eligibility odds, "what if X beats Y", backtest, calibration | **ncaaf-sim** |
| "State of [team]", "is [team] for real", a team's CFP path, team deep dive (chat) | **ncaaf-team-card** |
| Raw numbers: scores, slate, standings, polls, CFP ranking, lines, box score, TV, "what week is it", Kalshi prices | **ncaaf-data-pull** (`phase.py` for gates) |
| QA / lint any product before delivery | **ncaaf-qa** (exit 1 = do not ship) |
| Suite maintenance, "codify", audit, open items | **ncaaf-suite-audit** |
| One player (stats, awards, Heisman) | not built (owner: teams only) → search, one pass, Reported tier, said plainly; ledger #5 |
| Live in-game check-ins, live scores on the hub | not built yet → `ncaaf_data.py game EID` for the state; ledger #1 |
| Bowl projections beyond the CFP, transfer portal, recruiting, coaching carousel | not built → search, tiered (§18); ledger #6 |

Multi-part questions compose products in sequence, each with its own data pass.

## Season phase (binding)
Every SCHEDULED product runs `phase.py --gate <product>` as step 0 and stops with its one line on exit 3.

| Phase (ESPN calendar, 2026) | Live products |
|---|---|
| preseason (before Aug 22) | League Hub in projection mode (prior-only ratings) |
| regular (Aug 22 – Nov 29) | everything; the hub daily |
| championship (Weeks 14–15: Nov 30 – Dec 12) | everything; title games and Selection Day (Dec 6) |
| postseason (Dec 13 – Jan 27) | hub (bowls and the CFP bracket), team cards |
| offseason | hub in final mode; the audit's annual walk (corpus, calibration, registry, fact sheet) |

## Data-source precedence (binding, §3)
1. **Live / very recent game data** → ncaaf-data-pull (ESPN scoreboard and summary). Never web-search a score.
2. **Everything the scripts carry** (schedule, finals, closing lines, standings, polls, CFP ranking, team statistics, DraftKings
   lines, Kalshi prices, HOUSE MODEL ratings and odds) → ncaaf-data-pull / ncaaf-sim. Scripts beat search for every number they
   hold. The HOUSE MODEL (v1.1) takes no market input: results, team box scores and the preseason AP poll (opinion, not a
   price) only. Kalshi is a second market beside DraftKings: never averaged with it, never blended with the HOUSE MODEL; a started game
   shows only the pre-kickoff price; a Kalshi–DraftKings gap is a disagreement between two markets, never an edge.
3. **Published models** (SP+, FPI, Sagarin, KenPom-style CFB ratings) → web search ONLY, one pass, vintage stamped, from the
   publisher; never blended with HOUSE MODEL values — shown side by side with the methodological reason.
4. **News layer** (injuries, quarterback changes, opt-outs, coaching, portal) → search, tiered per §18: Confirmed / Reported
   (name the reporter) / Speculation / Inference.
5. **Aggregator blocklist + Tier-4 floor (§3, identical to MLB / NFL / NHL, binding).** heavy.com is banned outright — never
   searched, fetched, cited or used to corroborate; same for Sportskeeda, ClutchPoints, Yardbarker, Pickdawgz, PredictEm,
   SportsGrid, Covers, Sportsbook Review and team-vertical content farms.

## Depth calibration (§2)
Pure lookups (a score, a kickoff, a channel, a rank) and anything prefixed **"quick:"** → the fact plus one line of context.
Everything else defaults to full analysis. When in doubt, go deep.

## House team (§1, owner decision 2026-10-26: "House team is Wisconsin")
- **Wisconsin Badgers = the house team** — fullest treatment; league-wide answers include the Wisconsin angle whenever one
  exists ("my team", "our game", "the Badgers" = Wisconsin); standings answers always detail the Big Ten race with the
  two-number rule; CFP answers always place Wisconsin against the cut; a slate answer leads with Wisconsin's game.
- The League Hub carries it: a House team card on the league home (record, Big Ten place, next game with HOUSE MODEL /
  DraftKings / Kalshi and the stakes, season odds, the two numbers), Wisconsin's row highlighted on every board, a header link
  and the top row of the picker (`hub_build.py --house WIS`, the default).
- Wisconsin facts come from the feeds and the fact sheet only (record, schedule, ranks, 2025 = 4–8 from the corpus); coaching,
  roster and injury news follow §3.4 tiers — nothing about the program is carried from memory.
- **Two-number rule (college form):** state (1) the conference-race gap — games behind the Big Ten title-game line (the
  second-best conference record), or games ahead of the first team outside it, with conference games left; and (2) the CFP gap —
  places inside or outside the 12-team cut in the committee's ranking (from Nov 3; the HOUSE MODEL committee proxy before),
  before automatic bids. Every team page on the hub prints both ("Two numbers.").

## Facts (verified 2026-10-26; `ncaaf-data-pull/references/season_2026_facts.json` IS the verification; re-verify each audit; tags C confirmed / R reported / U unpublished)
- **FBS 2026:** 138 teams — SEC 16, Big Ten 18, Big 12 16, ACC 17, American 14, Pac-12 8 (Boise State, Colorado State, Fresno
  State, Oregon State, San Diego State, Texas State, Utah State, Washington State), Mountain West 10 (incl. North Dakota State),
  Sun Belt 14 (East / West), MAC 13 (incl. Sacramento State), C-USA 10, Independents 2 (Notre Dame, UConn) [C].
- **Last season:** Indiana won the national title 27–21 over Miami (Jan 19, 2026, Hard Rock Stadium), 16–0, the program's first
  [C].
- **CFP 2026–27:** 12 teams; five automatic bids (ACC, Big Ten, Big 12, SEC champions + the best champion of the American,
  C-USA, MAC, Mountain West, Pac-12, Sun Belt), seven at-large; Notre Dame in if top 12; straight seeding, byes 1–4; an AQ outside
  the top 12 takes the lowest seed; first round on campus Dec 18–19; quarterfinals Fiesta (Dec 30), Peach / Rose / Cotton (Jan
  1); semifinals Orange (Jan 14), Sugar (Jan 15); title game Allegiant Stadium, Las Vegas, Mon Jan 25, 2027 [C]. No 1 seed picks
  its quarterfinal bowl from 2026 [C]. Rankings Tuesdays Nov 3, 10, 17, 24, Dec 1; Selection Day Sun Dec 6 [C]. A 24-team format
  for 2027 is reported in talks, NOT approved (decision due by Dec 1) [R].
- **Championship weekend:** Big 12 (AT&T Stadium) and Pac-12 (top seed hosts) Fri Dec 4; SEC (Atlanta), Big Ten (Indianapolis),
  ACC (Charlotte), American Sat Dec 5 [C]; Mountain West, Sun Belt, C-USA, MAC (Ford Field) Dec 4–5, days unpublished [U].

## Output contract (every product)
1. Freshness stamp — script stamps carried through; search vintages inline; say when a feed lags.
2. Samples beside rates: per-play rates under ~4 games are noise; the ratings lean on the prior until ~5 games.
3. Tables for data, prose for meaning; an interpretive clause on every number.
4. Times **CT first, UTC in parentheses**; TBD kickoffs on their Eastern date. Bold team names on first meaningful reference.
5. End with a verdict or bottom line — every product, every time; analytical verdicts state their weighting and an honest range
   before the label.
6. Honesty: unavailable or conflicting information said plainly; house numbers labeled HOUSE MODEL and never blended with market
   or published numbers; "if the season ended today" always names its basis; a bracket is never "set" before Selection Day.

## Published pages (fixed URLs, republished in place)
| Page | URL | Refresh |
|---|---|---|
| NCAAF League Hub (home, 138 teams, 11 conferences, 15 weeks, game pages) | https://claude.ai/artifact/3WewjztwCbPeZYbkdv9Dox | daily 5:41 AM CT scheduled task "NCAAF League Hub" (Mondays only in the offseason) + on request |

Skill scripts resolve under `/mnt/skills/*/<skill>/scripts` or `$HOME/.claude/skills/synced/*/<skill>/scripts` — always resolve
with both globs (dash shell: no brace expansion).
