---
name: ncaaf-hub
description: "Build the styled NCAAF League Hub as an artifact (teams only, no player pages): the league home (this week's games with HOUSE MODEL, DraftKings and Kalshi; AP, Coaches and CFP rankings; the CFP picture and bracket if the season ended today; title, playoff and conference odds; conference races; power board; efficiency map; team stats; season trends with the house-vs-closing scorecard; calendar), a page for each of the 138 FBS teams (record, conference standings, season odds and seed distribution, schedule and results with lines, ratings and percentile profile, record check, team stats), a page per conference, every week of the schedule and a page for each game of this week and last (preview: the line, tape, matchups, stakes; final: scoring, box, win probability, forecasts vs result); nothing authored. Use for \"college football hub\", \"NCAAF hub\", \"CFB hub\", \"league hub\", \"[team] page\", \"conference page\", \"week slate\", \"game page\", \"refresh the hub\", \"CFP picture\". Requires ncaaf-data-pull, ncaaf-sim, ncaaf-qa."
---

# ncaaf-hub

The college port of nfl-hub / epl-hub (themselves nba-hub and mlb-team-hub's "broadcast package"): the same split shell,
design system (the NFL League Hub's stylesheet, verbatim), percentile scale, fit-to-width boards and back trail. Every number
comes from the pull and is rendered by the script; nothing on the page is authored. **Teams only** (owner, 2026-10-26: "No
player cards, just teams"): no player pages, no player search.

**Fixed URL (first published 2026-10-26): NCAAF League Hub https://claude.ai/artifact/3WewjztwCbPeZYbkdv9Dox** — republish in
place; never create another page.

| File | Role |
|---|---|
| `scripts/hub_pull.py` | Collector → `league.json` (schema ncaaf-hub/1): season events with closing lines, the registry, HOUSE MODEL ratings + every game's house line / total / win chance + walk-forward pregame lines on this season's finals, the season simulation and today's committee-proxy picture, records (home/away/neutral/conference, one-score, Pythagorean, schedule strength, rating-expected wins), rankings, ESPN team stats → 25 rates with FBS ranks and percentiles, last season from the corpus, Kalshi (games of this week and last + futures), game summaries (last week's finals and this week's started games), the fact sheet. ≈30 s cold, ≈15 s warm. |
| `scripts/hub_build.py` | Renderer: `league --pull P --out-dir OUT` → `index.html` (shell) + `league/NCAAF.json`, `teams/<KEY>.json` ×138, `confs/<CONF>.json` ×11, `weeks/W1..W15.json` (+ `WP` postseason), `games/w<NN>.json` (game pages bundled by week), `publish-files.json`; QA-only `league-hub-full.html` and `games-qa.html` (never published). ≈4 s; ≈12 MB. |
| `scripts/hub_ctx.py` · `scripts/hub_common.py` | Build context (lookups, kickoff / line / result / cover formatting) · shared helpers (percentile scale, `rb_table` with the fit-to-width + sort contract, sections, tabs, ladders, chips, themes). |
| `scripts/pages_landing.py` · `pages_team.py` · `pages_conf.py` · `pages_week.py` · `pages_game.py` | The five view renderers (sections below). |
| `scripts/league_shell.py` | Shell JS: router (`#NCAAF`, `#<KEY>`, `#C-<CONF>`, `#W<n>`, `#WP`, `#G<eid>`), picker grouped by conference with the conferences and weeks on top, segmented tabs, click-to-sort boards (rank cells renumber), chart tooltips, back trail (crumbs-v1, sessionStorage `ncaaf_trail`), scroll memory, `FIT_JS`. `window.ncaafHub` = {show, cache, D, trail} for the gates. |
| `scripts/ncaaf_css.py` | NCAAF-only rules (FCS chips, rank numbers, conference-race cards, CFP bracket, game hero, linescore, paired box bars, win-probability chart, calendar tags), appended after the template. |
| `scripts/league_sweep.py` | Render gate (see QA). |
| `assets/hub-template.html` | The single styling source: the published NFL League Hub's stylesheet (nfl-hub v1.15) — template, percentile layer, NFL additions, picker, weekly schedule, landing, crumbs, scout sections, game pages. Player, search and live rules left out. |

## Daily build (deterministic)

```bash
export PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
python3 <ncaaf-data-pull>/scripts/phase.py --gate hub                         # exit 3 = dormant: stop with its line
python3 scripts/hub_pull.py --league --json league.json [--sims 10000] [--seed YYYYMMDD] [--no-kalshi]
python3 scripts/hub_build.py league --pull league.json --out-dir OUT
python3 <ncaaf-qa>/scripts/qa.py OUT/league-hub-full.html --pull league.json   # exit 1 blocks
python3 scripts/league_sweep.py OUT                                            # exit 1 blocks; 2 = no browser (never claim a pass)
python3 scripts/league_sweep.py OUT --dark --teams 40
```
The sim seed defaults to the build date (Central), so two builds on one day print identical odds. The gates need the Python
Playwright binding: a cloud container ships only Node's — `pip install --break-system-packages playwright==<the Node package's
version>` (never `playwright install`; it drives `/opt/pw-browsers`).

## Publishing
Artifact `publish` with `file_path` = `OUT/index.html`, `root` = `OUT` and `files` = every path in `OUT/publish-files.json`
(a publish keeps files it is not given, so always send the full list; ≈169 files), plus `url` = the fixed URL above. No
runtime capabilities are declared (no `db`, no `sample`: nothing is written by viewers). In a new conversation, Artifact `read`
the URL first. Last week's game bundle stays on the page after the scope moves on (nothing links it); harmless.

## League home (`#NCAAF`, the default view)
Nav: Week N · Rankings · Playoff · Odds · Conferences · Power · Efficiency · Team stats · Trends · Calendar · All teams.
- **Hero + strip**: progress by week; AP No. 1; the unbeaten teams; power #1 (HOUSE MODEL); title favorite (HOUSE MODEL, Kalshi's
  favorite beside); CFP No. 1 (the committee) or the house's No. 1 seed before Nov 3; scoring.
- **Week N**: game cards (every game with an AP team, then the best of the rest by house rating, up to 24): kickoff CT, TV, the
  HOUSE MODEL favorite / line, DraftKings, Kalshi; finals with the closing line, cover and total; the previous week's ranked
  teams beaten by lower-ranked or unranked teams; a link to the full week slate.
- **Rankings**: tabs CFP (from Nov 3) · AP · Coaches · HOUSE MODEL top 25 — rank, record, points, previous, house power,
  P(CFP), Kalshi playoff price.
- **Playoff picture**: if the season ended today — the 2026 bid rules applied to the committee's ranking (or the house proxy
  before Nov 3) with today's conference leaders as champions: byes, first-round pairings at the higher seed, AQ tags, first four
  out; the contenders board (P(CFP) ≥ 0.5%).
- **Odds**: national-title ladder (top 12, Kalshi beside), expected CFP teams by conference, and the full sortable odds board
  (proj W with 10–90 band, bowl, title game, conference champion, CFP, bye, semis, title, Kalshi CFP and title).
- **Conference races** (10 cards, top 6 by title-game odds, Kalshi champion price) · **Power** (all 138: net / offense / defense
  with percentile circles, schedule played and left, résumé vs an elite team, AP) · **Efficiency map** (offense vs defense,
  chips for the AP and house top 25, dots for the rest, tooltips) · **Team stats** (tabs offense / defense / turnovers & discipline
  & kicking, 138 rows, percentile circles) · **Season so far** (favorites SU and ATS, totals, home teams, FCS upsets, one-score
  games, the biggest upset by the line, highest-scoring game, and the HOUSE MODEL scorecard: walk-forward margin error and Brier
  against the closing line) · **Calendar** (the fact sheet with C / R / U tags) · **All teams** by conference.

## Team pages (`#<KEY>`)
Hero (name, conference and division, next game, last season's record and how it ended; record; conference place, AP and CFP
rank; HOUSE MODEL projected regular-season wins on the schedule's own axis with last season's wins marked; the odds line) and the
next-game bug (kickoff CT with UTC, venue, TV, HOUSE MODEL win chance / line / total, DraftKings spread / total / no-vig moneyline,
Kalshi, stakes: CFP odds with a win and a loss, or bowl eligibility when that is what is at stake, game page link) → snapshot
(record splits and points, proj W, power, P(CFP), conference title, last season) → **Standings** (the whole conference, divisions
for the Sun Belt, with HOUSE MODEL projected conference wins, title-game and champion odds, Kalshi) → **Odds** (bowl, 8+ / 10+
wins, unbeaten while it lasts, title game, champion, CFP, bye, each round, title; Kalshi beside where listed; seed distribution
1–12 + out) → **Schedule & results** (every game; finals with the walk-forward house pregame number, the closing line and whether
the team covered; upcoming with house P(win) / line, DraftKings, Kalshi for this week) → **Ratings & percentiles** (power,
offense, defense, schedule cards; 20-bar team profile from ESPN team statistics; computed reads) → **Record check** (Pythagorean
wins at exponent 2.37, rating-expected wins, one-score record, turnover margin, résumé vs an elite team, record vs ranked teams,
FCS games; computed reads) → **Team stats** (every rate with FBS rank and percentile).

## Conference pages (`#C-<CONF>`) · Week views (`#W<n>`, `#WP`) · Game pages (`#G<eid>`)
- Conference: hero and strip (leader, house title favorite, Kalshi favorite, best team, expected CFP teams, non-conference record
  vs FBS / power / FCS) → standings board → title race ladder (sums printed) → this week's games → members' power board.
- Week: header with the 15-week strip (+ P), summary (favorites SU / ATS on finals, ranked upsets; lines posted and 3+ point
  house-market gaps on games to play) → every FBS game by day and slot (Saturday early / afternoon / night / late night; time TBA
  on its Eastern date): kickoff, matchup with ranks and venue, TV, result or HOUSE MODEL (flagged when house and market favor
  different sides), line (closing or DraftKings), against the line (cover, or house − market gap), Kalshi.
- Game (this week and last; ≈112 pages): preview = hero, the line (HOUSE MODEL / DraftKings / Kalshi rows, computed read of the
  gaps), tale of the tape (house ratings and team stats, mirrored percentile bars), matchups (each offense against the other
  defense: Edge / Wall / Strength on strength / Weak on weak), form, stakes; final = hero with score and attendance, linescore and
  every scoring play, team box (paired bars), ESPN win probability chart, forecasts against the result (house pregame
  walk-forward, closing market, Kalshi pre-kickoff, each line's miss), what it means now, the tape.

## QA (both gates mandatory before a publish)
`ncaaf-qa/scripts/qa.py OUT/league-hub-full.html --pull league.json` (structure and placeholders in every inlined view, stamps,
banned sources, the default view rendered at 390/760/1100, pull integrity) and `league_sweep.py OUT` (lint: every fragment
balanced, no leaked None / NaN / undefined, no dead in-page link, home and team sections present, publish list complete; render:
the home, 11 conferences, 16 weeks, all 138 teams and a sample of game pages at 390 / 834 / 1180 — loads, no script errors, no
sideways scroll, every board fits its panel at 834+; interactions: a rankings tab, sorting the odds board both ways, a team link
from the power board then the trail and Back, the picker to a conference). `--dark` repeats in dark mode.
Verified 2026-10-26: qa PASS; sweep PASS 540 views light, 246 dark; 0 dead links.

## Honesty guards
- HOUSE MODEL numbers carry the label and are never blended with DraftKings, the closing line or Kalshi; Kalshi is a second
  market (YES prices on futures, no-vig on games, pre-kickoff once a game starts, thin books tagged); a house–market gap is a
  disagreement, not an edge (the closing market beat the house in the held-out seasons — said on the pages).
- The finals' house number is the walk-forward pregame line (ratings fit only on earlier weeks), labeled "pregame".
- Standings order is the hub's (conference record, then overall, then rating), not the leagues' tiebreakers — the footnote says so.
- "If the season ended today" names its basis (committee ranking or house proxy) every time; a bracket is never called set before
  Selection Day (Dec 6).
- TBD kickoffs print the Eastern date with "TBD"; ESPN team statistics include FCS games (said where shown); red-zone and big-play
  fields are empty in ESPN's college feed and are not shown.
- No player pages, no injuries, no live in-game state (yet): the provenance says so.

## Changelog
- **2026-10-26 — v1.** Owner: "Can you create an NCAA Football Hub Project, following the lead of our MLB, NFL, etc? No player
  cards, just teams." Built on the NFL League Hub's design (its published stylesheet verbatim) with college structure: 138 teams
  grouped by conference, conference pages, a 15-week schedule, the 12-team CFP. First publish: 169 files, 12.2 MB, build of
  Mon Oct 26, 2026 (Week 9; 566 finals). Gates: qa PASS; league_sweep PASS 540 light + 246 dark views; theme self-check PASS.
  Fixed during the build: rank numbers stacked above names in boards; conference-race tables wider than their cards (22 px
  sideways scroll at 1180); week boards wider than their panel at 834 (sub-lines now wrap); TBD kickoffs printed as Friday
  11 PM CT (ESPN parks them at midnight Eastern); the NFL rule `.wm-t i` greyed chip text (overridden).
