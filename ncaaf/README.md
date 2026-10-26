# NCAAF suite — the college football hub project

A college football (FBS) skill suite in the same shape as the MLB / NFL / NBA / NHL / EPL suites, teams only (no player cards).

| Skill | What it does |
|---|---|
| `skills/ncaaf-data-pull` | ESPN college-football feeds (scoreboards, closing lines, standings, polls, CFP ranking, team stats, game summaries), the FBS registry, team-color themes, Kalshi, the season-phase gate, the verified 2026 fact sheet |
| `skills/ncaaf-sim` | The HOUSE MODEL: offense/defense ratings, game lines and win chances, the season simulation (conference title games, the 12-team CFP, bowl eligibility, stakes), corpus 2014–2025, calibration and backtest |
| `skills/ncaaf-hub` | The NCAAF League Hub artifact: league home, 138 team pages, 11 conference pages, 15 weeks, game pages; render gate |
| `skills/ncaaf-qa` | Pre-delivery gate (structure, stamps, sources, layout, pull integrity) |
| `skills/ncaaf-team-card` | Chat team deep dive with a verdict |
| `skills/ncaaf-operator` | Router and rulebook (precedence, depth, verified facts, output contract) |
| `skills/ncaaf-suite-audit` | Maintenance: certification, codification, weekly and annual walks; changelog and open items |
| `NCAAF_WORKSPACE.md` | Project instructions for an "NCAAF" project |
| `dist/*.skill` | The packaged skills, ready to upload |

Published League Hub: https://claude.ai/artifact/3WewjztwCbPeZYbkdv9Dox (private until shared).

## Build it

```bash
export PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
python3 skills/ncaaf-hub/scripts/hub_pull.py --league --json league.json        # ≈30 s cold
python3 skills/ncaaf-hub/scripts/hub_build.py league --pull league.json --out-dir OUT
python3 skills/ncaaf-qa/scripts/qa.py OUT/league-hub-full.html --pull league.json
python3 skills/ncaaf-hub/scripts/league_sweep.py OUT
```
Then publish `OUT/index.html` with every file in `OUT/publish-files.json` to the fixed URL (see `skills/ncaaf-hub/SKILL.md`).
Python 3.11+, numpy, and (for the gates) the Python Playwright binding matching the installed Chromium.
