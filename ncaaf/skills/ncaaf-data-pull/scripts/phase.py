#!/usr/bin/env python3
"""phase.py — the NCAAF suite's season-phase gate (the MLB / NBA / NHL phase.py contract).

    python3 phase.py                    one line: season, phase, week, and which products are live
    python3 phase.py --gate PRODUCT     exit 0 = run; exit 3 = dormant (prints the one line to say instead)
    python3 phase.py --json

Phases (ESPN's league calendar for the season, Central time): preseason (before Week 1) · regular · championship (the last
two regular weeks: conference title games and Army–Navy) · postseason (bowls and the CFP) · offseason (after the title game).

Products and when they run:
  hub        the NCAAF League Hub — every phase (preseason = projection mode, offseason = final mode)
  gameday    live pushes — only on a day with an FBS game scheduled (checked against the week's scoreboard)
  backtest   ncaaf-sim walk-forward — any time
"""
import argparse
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ncaaf_common as C  # noqa: E402
import ncaaf_data as D  # noqa: E402

PRODUCTS = {"hub": {"preseason", "regular", "championship", "postseason", "offseason"},
            "gameday": {"regular", "championship", "postseason"},
            "backtest": {"preseason", "regular", "championship", "postseason", "offseason"}}


def games_today(ph):
    now = C.utcnow()
    today = C.to_ct(now).date()
    st, wk = (ph.get("st") or 2), ph.get("week")
    if not wk:
        return 0
    evs = D.week_events(ph["season"], st, wk)
    return sum(1 for e in evs if e.get("date") and C.to_ct(C.parse_iso(e["date"])).date() == today)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate")
    ap.add_argument("--season", type=int)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ph = D.phase(a.season)
    live = sorted(p for p, s in PRODUCTS.items() if ph["phase"] in s)
    line = (f"[ncaaf phase] {C.stamp_ct()} · {ph['season']} season · {ph['phase']}"
            + (f" · {ph['label']}" if ph.get("label") else "") + f" · live: {', '.join(live)}")
    if a.json:
        print(json.dumps(dict(ph, live=live), indent=1))
    else:
        print(line)
    if a.gate:
        g = a.gate.lower()
        if g not in PRODUCTS:
            sys.exit(f"[ncaaf phase] unknown product {g} (known: {', '.join(PRODUCTS)})")
        if ph["phase"] not in PRODUCTS[g]:
            print(f"[ncaaf phase] {g} is dormant in the {ph['phase']} — nothing to run.")
            sys.exit(3)
        if g == "gameday":
            n = games_today(ph)
            if not n:
                print("[ncaaf phase] gameday: no FBS game today (Central) — nothing to push.")
                sys.exit(3)
            print(f"[ncaaf phase] gameday: {n} FBS games today.")
    sys.exit(0)


if __name__ == "__main__":
    main()
