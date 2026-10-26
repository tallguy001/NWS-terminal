# NCAAF suite — changelog

## 2026-10-26 — v1 (founding build)

Owner request: "Nothing in this repo. Can you create an NCAA Football Hub Project, following the lead of our MLB, NFL, etc? No
player cards, just teams."

Built (all executed and inspected this session, live 2026 data, Week 9):
- **ncaaf-data-pull** — ESPN fetchers with a file cache, the FBS registry (138 teams, 11 groups), team themes (139, contrast
  self-check PASS), Kalshi reader (games + 12 futures events), phase gate, the verified 2026 fact sheet. `verify` 7/7.
- **ncaaf-sim** — corpus 2014–2025 (≈10,500 finals; closing lines on 5,934 finals 2019–2025); offense/defense ridge ratings;
  calibrated 2016–2023, held out 2024–2025: margin error 12.32 vs the closing line's 11.91, Brier 0.1837 vs 0.1797 (bootstrap
  interval of the gap [+0.0002, +0.0076]: the market is better); committee proxy top-12 overlap 11.0 of 12 (2014–2025); season
  simulation 10,000 seasons in ≈2.5 s with exact sums.
- **ncaaf-hub** — the League Hub on the NFL hub's stylesheet: home, 138 team pages, 11 conference pages, 16 week views, 112 game
  pages; published https://claude.ai/artifact/3WewjztwCbPeZYbkdv9Dox (169 files, 12.2 MB). Gates: ncaaf-qa PASS; league_sweep
  PASS 540 views light, 246 dark, 0 dead links.
- **ncaaf-qa**, **ncaaf-team-card**, **ncaaf-operator**, **ncaaf-suite-audit**, the workspace doc `NCAAF_WORKSPACE.md`.

Learned (codified in the owning skills):
- ESPN's college scoreboard drops odds at kickoff; finals' lines come from the core odds endpoint (home-perspective `spread`;
  skip "… Live Odds" providers). ESPN BET was the 2024–25 provider, DraftKings from 2026.
- ESPN team statistics: `results.opponent` is a bare list of categories (not `{categories: …}`); red-zone and big-play fields are
  empty (0.0) for college.
- ESPN's standings ORDER is unreliable mid-season; records agree with the games 138/138, so the hub orders by its own rule.
- Unset kickoffs (`timeValid: false`) sit at midnight Eastern: print the Eastern date with TBD.
- Kalshi's college codes differ from ESPN's (MTU/MTSU, JVST/JXST, MOSU/MOST): pair by team name, then code.
- The NFL CSS rule `.wm-t i` also greys the chip text inside the matchup cell; NCAAF overrides it (worth fixing in nfl-hub).
- qa.py must scan the views inlined in `lg-data`, or a placeholder inside any view passes.

Not done (open-items.md): live scores / gameday push, the daily scheduled task (owner approval), house team, on-demand scouting
reports, Kalshi ladders, exact conference tiebreakers, QB/injury adjustment, the 2027 CFP format decision.

Certified 2026-10-26 from the packaged copies (unzipped to a fresh directory): verify 7/7, theme PASS, backtest 2024–2025 reproduces 12.323 / 11.914, hub pull → build → qa PASS → league_sweep PASS. Script md5s:

```
  11fbca65c469913326bba1e7a6b0a72a  ncaaf-data-pull/scripts/ncaaf_common.py
  9d8ed7170d5370f205ac93044b16fd63  ncaaf-data-pull/scripts/ncaaf_data.py
  c0c4b28dfa5598636bf6563ec0a67ae4  ncaaf-data-pull/scripts/ncaaf_kalshi.py
  c32451deb1d62d21ffba1f29c77cc1c2  ncaaf-data-pull/scripts/ncaaf_theme.py
  bf182bcf3fa97002739348b2e57d37b7  ncaaf-data-pull/scripts/phase.py
  5e3ee05a9cf390ce49589f785ec58ada  ncaaf-hub/scripts/hub_build.py
  26bcb8dd245509b2761de8aa69897827  ncaaf-hub/scripts/hub_common.py
  126ed270924c56bc8defb84e03e08563  ncaaf-hub/scripts/hub_ctx.py
  c6921a106d5d9f96d40d5d6f2d53f12d  ncaaf-hub/scripts/hub_pull.py
  d22d2902b32399e3d16b3517479072f1  ncaaf-hub/scripts/league_shell.py
  a440ae995b71bc882fbd40e3a24c02c0  ncaaf-hub/scripts/league_sweep.py
  df5275cef6119e1ad7cc35f48b19af12  ncaaf-hub/scripts/ncaaf_css.py
  6db6680cfda7db2a9a35357c214b0f4b  ncaaf-hub/scripts/pages_conf.py
  ef6e40f07fb22ea360b91ebe0d5bef1d  ncaaf-hub/scripts/pages_game.py
  0d43d8d71921bc86930ca94e7a295c4f  ncaaf-hub/scripts/pages_landing.py
  971862d29b433f26e36aad170e2a6805  ncaaf-hub/scripts/pages_team.py
  4e6e0c854f5bb6bbd0e3376010ad0a71  ncaaf-hub/scripts/pages_week.py
  65ae5f07d40f9d6b3bd84df87e5a1f4c  ncaaf-qa/scripts/qa.py
  7fdabbbfedd2ca261cc2830cd67f0c70  ncaaf-sim/scripts/build_corpus.py
  1c1a8d6d85c6c8d9c262ad11c73abd0e  ncaaf-sim/scripts/ncaaf_model.py
  e637e90034b5b3830d1d0b66c1e695c0  ncaaf-sim/scripts/ncaaf_sim.py
```
