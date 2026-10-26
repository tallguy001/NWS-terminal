#!/usr/bin/env python3
"""hub_pull.py — the NCAAF League Hub's collector: every number the pages print, in one JSON (schema ncaaf-hub/1).

    python3 hub_pull.py --league --json league.json [--sims 10000] [--seed YYYYMMDD] [--no-kalshi] [--no-games] [--now ISO]

Reads (all cached; a warm run takes seconds, a cold run a few minutes):
  ncaaf-data-pull  the calendar, every FBS scoreboard of the season, the FBS registry and conferences, closing lines for every
                   final (ESPN core odds), the AP / Coaches / CFP rankings, ESPN team statistics (offense and opponents) for
                   all 138 teams, game summaries for the game pages, Kalshi (games of this week and last, futures)
  ncaaf-sim        HOUSE MODEL ratings (this season's finals, last season's prior), each remaining game's line / total /
                   win chance, a walk-forward pregame line for every final this season (the season scorecard), the
                   season simulation (conference title games, the CFP, bowl eligibility, next-game stakes) and the
                   committee-proxy picture "if the season ended today"
Nothing here is authored; hub_build.py renders it.
"""
import argparse
import datetime as dt
import gzip
import json
import math
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_common as HC  # noqa: E402

HC.need("ncaaf-sim")
import ncaaf_common as C  # noqa: E402
import ncaaf_data as D  # noqa: E402
import ncaaf_kalshi as K  # noqa: E402
import ncaaf_model as M  # noqa: E402
import ncaaf_sim as S  # noqa: E402

SCHEMA = "ncaaf-hub/1"
PYTH = 2.37      # Pythagorean exponent for college football (house choice, the published Football Outsiders value)


def log(s):
    print(s, file=sys.stderr, flush=True)


# ============================================================================ team stats -> rates, ranks, percentiles
STAT_DEFS = [
    # key, label, side ('us' offense / 'opp' allowed), fn(us, opp, gp, pf, pa) -> value, higher_is_better, fmt nd, unit
    ("ppg", "Points per game", "off", lambda u, o, g, pf, pa: pf / g if g else None, True, 1, ""),
    ("ypp", "Yards per play", "off", lambda u, o, g, pf, pa: _div(u.get("rushing.totalYards"), u.get("rushing.totalOffensivePlays")), True, 2, ""),
    ("ypg", "Total yards per game", "off", lambda u, o, g, pf, pa: _div(u.get("rushing.totalYards"), g), True, 1, ""),
    ("rypa", "Yards per carry", "off", lambda u, o, g, pf, pa: u.get("rushing.yardsPerRushAttempt"), True, 2, ""),
    ("rypg", "Rushing yards per game", "off", lambda u, o, g, pf, pa: _div(u.get("rushing.rushingYards"), g), True, 1, ""),
    ("pypa", "Yards per pass attempt", "off", lambda u, o, g, pf, pa: u.get("passing.yardsPerPassAttempt"), True, 2, ""),
    ("pypg", "Passing yards per game", "off", lambda u, o, g, pf, pa: _div(u.get("passing.netPassingYards"), g), True, 1, ""),
    ("cmp", "Completion %", "off", lambda u, o, g, pf, pa: u.get("passing.completionPct"), True, 1, "%"),
    ("3d", "Third-down conversion", "off", lambda u, o, g, pf, pa: _pct(u.get("miscellaneous.thirdDownConvs"), u.get("miscellaneous.thirdDownAttempts")), True, 1, "%"),
    ("sackr", "Sacks taken per game", "off", lambda u, o, g, pf, pa: _div(u.get("passing.sacks"), g), False, 2, ""),
    ("give", "Giveaways per game", "off", lambda u, o, g, pf, pa: _div(u.get("miscellaneous.totalGiveaways"), g), False, 2, ""),
    ("papg", "Points allowed per game", "def", lambda u, o, g, pf, pa: pa / g if g else None, False, 1, ""),
    ("dypp", "Yards per play allowed", "def", lambda u, o, g, pf, pa: _div(o.get("rushing.totalYards"), o.get("rushing.totalOffensivePlays")), False, 2, ""),
    ("dypg", "Total yards allowed per game", "def", lambda u, o, g, pf, pa: _div(o.get("rushing.totalYards"), g), False, 1, ""),
    ("drypa", "Yards per carry allowed", "def", lambda u, o, g, pf, pa: o.get("rushing.yardsPerRushAttempt"), False, 2, ""),
    ("dpypa", "Yards per pass allowed", "def", lambda u, o, g, pf, pa: o.get("passing.yardsPerPassAttempt"), False, 2, ""),
    ("d3d", "Third downs allowed", "def", lambda u, o, g, pf, pa: _pct(o.get("miscellaneous.thirdDownConvs"), o.get("miscellaneous.thirdDownAttempts")), False, 1, "%"),
    ("sacks", "Sacks per game", "def", lambda u, o, g, pf, pa: _div(u.get("defensive.sacks"), g), True, 2, ""),
    ("tfl", "Tackles for loss per game", "def", lambda u, o, g, pf, pa: _div(u.get("defensive.tacklesForLoss"), g), True, 2, ""),
    ("take", "Takeaways per game", "def", lambda u, o, g, pf, pa: _div(u.get("miscellaneous.totalTakeaways"), g), True, 2, ""),
    ("tom", "Turnover margin", "misc", lambda u, o, g, pf, pa: u.get("miscellaneous.turnOverDifferential"), True, 0, ""),
    ("pen", "Penalty yards per game", "misc", lambda u, o, g, pf, pa: _div(u.get("miscellaneous.totalPenaltyYards"), g), False, 1, ""),
    ("top", "Time of possession", "misc", lambda u, o, g, pf, pa: _div(u.get("miscellaneous.possessionTimeSeconds"), g), None, 0, ""),
    ("fg", "Field goal %", "misc", lambda u, o, g, pf, pa: u.get("kicking.fieldGoalPct") if (u.get("kicking.fieldGoalAttempts") or 0) >= 3 else None, True, 1, "%"),
    ("punt", "Net punting average", "misc", lambda u, o, g, pf, pa: u.get("punting.netAvgPuntYards") or None, True, 1, ""),
]


def _div(a, b):
    try:
        return float(a) / float(b) if a is not None and b else None
    except (TypeError, ValueError):
        return None


def _pct(a, b):
    v = _div(a, b)
    return None if v is None else 100 * v


def rank_pct(vals, higher=True):
    """{id: value} -> {id: (rank 1 = best, percentile 0–100, ties share the better rank)}; None stays None."""
    xs = {k: v for k, v in vals.items() if v is not None}
    n = len(xs)
    out = {k: (None, None) for k in vals}
    if n < 2:
        return out
    srt = sorted(xs.values(), reverse=higher)
    for k, v in xs.items():
        better = sum(1 for x in xs.values() if (x > v if higher else x < v))
        worse = sum(1 for x in xs.values() if (x < v if higher else x > v))
        out[k] = (better + 1, 100.0 * (worse + 0.5 * (n - better - worse - 1)) / (n - 1))
    return out


# ============================================================================ the pull
def build(a):
    t0 = time.time()
    now = C.parse_iso(a.now) if a.now else C.utcnow()
    season = a.season or C.season_of(now)
    ph = D.phase(season, now)
    cal = D.calendar(season)
    log(f"[hub_pull] {season} · {ph['phase']} · {ph.get('label')} · {C.stamp_ct(now)}")
    evs = D.season_events(season, post=True, now=now)
    reg = D.registry(season, evs)
    teams = reg["teams"]
    fbs = {t: v["conf"] for t, v in teams.items()}
    log(f"  events {len(evs)} ({sum(1 for e in evs if e['status']['completed'])} final) · {len(teams)} FBS teams · {C.stats_line()}")
    # ---- closing lines on every final (forever-cached)
    fin = [e for e in evs if e["status"]["completed"]]
    res = C.pmap(lambda e: D.closing(e["eid"], True), fin, workers=10)
    ncl = 0
    for e, r in zip(fin, res):
        e["cl"] = None if isinstance(r, Exception) else r
        ncl += 1 if e["cl"] and e["cl"].get("spread") is not None else 0
    # a game under way: the pregame line from the core endpoint (the scoreboard drops odds at kickoff)
    live = [e for e in evs if e["status"]["state"] == "in"]
    for e, r in zip(live, C.pmap(lambda e: D.closing(e["eid"], False), live, workers=6)):
        e["cl"] = None if isinstance(r, Exception) else r
    log(f"  closing lines {ncl}/{len(fin)} finals · {C.stats_line()}")
    # ---- HOUSE MODEL
    P = M.params()
    R, G = M.live(season, evs, reg, P, log=log)
    cw = D.current_week(season, now)
    cur_wk = cw["week"] if cw and cw["st"] == 2 else (max(e["week"] for e in evs if e["st"] == 2) + 1)
    for e in evs:
        h, aw = e["h"]["id"], e["a"]["id"]
        wk = e["week"] if e["st"] == 2 else None
        e["hm"] = {"line": round(R.line(h, aw, e["neutral"]), 4), "total": round(R.total(h, aw), 3),
                   "p": round(R.p_home(h, aw, e["neutral"], wk, e["st"]), 6)}
    # walk-forward pregame lines for this season's finals (each week fit on the games before it)
    pr, BX = R.prior, R.boxes
    reg_weeks = sorted({e["week"] for e in evs if e["st"] == 2 and e["status"]["completed"]})
    GG = [{"eid": e["eid"], "hid": e["h"]["id"], "aid": e["a"]["id"], "hs": e["h"]["score"], "as": e["a"]["score"], "neutral": e["neutral"],
           "week": e["week"], "st": e["st"], "date": e["date"]} for e in fin if e["h"]["score"] is not None]
    for w in reg_weeks:
        Rw = M.fit([g for g in GG if g["st"] == 2 and g["week"] < w], fbs, pr, P, season, w - 1, ref_week=w, boxes=BX)
        for e in evs:
            if e["st"] == 2 and e["week"] == w and e["status"]["completed"]:
                e["hm_pre"] = {"line": round(Rw.line(e["h"]["id"], e["a"]["id"], e["neutral"]), 4),
                               "p": round(Rw.p_home(e["h"]["id"], e["a"]["id"], e["neutral"], w), 6),
                               "total": round(Rw.total(e["h"]["id"], e["a"]["id"]), 3)}
    post_fin = [e for e in evs if e["st"] == 3 and e["status"]["completed"]]
    if post_fin:
        Rr = M.fit([g for g in GG if g["st"] == 2], fbs, pr, P, season, "reg", ref_week=99, boxes=BX)
        for e in post_fin:
            e["hm_pre"] = {"line": round(Rr.line(e["h"]["id"], e["a"]["id"], e["neutral"]), 4),
                           "p": round(Rr.p_home(e["h"]["id"], e["a"]["id"], e["neutral"], None, 3), 6),
                           "total": round(Rr.total(e["h"]["id"], e["a"]["id"]), 3)}
    ratings = {}
    nets = {t: R.net(t) for t in fbs}
    rk_net = HC_rank(nets, True)
    rk_off = HC_rank({t: R.o(t) for t in fbs}, True)
    rk_def = HC_rank({t: R.d(t) for t in fbs}, True)
    for t in fbs:
        ratings[t] = {"net": round(R.net(t), 4), "off": round(R.o(t), 4), "def": round(R.d(t), 4), "se": round(R.se.get(t, 0.0), 3),
                      "n": R.n_games.get(t, 0), "rk": rk_net[t][0], "pct": round(rk_net[t][1], 4), "rk_off": rk_off[t][0],
                      "pct_off": round(rk_off[t][1], 4), "rk_def": rk_def[t][0], "pct_def": round(rk_def[t][1], 4),
                      "prior": [round(x, 3) for x in (R.prior_rating.get(t) or (0.0, 0.0))]}
    log(f"  HOUSE MODEL ratings through week {R.through} · {len(G)} finals · {time.time() - t0:.1f} s")
    # ---- season simulation + today's picture
    seed = a.seed or int(C.to_ct(now).strftime("%Y%m%d"))
    sim = S.season_sim(season, R, evs, reg, n=a.sims, seed=seed, log=log)
    today = S.today_picture(R, evs, reg)
    # ---- schedule strength, résumé, records
    teamrec = records(evs, fbs, R)
    # ---- rankings
    try:
        rk = D.rankings(season)
    except RuntimeError as ex:
        rk = {}
        log(f"  rankings failed: {ex}")
    # ---- standings: ESPN's order and records (cross-check)
    try:
        esp = D.espn_standings(season)
    except RuntimeError:
        esp = {}
    mism = []
    for blk in esp.values():
        for r in blk["rows"]:
            tr = teamrec.get(r["id"])
            if tr and r.get("overall") and r["overall"] != f"{tr['w']}-{tr['l']}":
                mism.append(f"{r['abbr']} ESPN {r['overall']} vs games {tr['w']}-{tr['l']}")
    # ---- ESPN team statistics -> rates, ranks, percentiles
    stats, nst = {}, 0
    if not a.no_stats:
        res = C.pmap(lambda t: D.team_stats(season, t), list(fbs), workers=10)
        for t, r in zip(fbs, res):
            if isinstance(r, Exception):
                continue
            nst += 1
            u, o = r["us"], r["opp"]
            g = u.get("general.gamesPlayed") or teamrec[t]["gp"] or None
            vals = {}
            for k, lab, side, fn, hib, nd, unit in STAT_DEFS:
                try:
                    vals[k] = fn(u, o, g, teamrec[t]["pf"], teamrec[t]["pa"])
                except Exception:  # noqa: BLE001
                    vals[k] = None
            stats[t] = {"v": vals, "gp": g}
        for k, lab, side, fn, hib, nd, unit in STAT_DEFS:
            if hib is None:
                continue
            rp = rank_pct({t: stats[t]["v"].get(k) for t in stats}, hib)
            for t in stats:
                rr = rp.get(t, (None, None))
                stats[t].setdefault("rk", {})[k] = rr[0]
                stats[t].setdefault("pct", {})[k] = None if rr[1] is None else round(rr[1], 4)
    log(f"  team statistics {nst}/{len(fbs)} · {C.stats_line()}")
    # ---- last season (the 2025 corpus)
    last = last_season(season - 1, fbs)
    # ---- Kalshi (games of this week and last + futures)
    kal = {"ok": False, "why": "not read this build (--no-kalshi)"}
    if not a.no_kalshi:
        try:
            seen = dict(teams)
            for e in evs:
                for s in ("h", "a"):
                    seen.setdefault(e[s]["id"], e[s])
            ix = K.index(seen)
            scope = [e for e in evs if e["st"] == 2 and e["week"] in (cur_wk - 1, cur_wk)]
            recs, km = K.games(scope, ix, now=now, log=log)
            F, fm = K.futures(ix, season)
            kal = {"ok": bool(km.get("ok")), "why": km.get("why") or "", "games": recs, "meta": km, "futures": F, "fmeta": fm}
        except Exception as ex:  # noqa: BLE001
            kal = {"ok": False, "why": f"{type(ex).__name__}: {ex}"}
            log(f"  Kalshi failed: {ex}")
    # ---- game pages: summaries for last week's finals and this week's games under way / final
    games = {}
    if not a.no_games:
        scope = [e for e in evs if e["st"] == 2 and e["week"] in (cur_wk - 1, cur_wk) and e["status"]["state"] in ("post", "in")]
        res = C.pmap(lambda e: D.summary(e["eid"], final=e["status"]["completed"]), scope, workers=8)
        for e, r in zip(scope, res):
            if not isinstance(r, Exception):
                games[e["eid"]] = r
        log(f"  game summaries {len(games)}/{len(scope)} · {C.stats_line()}")
    facts = {}
    fp = os.path.join(C.HERE, "..", "references", f"season_{season}_facts.json")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            facts = json.load(f)
    cal_doc = M.load_cal()
    P_ = {"schema": SCHEMA, "season": season, "built_utc": now.strftime("%Y-%m-%dT%H:%MZ"), "built_ct": C.stamp_ct(now),
          "phase": ph, "cal": cal, "week": cur_wk, "reg": reg, "events": evs, "ratings": ratings,
          "model": {"mu": round(R.mu, 3), "hfa": round(R.hfa, 3), "sigma": P["sigma"], "sigma_early": P.get("sigma_early"),
                    "version": "v1.1" if P.get("stack") else "v1", "early": R.early, "boxes": R.box_note,
                    "poll": (M.polls().get(str(season)) or {}).get("date"),
                    "through": R.through, "finals": len(G), "fcs_group": round(R.g_off + R.g_def, 2),
                    "params": P, "calibration": {k: cal_doc.get(k) for k in ("model", "built", "train_seasons", "test_seasons", "corpus", "reading")},
                    "test_all": (cal_doc.get("report") or {}).get("test_all"), "train_all": (cal_doc.get("report") or {}).get("train_all"),
                    "v11": {k: (cal_doc.get("v11") or {}).get(k) for k in ("compare", "loso")},
                    "committee": cal_doc.get("committee")},
          "sim": sim, "today": today, "teamrec": teamrec, "rankings": rk, "stats": stats,
          "stat_defs": [[k, lab, side, hib, nd, unit] for k, lab, side, fn, hib, nd, unit in STAT_DEFS],
          "last": last, "kalshi": kal, "games": games, "facts": facts, "espn_mismatch": mism,
          "counts": {"finals": len(fin), "closing": ncl, "events": len(evs)}, "seconds": round(time.time() - t0, 1),
          "fetch": C.stats_line()}
    log(f"[hub_pull] done in {P_['seconds']} s · {C.stats_line()}" + (f" · ESPN record mismatches: {mism[:5]}" if mism else ""))
    return P_


def HC_rank(vals, higher=True):
    return rank_pct(vals, higher)


def records(evs, fbs, R):
    """Per FBS team: overall / home / away / neutral / conference records, PF, PA, streak, one-score record, Pythagorean
    wins, schedule strength played and remaining (mean opponent HOUSE MODEL net), the rating-expected wins of the games
    played (sum of today's single-game win chances), the résumé against an elite team."""
    out = {t: {"w": 0, "l": 0, "hw": 0, "hl": 0, "aw": 0, "al": 0, "nw": 0, "nl": 0, "cw": 0, "cl": 0, "pf": 0, "pa": 0,
               "gp": 0, "os_w": 0, "os_l": 0, "fcs_w": 0, "fcs_l": 0, "seq": [], "opp_played": [], "opp_left": [],
               "xw": 0.0, "rk_w": 0, "rk_l": 0} for t in fbs}
    for e in evs:
        if e["st"] != 2:
            continue
        h, a = e["h"], e["a"]
        nm = e["status"].get("name") or ""
        if "CANCEL" in nm:
            continue
        for me, op, home in ((h, a, True), (a, h, False)):
            t = me["id"]
            if t not in out:
                continue
            r = out[t]
            if e["status"]["completed"] and me["score"] is not None:
                won = me["score"] > op["score"]
                r["gp"] += 1
                r["w" if won else "l"] += 1
                r["pf"] += me["score"]
                r["pa"] += op["score"]
                loc = "n" if e["neutral"] else ("h" if home else "a")
                r[loc + ("w" if won else "l")] += 1
                if e["conf"] and fbs.get(op["id"]) == fbs.get(t) and fbs.get(t) != "IND" and not S.is_title_game(e, fbs.get(h["id"]), fbs.get(a["id"])):
                    r["cw" if won else "cl"] += 1
                if abs(me["score"] - op["score"]) <= 8:
                    r["os_w" if won else "os_l"] += 1
                if op["id"] not in fbs:
                    r["fcs_w" if won else "fcs_l"] += 1
                if op.get("rank"):
                    r["rk_w" if won else "rk_l"] += 1
                r["seq"].append("W" if won else "L")
                r["opp_played"].append(op["id"])
                adv = 0.0 if e["neutral"] else (R.hfa if home else -R.hfa)
                r["xw"] += M.Phi((R.net(t) - R.net(op["id"]) + adv) / R.P["sigma"])
            else:
                r["opp_left"].append(op["id"])
    for t, r in out.items():
        s = r.pop("seq")
        n = 0
        for x in reversed(s):
            if x == s[-1]:
                n += 1
            else:
                break
        r["strk"] = f"{s[-1]}{n}" if s else ""
        r["last5"] = "".join(s[-5:])
        pf, pa = r["pf"], r["pa"]
        r["pyth"] = round(r["gp"] * (pf ** PYTH) / ((pf ** PYTH) + (pa ** PYTH)), 3) if (pf + pa) > 0 else None
        r["sos_played"] = round(sum(R.net(o) for o in r["opp_played"]) / len(r["opp_played"]), 3) if r["opp_played"] else None
        r["sos_left"] = round(sum(R.net(o) for o in r["opp_left"]) / len(r["opp_left"]), 3) if r["opp_left"] else None
        r["xw"] = round(r["xw"], 3)
    sp = rank_pct({t: r["sos_played"] for t, r in out.items()}, True)
    sl = rank_pct({t: r["sos_left"] for t, r in out.items()}, True)
    for t, r in out.items():
        r["sos_played_rk"], r["sos_left_rk"] = sp[t][0], sl[t][0]
    return out


def last_season(y, fbs_now):
    """Last season's record and how it ended, from the packaged corpus (ncaaf-sim references)."""
    Cp = M.load_corpus(y)
    out = {}
    if not Cp:
        return out
    games = sorted(Cp["games"], key=lambda g: g["date"])
    for t in fbs_now:
        w = l = 0
        lastg = None
        for g in games:
            if t not in (g["hid"], g["aid"]):
                continue
            me_h = g["hid"] == t
            won = (g["hs"] > g["as"]) == me_h
            w += 1 if won else 0
            l += 0 if won else 1
            lastg = (g, won, g["aid"] if me_h else g["hid"])
        if not (w or l):
            continue
        end = ""
        if lastg and lastg[0]["st"] == 3:
            g, won, opp = lastg
            note = (g.get("note") or "").strip()
            opp_ab = Cp["names"].get(opp, "?")
            if "national championship" in note.lower():
                end = f"Won the national championship over {opp_ab}" if won else f"Lost the national championship to {opp_ab}"
            elif note:
                lab = note.split(" Presented")[0].split(" presented")[0]
                end = f"{'Won' if won else 'Lost'} the {lab} {'over' if won else 'to'} {opp_ab}"
            else:
                end = f"{'Won' if won else 'Lost'} a bowl game {'over' if won else 'to'} {opp_ab}"
        out[t] = {"w": w, "l": l, "end": end, "conf": Cp["fbs"].get(t)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--league", action="store_true", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--season", type=int)
    ap.add_argument("--sims", type=int, default=10000)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--now")
    ap.add_argument("--no-kalshi", action="store_true")
    ap.add_argument("--no-games", action="store_true")
    ap.add_argument("--no-stats", action="store_true")
    a = ap.parse_args()
    P = build(a)
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(P, f, separators=(",", ":"), ensure_ascii=False, default=str)
    log(f"[hub_pull] wrote {a.json} ({os.path.getsize(a.json) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
