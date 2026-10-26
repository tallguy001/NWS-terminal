#!/usr/bin/env python3
"""build_boxes.py — per-game team box stats for FBS v FBS finals (the efficiency layer of the HOUSE MODEL).

    python3 build_boxes.py --seasons 2016-2025 [--workers 16] [--out ../references/corpus]

For every final in references/corpus/games_<Y>.json.gz with two FBS teams, both teams' statistics from ESPN's core API
(events/{id}/competitions/{id}/competitors/{team}/statistics, ≈100 KB each, NOT cached raw) reduced to one compact row:
plays, yards, first downs, rush attempts / yards, pass attempts / net yards, sacks taken, third-down conversions / attempts,
giveaways, penalty yards, possession seconds. Written to references/corpus/boxes_<Y>.json.gz = {season, cols, rows: {eid:
{team id: [..]}}}. Closed seasons never change: build once, add each finished season at the annual walk. Library:
`fetch_box(eid, tid)` (the live pull uses it for this season's finals).
"""
import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
OUT = os.path.normpath(os.path.join(HERE, "..", "references", "corpus"))
COLS = ["plays", "yds", "fd", "ra", "ry", "pa", "py", "sk", "c3", "a3", "to", "pen", "top"]
PICK = {("rushing", "totalOffensivePlays"): "plays", ("rushing", "totalYards"): "yds", ("miscellaneous", "firstDowns"): "fd",
        ("rushing", "rushingAttempts"): "ra", ("rushing", "rushingYards"): "ry", ("passing", "passingAttempts"): "pa",
        ("passing", "netPassingYards"): "py", ("passing", "sacks"): "sk", ("miscellaneous", "thirdDownConvs"): "c3",
        ("miscellaneous", "thirdDownAttempts"): "a3", ("miscellaneous", "totalGiveaways"): "to",
        ("miscellaneous", "totalPenaltyYards"): "pen", ("miscellaneous", "possessionTimeSeconds"): "top"}


def fetch_box(eid, tid, tries=4):
    url = f"{CORE}/events/{eid}/competitions/{eid}/competitors/{tid}/statistics"
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read().decode("utf-8"))
            vals = {}
            for cat in (d.get("splits") or {}).get("categories") or []:
                for s in cat.get("stats") or []:
                    key = PICK.get((cat.get("name"), s.get("name")))
                    if key and key not in vals:
                        vals[key] = s.get("value")
            if not vals.get("plays"):
                return None
            # giveaways are sometimes absent: interceptions thrown + fumbles lost
            if vals.get("to") is None:
                ints = fl = None
                for cat in (d.get("splits") or {}).get("categories") or []:
                    for s in cat.get("stats") or []:
                        if cat.get("name") == "passing" and s.get("name") == "interceptions":
                            ints = s.get("value")
                        if cat.get("name") == "general" and s.get("name") == "fumblesLost":
                            fl = s.get("value")
                if ints is not None or fl is not None:
                    vals["to"] = (ints or 0) + (fl or 0)
            return [None if vals.get(c) is None else round(float(vals[c]), 1) for c in COLS]
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(1.5 * (2 ** k))
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (2 ** k))
    return None


def build(season, workers=16, log=print):
    import ncaaf_model as M
    Cp = M.load_corpus(season)
    fbs = Cp["fbs"]
    games = [g for g in Cp["games"] if g["hid"] in fbs and g["aid"] in fbs]
    jobs = [(g["eid"], t) for g in games for t in (g["hid"], g["aid"])]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(lambda j: fetch_box(*j), jobs))
    rows = {}
    for (eid, tid), r in zip(jobs, res):
        if r:
            rows.setdefault(eid, {})[tid] = r
    full = sum(1 for g in games if len(rows.get(g["eid"], {})) == 2)
    log(f"[build_boxes] {season}: {full}/{len(games)} FBS v FBS finals with both boxes · {len(jobs)} GETs in {time.time() - t0:.0f} s")
    return {"season": season, "cols": COLS, "rows": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", default="2016-2025")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.seasons.split("-")) if "-" in a.seasons else (int(a.seasons), int(a.seasons))
    for y in range(lo, hi + 1):
        doc = build(y, a.workers)
        p = os.path.join(a.out, f"boxes_{y}.json.gz")
        with gzip.open(p, "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump(doc, f, separators=(",", ":"))
        print(f"  wrote {p} ({os.path.getsize(p) / 1e3:.0f} KB)", flush=True)


if __name__ == "__main__":
    main()
