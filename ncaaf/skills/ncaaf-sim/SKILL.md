---
name: ncaaf-sim
description: "The NCAAF suite's HOUSE MODEL: opponent-adjusted offense and defense points ratings for all 138 FBS teams (ridge fit on this season's finals, last season regressed toward the current conference as the prior, FCS opponents pooled), game lines, totals and win chances, and a Monte Carlo season simulation with conference title games, a committee-ranking proxy fitted to the CFP committee's final rankings 2014-2025, the 2026 12-team bracket rules, bowl eligibility and next-game stakes; validated walk-forward against the closing market 2016-2025. Use for \"CFB power ratings\", \"house model\", \"who does the model like\", \"model line\", \"CFP odds\", \"playoff chances\", \"conference title odds\", \"projected wins\", \"bowl eligible\", \"what if X beats Y\", \"backtest\", \"calibration\", \"committee proxy\". Requires ncaaf-data-pull. Not for the styled hub (ncaaf-hub) or the NFL (nfl-sim)."
---

# ncaaf-sim

The college football HOUSE MODEL. Results only — the market is the yardstick, never an input — and labeled HOUSE MODEL
wherever a number is shown. Advisory: the closing market is the better forecaster (numbers below).

| File | Role |
|---|---|
| `scripts/ncaaf_model.py` | Ratings fit, predictions, the walk-forward backtest, the calibration grid. CLI `ratings`, `predict AWAY HOME [--neutral]`, `backtest`, `calibrate`. |
| `scripts/ncaaf_sim.py` | Season simulation (`season`), a week's house lines beside DraftKings (`week`), the committee-proxy fit (`committee`). Library: `season_sim(season, R, events, reg, n, seed)`, `today_picture(R, events, reg)`. |
| `scripts/build_corpus.py` | History: every FBS game 2014→ with score, ESPN game note and (2019→) the closing line, one gzip per season. |
| `references/corpus/games_<Y>.json.gz` | 2014–2025 (≈10,500 finals; 230 KB in all). Closed seasons never change: add the finished season once a year (after the title game). |
| `references/calibration.json` | Chosen parameters, training (2016–2023) and held-out (2024–2025) reports, the committee proxy's parameters and grades. |
| `references/priors_<Y>.json` | Final ratings of season Y−1 (the prior source for Y). Rebuilt by `calibrate --write`. |
| `references/cfp_final.json` | The committee's final ranking each season 2014–2025 (ESPN core API ranking 21). |

## The model
- Each team-game score = μ + offense(team) − defense(opponent) ± hfa/2 (home +, away −, neutral 0). Net = offense + defense =
  points better than an average FBS team on a neutral field. Line = net(home) − net(away) + hfa (none at a neutral site).
  Total = 2μ + offenses − defenses.
- Weighted least squares with a Gaussian prior on every rating (prior strength `k` = games' worth): early weeks lean on the prior,
  the games take over as they accrue. FCS opponents share a fitted group offense / defense with small individual deviations
  (2026: the FCS group sits 36 points below an average FBS team); FCS games carry half weight.
- Prior: last season's final rating, `rho` = 0.70 carried over, the rest regressed to the team's CURRENT conference mean of
  last season's ratings (a team that moved leagues starts from its new league's level); teams new to the data start 3 points
  below their conference.
- Win chance = Φ(line / σ): σ = 15.5 points (15.0 in Weeks 1–4), fitted walk-forward by log loss.
- Chosen by coordinate descent on 2016–2023 margin error: hfa 2.5, k 3/3, k_fcs 3, w_fcs 0.5, no blowout cap, no time decay.

## Validation (walk-forward: each week priced from only the games before it; FBS v FBS with a closing line)

| Seasons | Games | Margin error house / closing | Brier house / closing | Brier gap, 95% bootstrap |
|---|---|---|---|---|
| 2016–2023 (training) | 3,646 | 12.83 / 12.31 | 0.1820 / 0.1729 | +0.0090 [+0.0063, +0.0112] |
| 2024–2025 (held out) | 1,576 | 12.32 / 11.91 | 0.1837 / 0.1797 | +0.0039 [+0.0002, +0.0076] |
| 2025 alone | 806 | 12.16 / 11.83 | 0.1772 / 0.1754 | +0.0017 [−0.0035, +0.0068] (no measurable difference) |
| 2026 to date (live, the hub's scorecard) | 444 | 12.15 / 11.29 | 0.1779 / 0.1724 | — |

Against the spread the house goes 335–317 (51.4%) on held-out games where it differs from the close by 3+ points: noise, not
an edge. Same favorite as the closing line 89% of the time. A run that "beats the closer" is a bug until the leakage walk
(nfl-suite-audit's rule) proves otherwise.

## Season simulation (`ncaaf_sim.py season`, ≈2.5 s for 10,000 seasons)
1. Each team's true strength is drawn once per season around its net rating with the fit's own standard error (≈ ±4 points);
   each remaining game's margin adds noise sized so a single game keeps σ. A season's odds therefore run a little flatter than
   the single-game lines (the NFL hub's recorded finding; the hub prints game lines from the single-game model).
2. Conference title games: the two best conference records (Sun Belt: East and West winners); a two-way tie at the cut goes to
   head-to-head, else simulated strength (the leagues' published tiebreakers are longer — an approximation, labeled). A title
   game ESPN already lists is played as listed; neutral site.
3. Committee proxy: résumé (wins − the wins the 12th-best team would expect against the same schedule) + 1.25 × strength/10 +
   0.5 × conference champion. Fitted to the committee's final rankings 2014–2025: of the committee's top 12 it names 11.0 on
   average (9–12 by season); Spearman 0.80 on the top 25.
4. Field (2026–27, verified 2026-10-26): champions of the ACC, Big Ten, Big 12, SEC + the best champion of the American, C-USA,
   MAC, Mountain West, Pac-12, Sun Belt; Notre Dame if top 12; seven at-large; straight seeding; an automatic qualifier outside
   the top 12 takes the lowest seed; byes 1–4; first round on the higher seed's campus, then neutral.
5. Counted per team: regular-season wins (10th/50th/90th), bowl eligibility (6 wins, ≤ 1 FCS win), 8+ / 10+ wins, unbeaten,
   title game, conference title, CFP, bye, each seed, quarterfinal, semifinal, final, title; and for each team's next game the
   CFP / title-game / bowl / conference odds in the seasons it wins vs loses. Integrity: CFP places sum to 12, titles to 1, each
   conference's title-game places to 2 and champions to 1 (ncaaf-qa checks).

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/ncaaf_model.py ratings --top 25
python3 scripts/ncaaf_model.py predict WIS IOWA                  # HOUSE MODEL IOWA −3.2, total 34.1, P(IOWA) 58.1% (2026-10-26)
python3 scripts/ncaaf_sim.py week                                # this week: house vs DraftKings
python3 scripts/ncaaf_sim.py season --sims 10000 --json sim.json
python3 scripts/ncaaf_model.py backtest --seasons 2019-2025
# once a year, after the title game (adds the finished season, refits, rewrites calibration + priors):
python3 scripts/build_corpus.py --seasons 2026 && python3 scripts/ncaaf_model.py calibrate --train 2016-2024 --test 2025-2026 --write
python3 scripts/ncaaf_sim.py committee --fetch --write
```

## Honesty guards
- HOUSE MODEL numbers carry the literal label and are never averaged with DraftKings, the closing line or Kalshi.
- Injuries, quarterback changes, opt-outs and weather are not modeled (results only); bowl games are fitted but bowls are not
  simulated (opt-outs make them a different sport).
- The committee proxy is a formula fitted to past committees; the committee is people. "If the season ended today" uses the
  committee's own ranking once it exists (from Nov 3) with today's conference leaders as champions.
- Tiebreakers and conference title-game selection are approximations; bowl eligibility ignores waivers and APR backfills.

## Changelog
- **2026-10-26 — v1.** Corpus 2014–2025 built from ESPN (scores 12 seasons, closing lines on 5,934 finals 2019–2025);
  calibrated on 2016–2023, held out 2024–2025 (table above); committee proxy fitted on 12 final rankings; 2026 live: 566 finals,
  326 games to play, sums exact. Open items: ncaaf-suite-audit `references/open-items.md`.
