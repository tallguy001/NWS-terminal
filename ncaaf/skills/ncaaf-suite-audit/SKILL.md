---
name: ncaaf-suite-audit
description: "Maintain the NCAAF skill suite (ncaaf-data-pull, ncaaf-sim, ncaaf-hub, ncaaf-qa, ncaaf-team-card, ncaaf-operator and the NCAAF workspace doc): install certification, codification of session learnings into the owning skill, drift checks between the routing table and the installed suite, the weekly in-season freshness walk and the annual offseason walk (corpus, calibration, committee proxy, registry, fact sheet). Use whenever the user says \"audit the CFB suite\", \"audit the NCAAF project\", \"codify\", \"are the college skills current\", \"what's stale\", or at the end of any college football session that produced a durable learning (an endpoint that changed, a renamed feed field, a script bug fixed, a calibration adjusted, realignment). This is process maintenance, not a football product."
---

# ncaaf-suite-audit

The suite stays trustworthy only if learnings land in files, not scrollback. Model: audit → change list → codify → repackage →
present → user re-saves. Durable log: `references/changelog.md`. Standing ledger: `references/open-items.md` (owner, first
raised, closing condition) — read at the start of every audit, re-dated at the end.

## Binding rules (the NFL suite's, unchanged)
1. **"Shipped" means executed and inspected.** A changelog entry claims a capability only after the command ran and its output was
   looked at. Docs-without-code is logged as "contract updated, implementation pending". Docs and scripts package together.
2. **Name the copy and its vintage.** Say which copy was read (live probe vs bundled reference) and when.
3. **Derived rankings are generated, never remembered.** Any superlative is recomputed from the current pull with its through-week.
4. **Stale beats wrong.** A source not reachable this session is "unverified as of <date>", never memory.

## Install certification (every fresh install or re-save; probe the INSTALLED copy)
1. `ncaaf_data.py verify --strict` → 7/7 (calendar, scoreboard with DraftKings odds, standings 130+ teams, rankings, a closing
   line, a game summary, team statistics). `ncaaf_theme.py` → PASS. `phase.py` prints a phase line.
2. `ncaaf_kalshi.py` → this week's games paired with 0 unmatched FBS games (unnamed FCS-only markets are expected).
3. `ncaaf_model.py backtest --seasons 2024-2025` reproduces calibration.json's held-out numbers (margin error 12.32 vs 11.91);
   `ncaaf_sim.py season` prints CFP sum 12.0 and title sum 1.0.
4. ncaaf-hub: pull → build → `qa.py` PASS → `league_sweep.py` PASS light and `--dark` (exit 2 = no browser = NOT certified; a
   cloud container needs `pip install --break-system-packages playwright==<the Node package's version>`).
5. Record the script md5s in the changelog entry; a re-save whose md5s differ is a new build: certify again.
Harness notes: `PYTHONDONTWRITEBYTECODE=1` (and `python3 -B` with `-I`); before packaging, `find <build> -name __pycache__` must
print nothing.

## The walks
1. **Feed verification** — `verify --strict`; on a ❌ read ncaaf-data-pull's Feeds table and probe the endpoint; field renames
   (ESPN moved team-stat opponents to a bare list once already) are fixed in the script and the table together.
2. **Codification sweep** — anything learned the hard way goes into the owning skill (script + SKILL.md). The test: would a cold
   session repeat today's mistake?
3. **Drift checks** — the operator's routing table names a real skill or command on every row; trigger namespaces stay disjoint
   from nfl-* (pro football) and wiaa-fb (Wisconsin high school); cross-references resolve.
4. **In-season freshness walk (weekly, Tuesday)** — `clock`; last week's finals all carry closing lines (`lines --week N-1`);
   the AP poll's week advanced; from Nov 3 the CFP ranking is read (`rankings --poll cfp`) and the hub's playoff picture says
   "committee"; the hub's scorecard (Trends) still shows the closing line ahead — if the house ever leads over a full month,
   run the leakage walk (nfl-suite-audit walk 5: read `chain`/`fit` for look-ahead, then a paired bootstrap) before believing it.
5. **Annual walk (after the title game, before August)** — add the finished season to the corpus (`build_corpus.py --seasons Y`),
   recalibrate (`ncaaf_model.py calibrate --train … --test … --write`), refit the committee proxy (`ncaaf_sim.py committee --fetch
   --write`), rebuild the registry (`ncaaf_data.py registry --write` once ESPN shows the new season's membership), rewrite
   `season_<Y>_facts.json` from verified sources (CFP format — the 2027 expansion decision —, dates, champions), update qa.py's
   SEASON_DATES, and re-run certification.

## Packaging
Copy each skill to a writable path, edit, then `python3 <skill-creator>/scripts/package_skill.py <folder> <dist>` → present the
`.skill` files with the updated workspace doc. Preserve skill names exactly.
