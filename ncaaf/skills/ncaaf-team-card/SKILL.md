---
name: ncaaf-team-card
description: "Produce the analytical college football team card in chat for any FBS team: record and splits against the underlying margins (HOUSE MODEL net, offense and defense ratings with FBS ranks), Pythagorean and rating-expected wins, one-score record and turnover margin, schedule played and remaining, the team-stat profile with percentiles, conference race and CFP odds from the house season simulation beside Kalshi and the polls, the next game with house line vs DraftKings, and a mandatory verdict (Contender or Pretender, Better or Worse than the house projection) with its weighting and an honest range. Use for \"state of [team]\", \"team card [team]\", \"is [team] for real\", \"can [team] make the playoff\", \"what does [team] need\", \"[team] CFP chances\", \"deep dive on [team]\" in college football. Teams only (no player cards). Not for raw lookups (ncaaf-data-pull), the styled page (ncaaf-hub) or NFL teams."
---

# ncaaf-team-card

The chat sibling of a hub team page (the nhl-team-card / mlb-team-card shape, college edition). **Default team: Wisconsin**
(the house team, owner 2026-10-26) when no team is named — "my team", "the Badgers", "how are we doing". No player cards in this suite:
a question about one player gets the team context plus a plain search answer, labeled as such.

## Steps
1. **Data pass** (scripts beat search for every number they carry):
   ```bash
   export PYTHONDONTWRITEBYTECODE=1
   python3 <ncaaf-data-pull>/scripts/ncaaf_data.py team KEY            # schedule, results, lines
   python3 <ncaaf-data-pull>/scripts/ncaaf_data.py standings --conf CONF
   python3 <ncaaf-data-pull>/scripts/ncaaf_data.py rankings
   python3 <ncaaf-sim>/scripts/ncaaf_model.py ratings --top 138         # net / offense / defense, ranks
   python3 <ncaaf-sim>/scripts/ncaaf_sim.py season --sims 10000 --json /tmp/sim.json
   python3 <ncaaf-data-pull>/scripts/ncaaf_kalshi.py                    # this week's games + futures
   ```
   Faster when a hub pull exists from today: read `league.json` (ratings, sim, teamrec, stats, kalshi) — same numbers the
   hub prints. Never mix a fresh pull with an older hub's numbers in one answer.
2. **Record vs reality** — W–L beside Pythagorean wins (exponent 2.37) and rating-expected wins; one-score record (≤ 8 points);
   turnover margin; record vs AP-ranked teams; FCS games. A record more than ~1.2 wins ahead of the points is luck until shown
   otherwise.
3. **Quality** — HOUSE MODEL net, offense, defense with FBS ranks (138) and how far each moved from the preseason prior; the
   team-stat profile (yards per play both ways, run and pass efficiency, third downs, sacks, takeaways) with percentiles; state
   the sample (games played; early-season ratings lean on the prior).
4. **Schedule** — strength played and remaining (mean opponent house net, rank of 138), the remaining games with the house win
   chance each, the toughest left.
5. **Race** — the two-number rule (ncaaf-operator §1): games behind the conference title-game line (or ahead of the first team
   outside it) with conference games left, and places inside / outside the 12-team cut in the committee's ranking (the house proxy
   before Nov 3) — the hub's team page prints both as "Two numbers." Then P(title game), P(champion), Kalshi's champion price
   beside; P(CFP), P(bye), the seed range, Kalshi's playoff price, the AP / CFP rank.
6. **Next game** — kickoff CT (UTC), venue, TV; HOUSE MODEL line / total / win chance vs DraftKings and Kalshi (never blended);
   the stakes from the simulation (CFP odds with a win and with a loss).
7. **Verdict** (mandatory): weighting rationale first (how much record vs margins vs schedule), an honest range (the 10th–90th
   win band), then the labels: **Contender | Pretender** (for the CFP if P(CFP) ≥ 10%, else for the conference title) and
   **Better | Worse than the projection** (where the rest of the season lands against the house mean, and why).

## Output contract
Freshness stamp with the build or fetch time; CT first with UTC in parentheses; tables for data, prose for meaning; HOUSE MODEL
numbers labeled; market numbers name DraftKings (via ESPN) or Kalshi; "Under way" never "tonight" for a started game; end with the
verdict. Small samples said beside rates (a team's per-play rates after four games are noise; the ratings carry the prior).
