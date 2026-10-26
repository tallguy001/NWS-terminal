---
name: ncaaf-sim
description: "The NCAAF suite's HOUSE MODEL (v1.1): opponent-adjusted offense and defense ratings for all 138 FBS teams (a points ridge fit on this season's finals stacked with run, pass and turnover efficiency from team box scores; prior from last season regressed toward the current conference and moved by the preseason AP poll; FCS opponents pooled), game lines, totals and win chances, and a Monte Carlo season simulation with conference title games, a committee-ranking proxy fitted to the CFP committee's final rankings 2014-2025, the 2026 12-team bracket rules, bowl eligibility and next-game stakes; validated walk-forward against the closing market 2016-2026. Use for \"CFB power ratings\", \"house model\", \"who does the model like\", \"model line\", \"CFP odds\", \"playoff chances\", \"conference title odds\", \"projected wins\", \"bowl eligible\", \"what if X beats Y\", \"backtest\", \"calibration\", \"committee proxy\". Requires ncaaf-data-pull. Not for the styled hub (ncaaf-hub) or the NFL (nfl-sim)."
---

# ncaaf-sim

The college football HOUSE MODEL. **No market input anywhere** — game results, team box scores and the preseason AP poll (public
opinion, released before any game) — the market is only the yardstick. Labeled HOUSE MODEL wherever a number is shown. Advisory:
the closing market is the better forecaster (numbers below).

| File | Role |
|---|---|
| `scripts/ncaaf_model.py` | Ratings fit, predictions, walk-forward backtest, calibration. CLI `ratings`, `predict AWAY HOME [--neutral]`, `backtest`, `calibrate` (v1 points grid), `calibrate-v11` (the v1.1 layers; `--loso`, `--write`). Library: `live(season, …)` (fetches this season's team boxes, cached), `chain`, `fit(…, boxes=)`, `prior_from(…, season=)`. |
| `scripts/ncaaf_sim.py` | Season simulation (`season`), a week's house lines beside DraftKings (`week`), the committee-proxy fit (`committee`). Library: `season_sim(season, R, events, reg, n, seed)`, `today_picture(R, events, reg)`. |
| `scripts/build_corpus.py` | History: every FBS game 2014→ with score, ESPN game note and (2019→) the closing line, one gzip per season. |
| `scripts/build_boxes.py` | Team boxes of every FBS v FBS final (ESPN core competitor statistics: plays, yards, first downs, rushes / rushing yards, passes / net passing yards, sacks, third downs, giveaways, penalties, possession). `fetch_box(eid, team)` for the live season. ≈1,550 requests in ≈22 s a season. |
| `scripts/build_polls.py` | The preseason AP poll (points incl. others receiving votes) per season: ESPN core `types/1/weeks/1/rankings/1` from 2025, `types/2/weeks/1` before. |
| `references/corpus/games_<Y>.json.gz` | 2014–2025 (≈10,500 finals; 230 KB in all). Closed seasons never change: add the finished season once a year. |
| `references/corpus/boxes_<Y>.json.gz` | 2014–2025 team boxes (100% of FBS v FBS finals; ≈35 KB a season). |
| `references/corpus/polls_pre.json` | Preseason AP poll 2014–2026 (42–50 teams with points each season). |
| `references/calibration.json` | Production parameters, the held-out report, the `v11` block (selection, training and production fits, v1 vs v1.1, leave-one-season-out), the committee proxy. |
| `references/priors_<Y>.json` | Final ratings of season Y−1 incl. the efficiency layers (the prior source for Y). Rebuilt by `calibrate-v11 --write`. |
| `references/cfp_final.json` | The committee's final ranking each season 2014–2025 (ESPN core API ranking 21). |

## The model (v1.1, 2026-10-26)
- **Points layer** (v1): each team-game score = μ + offense(team) − defense(opponent) ± hfa/2 (home +, away −, neutral 0); weighted
  least squares with a Gaussian prior on every rating (prior strength k = 4 games' worth): early weeks lean on the prior, the
  games take over as they accrue. FCS opponents share a fitted group offense / defense with small individual deviations (2026:
  36 points below an average FBS team); FCS games carry half weight. Total = 2μ + offenses − defenses (totals use this layer only).
- **Prior**: last season's final rating, rho = 0.70 carried over, the rest regressed to the team's CURRENT conference mean (a team
  that moved leagues starts from its new league's level; teams new to the data 3 points below). **v1.1:** then moved to the
  poll regression's estimate of the season-final net: −1.14 + 0.885 × prior net + 4.39 × √(preseason AP points share) + 1.70 if
  the team received votes (fit 2015–2025; the poll cuts the prior's error from 6.35 to 6.20 points), split evenly over
  offense and defense. Unranked teams with a high prior are pulled down the same way ranked teams are pulled up.
- **Efficiency layers** (v1.1): rushing yards per carry, passing yards per dropback (sacks counted) and giveaways, each fitted
  as its own opponent-adjusted offense / defense ridge (k_e 4, carry-over 0.75 to the next season) from FBS v FBS team boxes.
- **The line** = 0.921 × points line + 1.24 × Δ rushing + 0.24 × Δ passing + 1.35 × Δ giveaways, with Weeks 1–4 weights
  1.09 / 0.54 / 0.54 (production fit 2016–2025). The giveaway weight is positive: given the points line it is a turnover-luck
  correction (turnovers barely persist, so a team that scored despite them is better than its points say). The stack is linear
  in each team, so it folds into one rating per team — offense = 0.921 × scoring offense + Σ w × efficiency offense, defense
  likewise, net = offense + defense, home field = 0.921 × 2.5 = 2.3 points — and `R.net / R.o / R.d / R.line` (and the season
  simulation) all read the same v1.1 numbers. FCS teams (no boxes) keep their points ratings.
- **Win chance** = Φ(line / σ): σ = 15.5 points (16.0 in Weeks 1–4), fitted by log loss.
- **What was tried and not shipped** (walk-forward, 2016–2023): every v1 parameter was already at a flat optimum (no setting moved
  margin error more than 0.006); a two-season prior; a line-dependent σ; box-implied points blended into each score (−0.006);
  yards per play, first-down rate, third downs, penalties (dominated by the shipped set).

## Validation (walk-forward: each week priced from only the games before it; FBS v FBS)

Held-out seasons use the v1.1 layers fitted on 2016–2023 only; the closing line from ESPN core odds.

| Seasons | Games | Margin error v1.1 / v1 / closing | Brier v1.1 / v1 / closing |
|---|---|---|---|
| 2016–2023 (training) | 3,646 | 12.72 / 12.83 / 12.31 | 0.1805 / 0.1820 / 0.1729 |
| 2024–2025 (held out) | 1,576 | 12.28 / 12.32 / 11.91 | 0.1842 / 0.1837 / 0.1797 |
| 2026 to date (Weeks 1–8, fully out of sample) | 444 | **11.99 / 12.15** / 11.29 | **0.1767 / 0.1779** / 0.1724 |
| Leave one season out, 2016–2025 (each season predicted with every coefficient fit on the other nine) | 7,560 | v1.1 − v1 = **−0.077**, better in **9 of 10** seasons; Weeks 1–4 −0.14 | better in 9 of 10 (−0.0007) |

Reading: a modest, consistent gain — the 2024–2025 hold-out alone is not significant (−0.037, 95% interval −0.135 to +0.064;
2025 flat), the ten-season check and the live 2026 season agree on the direction. The closing line is still better by ≈0.37
points a game (v1: 0.41). Against the spread the house goes 307–303 on held-out games where it differs from the close by 3+:
noise, not an edge. Same favorite as the close 90% of the time. A run that "beats the closer" is a bug until the leakage walk
proves otherwise. `backtest` runs the production fit (its coefficients saw 2024–2025: 12.27 there — not a held-out number).

## Season simulation (`ncaaf_sim.py season`, ≈2.5 s for 10,000 seasons)
1. Each team's true strength is drawn once per season around its net rating with the fit's own standard error (≈ ±4 points);
   each remaining game's margin = strength difference + the model's home field + noise sized so a single game keeps σ. A
   season's odds therefore run a little flatter than the single-game lines (the NFL hub's recorded finding).
2. Conference title games: the two best conference records (Sun Belt: East and West winners); a two-way tie at the cut goes to
   head-to-head, else simulated strength (the leagues' published tiebreakers are longer — an approximation, labeled). A title
   game ESPN already lists is played as listed; neutral site.
3. Committee proxy: résumé (wins − the wins the 9th-best team would expect against the same schedule) + 0.75 × strength/10 +
   0.75 × conference champion. Refit on the v1.1 ratings to the committee's final rankings 2014–2025: of the committee's top 12
   it names 11.1 on average (9–12 by season); Spearman 0.78 on the top 25.
4. Field (2026–27, verified 2026-10-26): champions of the ACC, Big Ten, Big 12, SEC + the best champion of the American, C-USA,
   MAC, Mountain West, Pac-12, Sun Belt; Notre Dame if top 12; seven at-large; straight seeding; an automatic qualifier outside
   the top 12 takes the lowest seed; byes 1–4; first round on the higher seed's campus, then neutral.
5. Counted per team: regular-season wins (10th/50th/90th), bowl eligibility (6 wins, ≤ 1 FCS win), 8+ / 10+ wins, unbeaten,
   title game, conference title, CFP, bye, each seed, quarterfinal, semifinal, final, title; and for each team's next game the
   CFP / title-game / bowl / conference odds in the seasons it wins vs loses. Integrity: CFP places sum to 12, titles to 1, each
   conference's title-game places to 2 and champions to 1 (ncaaf-qa checks).

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/ncaaf_model.py ratings --top 25                  # fetches this season's team boxes (≈900 requests cold, cached)
python3 scripts/ncaaf_model.py predict WIS IOWA                  # HOUSE MODEL IOWA −6.0, total 34.6, P(IOWA) 65.0% (2026-10-26)
python3 scripts/ncaaf_sim.py week                                # this week: house vs DraftKings
python3 scripts/ncaaf_sim.py season --sims 10000 --json sim.json
python3 scripts/ncaaf_model.py backtest --seasons 2019-2025
# August, once the preseason AP poll is out (the live pull also fetches it into the cache on its own):
python3 scripts/build_polls.py --seasons 2027
# once a year, after the title game (adds the finished season, refits, rewrites calibration + priors):
python3 scripts/build_corpus.py --seasons 2026 && python3 scripts/build_boxes.py --seasons 2026
python3 scripts/ncaaf_model.py calibrate-v11 --train 2016-2024 --test 2025-2026 --loso --write
python3 scripts/ncaaf_sim.py committee --fetch --write
```
`calibrate` (v1) re-runs the points grid from scratch and writes a v1-only calibration; run `calibrate-v11` after it.

## Honesty guards
- HOUSE MODEL numbers carry the literal label and are never averaged with DraftKings, the closing line or Kalshi. The preseason
  AP poll is an input to the prior only (media opinion, not a price); published models (SP+, FPI) are never inputs.
- Injuries, quarterback changes, opt-outs and weather are not modeled; bowl games are fitted but bowls are not simulated
  (opt-outs make them a different sport). The poll prior and the efficiency layer help most in Weeks 1–4; neither knows about
  a quarterback change.
- The committee proxy is a formula fitted to past committees; the committee is people. "If the season ended today" uses the
  committee's own ranking once it exists (from Nov 3) with today's conference leaders as champions.
- Tiebreakers and conference title-game selection are approximations; bowl eligibility ignores waivers and APR backfills.
- If the box fetch fails, the efficiency layers fall back to their priors and the pull logs it (`team boxes: {…}`); the hub's
  Sources line prints the box coverage.

## Changelog
- **2026-10-26 — v1.1 (owner: "fine tune the model").** Preseason AP poll prior + box-score efficiency stack (run, pass,
  giveaways); prior strength 3 → 4; σ 15.5 / 16.0; committee proxy refit (11.0 → 11.1 of 12). Box corpus 2014–2025 and poll
  corpus 2014–2026 added. Validation table above; v1 numbers kept beside for comparison.
- **2026-10-26 — v1.** Corpus 2014–2025 built from ESPN (scores 12 seasons, closing lines on 5,934 finals 2019–2025);
  calibrated on 2016–2023, held out 2024–2025 (12.32 vs the close's 11.91); committee proxy fitted on 12 final rankings.
  Open items: ncaaf-suite-audit `references/open-items.md`.
