#!/usr/bin/env python3
"""build_corpus.py — the HOUSE MODEL's history: every FBS game of past seasons with its score and closing line.

    python3 build_corpus.py --seasons 2014-2025 [--lines-from 2019] [--out ../references/corpus]

Per season (ESPN, through ncaaf-data-pull): the league calendar, every regular week and the postseason scoreboard (groups=80:
every game with an FBS team, FCS opponents included), FBS membership and conferences from that season's standings, and —
from --lines-from on — each final's closing line from ESPN's core odds endpoint (DraftKings, else ESPN BET, else the
consensus; a live-odds provider never). One gzip JSON per season: references/corpus/games_<Y>.json.gz =
{season, built, fbs: {team id: conf key}, names: {team id: abbr}, games: [[eid, st, week, date, hid, aid, hs, as, neutral,
conf_game, spread_home, total, ml_h, ml_a, prov, note], ...]} (note = ESPN's game headline,
e.g. "Big Ten Championship") (finals only; canceled games dropped).
Closed seasons never change, so a rebuild is only needed once a year (after the title game) — the ncaaf-suite-audit walk.
"""
import argparse
import gzip
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _need():
    import glob
    cand = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ncaaf-data-pull", "scripts")
    dirs = [cand] + sorted(glob.glob("/mnt/skills/*/ncaaf-data-pull/scripts")) + \
        sorted(glob.glob(os.path.expanduser("~/.claude/skills/synced/*/ncaaf-data-pull/scripts")))
    for d in dirs:
        if os.path.isdir(d):
            sys.path.insert(0, d)
            return d
    sys.exit("[ncaaf-sim] sibling skill ncaaf-data-pull not installed (required)")


_need()
import ncaaf_common as C  # noqa: E402
import ncaaf_data as D  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "references", "corpus"))


def fbs_membership(season):
    st = D.espn_standings(season)
    fbs, names = {}, {}
    for cid, blk in st.items():
        ck = (D.CONFS.get(cid) or (blk.get("abbr"),))[0]
        for r in blk["rows"]:
            fbs[r["id"]] = ck
            names[r["id"]] = r["abbr"]
    return fbs, names


def build(season, lines=True, log=print):
    evs = D.season_events(season, post=True)
    fbs, names = fbs_membership(season)
    fin = [e for e in evs if e["status"]["completed"] and e["h"]["score"] is not None and e["a"]["score"] is not None]
    for e in evs:
        for s in ("h", "a"):
            names.setdefault(e[s]["id"], e[s]["abbr"])
    cl = {}
    if lines:
        res = C.pmap(lambda e: D.closing(e["eid"], True), fin, workers=10)
        for e, r in zip(fin, res):
            cl[e["eid"]] = None if isinstance(r, Exception) else r
    rows = []
    for e in fin:
        o = cl.get(e["eid"]) or {}
        rows.append([e["eid"], e["st"], e["week"], e["date"], e["h"]["id"], e["a"]["id"], e["h"]["score"], e["a"]["score"],
                     1 if e["neutral"] else 0, 1 if e["conf"] else 0, o.get("spread"), o.get("total"), o.get("ml_h"),
                     o.get("ml_a"), o.get("prov"), (e["notes"][0] if e["notes"] else None)])
    n_l = sum(1 for r in rows if r[10] is not None)
    log(f"[build_corpus] {season}: {len(rows)} finals ({sum(1 for r in rows if r[4] in fbs and r[5] in fbs)} FBS v FBS), "
        f"{len(fbs)} FBS teams, closing lines on {n_l} · {C.stats_line()}")
    return {"season": season, "built": C.stamp_ct(), "fbs": fbs, "names": names,
            "cols": ["eid", "st", "week", "date", "hid", "aid", "hs", "as", "neutral", "conf", "spread", "total", "ml_h", "ml_a", "prov",
                     "note"],
            "games": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", default="2014-2025")
    ap.add_argument("--lines-from", type=int, default=2019)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.seasons.split("-")) if "-" in a.seasons else (int(a.seasons), int(a.seasons))
    os.makedirs(a.out, exist_ok=True)
    for y in range(lo, hi + 1):
        doc = build(y, lines=y >= a.lines_from)
        p = os.path.join(a.out, f"games_{y}.json.gz")
        with gzip.open(p, "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump(doc, f, separators=(",", ":"))
        print(f"  wrote {p} ({os.path.getsize(p) / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
