#!/usr/bin/env python3
"""build_polls.py — the preseason AP poll (points, incl. others receiving votes) per season: the HOUSE MODEL's poll prior.

    python3 build_polls.py --seasons 2014-2026 [--out ../references/corpus/polls_pre.json]

ESPN core API seasons/{Y}/types/1/weeks/1/rankings/1 (from 2025) or types/2/weeks/1/rankings/1 (through 2024) = the AP Top 25,
preseason edition (released mid-August, before any game), with `ranks` (25) and `others` (receiving votes) carrying total points. Written as {"<Y>": {"date": ..., "max": top points,
"points": {team id: points}}}. A season's entry never changes once the poll is out: add the new season each August (the hub
pull does it automatically when the entry is missing). Library: `fetch(season)`.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
OUT = os.path.normpath(os.path.join(HERE, "..", "references", "corpus", "polls_pre.json"))


def fetch(season, tries=4):
    """-> {"date", "max", "points": {tid: pts}} or None when the preseason poll is not published."""
    for st in (1, 2):
        p = _fetch(f"{CORE}/seasons/{season}/types/{st}/weeks/1/rankings/1", tries)
        if p:
            return p
    return None


def _fetch(url, tries):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read().decode("utf-8"))
            pts = {}
            for e in (d.get("ranks") or []) + (d.get("others") or []):
                m = re.search(r"/teams/(\d+)", ((e.get("team") or {}).get("$ref") or ""))
                if m and e.get("points") is not None:
                    pts[m.group(1)] = float(e["points"])
            if not pts:
                return None
            return {"date": d.get("date"), "max": max(pts.values()), "points": pts}
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(1.5 * (2 ** k))
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (2 ** k))
    return None


def load(path=OUT):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", required=True, help="e.g. 2014-2026")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    lo, _, hi = a.seasons.partition("-")
    doc = load(a.out)
    for y in range(int(lo), int(hi or lo) + 1):
        p = fetch(y)
        if p:
            doc[str(y)] = p
        print(f"{y}: {'%d teams, top %d pts, %s' % (len(p['points']), p['max'], p['date']) if p else 'not published'}",
              file=sys.stderr)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    main()
