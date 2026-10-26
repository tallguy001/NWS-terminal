---
name: ncaaf-qa
description: "Pre-delivery gate for every NCAAF workspace HTML or markdown product (the NCAAF League Hub, any college football page or report): tag balance and leftover placeholders in the page and in every inlined view, stale season language, banned aggregator sources, HOUSE MODEL labelling, a freshness stamp, a Chromium layout pass at 390/760/1100 px, and pull integrity (130+ FBS teams rated and simulated, CFP places sum to 12, titles to 1, each conference's title-game places to 2 and champions to 1, nested round odds, closing lines on the finals, a started game carries only Kalshi's pre-kickoff price, ESPN's records agree). Use before publishing any college football product, or on \"QA the CFB page\", \"check the NCAAF hub\". Exit 1 blocks delivery."
---

# ncaaf-qa

```bash
python3 scripts/qa.py FILE [--pull PULL.json] [--date YYYY-MM-DD] [--no-render] [--json] [--widths 390,760,1100]
```
Exit 0 = PASS · 1 = FAIL (blocking: fix before delivery) · 2 = PASS with warnings (acceptable when each warning is explained).

Checks: structure (unbalanced tags; TODO / `{{…}}` / undefined / NaN / `[object Object]`; elements that are only None/null/nan;
**every view inlined in a League Hub page's `lg-data` payload is scanned too**, so `league-hub-full.html` covers all 166 views) ·
season (dates in `SEASON_DATES`, re-verified at each season audit: 2026 Week 1 Aug 22, first CFP ranking Nov 3, Selection Day
Dec 6, title game Jan 25, 2027; a bracket called set before Selection Day fails) · sources (heavy.com, sportskeeda, clutchpoints,
yardbarker and their class are banned) · stamps (a "Built … CT" stamp, warned past 36 h; the literal HOUSE MODEL exists; no
market word directly inside a HOUSE MODEL label) · layout (rendered in Chromium at each width: no page-level sideways scroll, no
JS errors, no client-side placeholders; static fallback when no browser, and the report says so) · integrity (`--pull`: team
count, every team rated and simulated, odds in [0,1] and nested (title ≤ final ≤ semis ≤ quarterfinal ≤ CFP), the sums above,
FBS ratings centered, closing lines on ≥ 95% of finals (warn), Kalshi game prices in (0,1) and pre-kickoff once a game is under
way or final with a stamp at or before kickoff (FAIL), a failed Kalshi read or ESPN record disagreement warns).

The League Hub is a split page: `qa.py` renders only the default view; ncaaf-hub's `league_sweep.py` is the mandatory render
gate for every view, the interactions and the dead-link lint. Playwright uses `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`; never
run `playwright install`.

## Changelog
- **2026-10-26 — v1.** Built with ncaaf-hub v1. Verified: PASS on the first build; negative tests — a P(CFP) of 1.7 (range and
  the 12-place sum), a final priced from the current Kalshi book, and a NaN planted inside an inlined view each FAIL (the last
  one was missed until the payload scan was added).
