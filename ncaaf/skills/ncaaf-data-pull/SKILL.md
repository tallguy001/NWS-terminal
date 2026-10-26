---
name: ncaaf-data-pull
description: "The NCAAF suite's data layer: deterministic, cached pulls from ESPN's college-football feeds (FBS scoreboards with kickoffs, TV, venues and DraftKings lines; closing lines on every final from ESPN's core odds; computed conference standings checked against ESPN; AP, Coaches and CFP rankings; ESPN team statistics for all 138 FBS teams; game summaries), the FBS registry and conferences, team-color themes, the season-phase gate and Kalshi's college-football markets (games, playoff, title, conference champions). Use for any college football number: \"CFB scores\", \"college football slate\", \"who plays this week\", \"AP poll\", \"CFP rankings\", \"Big Ten standings\", \"the line on Iowa\", \"closing line\", \"box score\", \"what week is it\", \"Kalshi CFP odds\". Required sibling of ncaaf-sim, ncaaf-hub and ncaaf-qa. Not for ratings or odds (ncaaf-sim) or the styled hub (ncaaf-hub); not for NFL (nfl-data-pull) or Wisconsin high school (wiaa-fb)."
---

# ncaaf-data-pull

The college port of nfl-data-pull / nhl-data-pull: every number the NCAAF suite prints comes through these scripts, cached,
stamped, and never typed by hand. Season label = the kickoff year (2026 = the 2026–27 season).

| Script | Role |
|---|---|
| `scripts/ncaaf_common.py` | Cached HTTP (`$NCAAF_CACHE`, default `/tmp/ncaaf_cache`; `ttl=None` keeps finals forever; a failed GET falls back to a stale copy and says so), Central time, half-up formatting with a true minus, lines and moneylines, sibling-skill resolution. |
| `scripts/ncaaf_data.py` | ESPN fetchers + CLI (below). Identity: the ESPN team id is canonical; `key` = abbreviation without punctuation (TA&M → TAM, M-OH → MOH) is the hub route. FCS opponents are carried with no route. |
| `scripts/ncaaf_theme.py` | Team colors → page themes (the nfl_theme API and contrast rules: WCAG AA ≥ 4.5:1 derived, never hand-set). Palette = ESPN's `color` / `alternateColor`; a light gold primary with a dark alternate flips (Purdue, Colorado, Wake Forest, Missouri, Vanderbilt, Arizona State read dark-and-gold); `FIX` adds Georgia Tech's navy. `python3 ncaaf_theme.py` = self-check (139 themes, PASS). |
| `scripts/ncaaf_kalshi.py` | Kalshi's public Trade API (no key, read-only): KXNCAAFGAME (games), KXNCAAF (title), KXNCAAFPLAYOFF, the ten conference-champion series. Paired by team NAME (Kalshi's codes differ: MTU = MTSU, JVST = JXST, MOSU = MOST), then code, plus the Eastern date ±1 day. |
| `scripts/phase.py` | Season-phase gate: `--gate hub|gameday|backtest` exits 3 when dormant (gameday also needs an FBS game today). |
| `references/teams_<Y>.json` | FBS registry snapshot (membership, divisions, colors) — `ncaaf_data.py registry --write` each August and after realignment. |
| `references/season_<Y>_facts.json` | Verified fact sheet (tags C / R / U, sources named): FBS membership, last season's champion, the CFP format, seeding and calendar, the rules the model uses. Rebuilt by hand from verified sources each season. |

## CLI

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/ncaaf_data.py clock                      # season, phase, ESPN's week calendar
python3 scripts/ncaaf_data.py slate [--week N] [--top]   # a week's FBS games (Central kickoffs, TV, ranks, DraftKings or result)
python3 scripts/ncaaf_data.py standings [--conf B1G]     # conference standings from the games, checked against ESPN
python3 scripts/ncaaf_data.py rankings [--poll ap|usa|cfp]
python3 scripts/ncaaf_data.py team WIS                   # schedule and results with lines
python3 scripts/ncaaf_data.py game 401871058             # linescore, team box, scoring plays, closing line
python3 scripts/ncaaf_data.py lines [--week N]           # closing (finals) or current DraftKings lines
python3 scripts/ncaaf_data.py registry [--write]
python3 scripts/ncaaf_data.py verify [--strict]          # probes every feed; --strict exits 1 on a failure
python3 scripts/ncaaf_kalshi.py [--week N]               # what Kalshi attaches to a week's games + the futures
python3 scripts/phase.py [--gate hub]
```
Every command takes `--season Y` and `--json`.

## Feeds (verified 2026-10-26)

| Feed | Endpoint | Notes |
|---|---|---|
| Scoreboard | `site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&dates=Y&seasontype=2&week=N&limit=400` | groups=80 = every game with an FBS team (FCS opponents included). Weeks come from the league `calendar` (2026: 15 regular weeks, then Bowls `seasontype=3 week=1` and CFP `week=999`). **DraftKings odds appear only before kickoff** — a final carries none. `timeValid: false` = kickoff unset (parked at midnight Eastern: print the Eastern date and "TBD"). `conferenceCompetition` marks conference games. |
| Closing lines | `sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{id}/competitions/{id}/odds` | 7–17 KB per game; DraftKings (2026), ESPN BET (2024–25), consensus (≤2023). `spread` is the HOME line (negative = home favored); skip any provider named "… Live Odds". |
| Standings | `site.api.espn.com/apis/v2/sports/football/college-football/standings?group=80&season=Y` | Membership (138 teams in 2026) and ESPN's records (`overall`, `vs. Conf.`). ESPN's ORDER is unreliable mid-season (UCLA 5–0 listed above Ohio State 4–0 above Indiana 4–1 on 2026-10-26): the suite orders by its own conference record and uses ESPN only as a cross-check. |
| Rankings | `…/college-football/rankings` | `ap`, `usa` (AFCA Coaches), and the CFP committee ranking from its first release (2026: Tue Nov 3). Past final CFP rankings: core API `seasons/Y/types/2/weeks/W/rankings/21`. |
| Team stats | `…/teams/{id}/statistics?season=Y` | `results.stats` = {categories}, `results.opponent` = a bare LIST of categories. Red-zone and big-play fields are empty for college (0.0) — never shown. Totals include FCS games. |
| Game summary | `…/summary?event={id}` | ~600 KB: box, scoring plays, drives, ESPN win probability, pickcenter. Fetched only for game pages, kept forever once final. |
| Kalshi | `api.elections.kalshi.com/trade-api/v2` | prices in `*_dollars` fields; 0.35 s pacing with backoff on 429. |

## Honesty rules (binding for every consumer)
- One source per number: scores, kickoffs and TV from ESPN's scoreboard; finals' lines from the core odds endpoint; standings
  computed from the games (a disagreement with ESPN's record is logged, never silently resolved).
- A game past kickoff is "Under way"; a game with `timeValid: false` reads "TBD" on its Eastern date, never a fake late kickoff.
- Kalshi is a second market: never averaged with DraftKings, never blended with the HOUSE MODEL; a started game shows only the
  pre-kickoff price (last hourly candle ending at or before kickoff, stepped back when that hour moved 20¢); thin books tagged.
- Aggregator blocklist (heavy.com class) applies to any search that supplements these feeds.

## Changelog
- **2026-10-26 — v1.** Owner: "create an NCAA Football Hub Project, following the lead of our MLB, NFL, etc. No player cards,
  just teams." Built and verified against live data: 138 FBS teams in 11 groups, 949 events (566 finals) for 2026, closing lines
  on 566/566 finals, standings agree with ESPN's records 138/138, team statistics 138/138, Kalshi 112/112 games of this week and
  last paired (0 unmatched) plus 12 futures events; `verify` 7/7; theme self-check PASS (139 themes).
