#!/usr/bin/env python3
"""ncaaf_data.py — the NCAAF suite's data layer: deterministic, cached pulls from ESPN's college-football feeds.

    python3 ncaaf_data.py clock                         season, phase, current week, the calendar
    python3 ncaaf_data.py slate [--week N] [--top]      a week's FBS games: kickoff CT, TV, ranks, DraftKings line / result
    python3 ncaaf_data.py standings [--conf SEC]        conference standings computed from the games (checked against ESPN)
    python3 ncaaf_data.py rankings [--poll ap|usa|cfp]  the latest AP / Coaches / CFP rankings
    python3 ncaaf_data.py team KEY                      one team: record, conference place, rank, schedule with lines
    python3 ncaaf_data.py game EVENT_ID                 one game: linescore, team box, scoring plays, closing line
    python3 ncaaf_data.py lines [--week N]              DraftKings (pregame) or closing lines for a week
    python3 ncaaf_data.py registry [--write]            the FBS registry (138 teams in 2026) -> references/teams_<Y>.json
    python3 ncaaf_data.py verify [--strict]             probe every feed the suite uses (exit 1 on a failure with --strict)
    (every command takes --season Y and --json)

Sources (all read-only, no key): ESPN site API (scoreboard groups=80 = FBS, standings, rankings, team statistics, game
summary), ESPN core API (per-game odds: the closing line once a game is final — the scoreboard drops odds at kickoff).
Identity: ESPN team id is canonical; `key` (abbreviation without punctuation: TA&M -> TAM, M-OH -> MOH) is the hub route.
FCS opponents are carried with fbs=False and no route.
"""
import argparse
import json
import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ncaaf_common as C  # noqa: E402

REFS = os.path.normpath(os.path.join(HERE, "..", "references"))

# ESPN conference group id -> (route key, short name, full name, tier)
CONFS = {
    "8": ("SEC", "SEC", "Southeastern Conference", "P4"),
    "5": ("B1G", "Big Ten", "Big Ten Conference", "P4"),
    "4": ("B12", "Big 12", "Big 12 Conference", "P4"),
    "1": ("ACC", "ACC", "Atlantic Coast Conference", "P4"),
    "151": ("AAC", "American", "American Conference", "G6"),
    "9": ("P12", "Pac-12", "Pac-12 Conference", "G6"),
    "17": ("MWC", "Mountain West", "Mountain West Conference", "G6"),
    "37": ("SBC", "Sun Belt", "Sun Belt Conference", "G6"),
    "15": ("MAC", "MAC", "Mid-American Conference", "G6"),
    "12": ("CUSA", "C-USA", "Conference USA", "G6"),
    "18": ("IND", "Independents", "FBS Independents", "IND"),
}
CONF_ORDER = ["SEC", "B1G", "B12", "ACC", "AAC", "P12", "MWC", "SBC", "MAC", "CUSA", "IND"]
CONF_BY_KEY = {v[0]: dict(id=k, key=v[0], short=v[1], name=v[2], tier=v[3]) for k, v in CONFS.items()}
ODDS_PREF = ["DraftKings", "ESPN BET", "consensus", "Caesars", "William Hill", "numberfire", "teamrankings", "Betradar"]


def key_of(abbr):
    return re.sub(r"[^A-Z0-9]", "", (abbr or "").upper()) or None


# ============================================================================ calendar
def calendar(season):
    """[{st: 2|3, week: int, label, start, end}] from the scoreboard's league calendar (cached a day)."""
    d = C.get_json(f"{C.SITE}/scoreboard?groups={C.FBS_GROUP}&dates={season}&seasontype=2&week=1&limit=1", ttl=86400)
    out = []
    for blk in (d.get("leagues") or [{}])[0].get("calendar") or []:
        st = int(blk.get("value") or 0)
        if st not in (2, 3):
            continue
        for e in blk.get("entries") or []:
            out.append({"st": st, "week": int(e.get("value")), "label": e.get("label"), "detail": e.get("detail"),
                        "start": e.get("startDate"), "end": e.get("endDate")})
    return out


def current_week(season, now=None):
    """The calendar entry that holds `now` (regular season), else the nearest: before week 1 -> week 1; after the last
    regular week -> the postseason entry ('Bowls'), returned with st=3."""
    now = now or C.utcnow()
    cal = calendar(season)
    for e in cal:
        s, t = C.parse_iso(e["start"]), C.parse_iso(e["end"])
        if s and t and s <= now <= t:
            return e
    reg = [e for e in cal if e["st"] == 2]
    if reg and now < C.parse_iso(reg[0]["start"]):
        return reg[0]
    post = [e for e in cal if e["st"] == 3]
    return post[0] if post else (reg[-1] if reg else None)


def phase(season=None, now=None):
    """preseason | regular | championship | postseason | offseason (2026: championship weekend = the regular week holding
    Dec 4–5, Army–Navy is the last regular week)."""
    now = now or C.utcnow()
    season = season or C.season_of(now)
    cal = calendar(season)
    reg = [e for e in cal if e["st"] == 2]
    post = [e for e in cal if e["st"] == 3]
    if not reg:
        return {"season": season, "phase": "offseason", "week": None}
    w1 = C.parse_iso(reg[0]["start"])
    end_reg = C.parse_iso(reg[-1]["end"])
    end_post = max((C.parse_iso(e["end"]) for e in post), default=end_reg)
    cw = current_week(season, now)
    if now < w1:
        ph = "preseason"
    elif now <= end_reg:
        ph = "championship" if cw and cw["st"] == 2 and cw["week"] >= len(reg) - 1 else "regular"
    elif now <= end_post:
        ph = "postseason"
    else:
        ph = "offseason"
    return {"season": season, "phase": ph, "week": cw["week"] if cw else None, "st": cw["st"] if cw else None,
            "label": cw["label"] if cw else None, "n_reg_weeks": len(reg)}


# ============================================================================ scoreboard -> events
def _team(c):
    t = c.get("team") or {}
    rank = ((c.get("curatedRank") or {}).get("current"))
    recs = {r.get("type") or r.get("name"): r.get("summary") for r in (c.get("records") or [])}
    sc = c.get("score")
    try:
        sc = int(sc) if sc not in (None, "") else None
    except (TypeError, ValueError):
        sc = None
    return {"id": str(t.get("id")), "abbr": t.get("abbreviation"), "key": key_of(t.get("abbreviation")),
            "loc": t.get("location") or t.get("shortDisplayName"), "nick": t.get("name"),
            "full": t.get("displayName"), "short": t.get("shortDisplayName"),
            "conf_id": str(t.get("conferenceId")) if t.get("conferenceId") is not None else None,
            "color": t.get("color"), "alt": t.get("alternateColor"),
            "score": sc, "rank": rank if rank and rank <= 25 else None,
            "rec": recs.get("total") or recs.get("overall"), "rec_conf": recs.get("vsconf"),
            "winner": c.get("winner"),
            "ls": [x.get("value") for x in (c.get("linescores") or [])]}


def _odds(cp):
    for o in cp.get("odds") or []:
        prov = (o.get("provider") or {}).get("name") or ""
        if "live" in prov.lower():
            continue
        ml = o.get("moneyline") or {}

        def mlv(side):
            v = (((ml.get(side) or {}).get("close") or {}).get("odds"))
            try:
                return float(str(v).replace("+", "")) if v not in (None, "", "OFF", "EVEN") else (100.0 if v == "EVEN" else None)
            except ValueError:
                return None
        sp = o.get("spread")
        out = {"prov": prov, "spread": float(sp) if sp is not None else None,
               "total": float(o["overUnder"]) if o.get("overUnder") is not None else None,
               "ml_h": mlv("home"), "ml_a": mlv("away"), "details": o.get("details")}
        out["p_h"] = C.novig(out["ml_h"], out["ml_a"])
        return out
    return None


def norm_event(ev, season=None, st=None, week=None):
    cp = (ev.get("competitions") or [{}])[0]
    comps = cp.get("competitors") or []
    h = next((c for c in comps if c.get("homeAway") == "home"), comps[0] if comps else {})
    a = next((c for c in comps if c.get("homeAway") == "away"), comps[-1] if comps else {})
    stt = (ev.get("status") or cp.get("status") or {})
    ty = stt.get("type") or {}
    venue = cp.get("venue") or {}
    addr = venue.get("address") or {}
    tv = []
    for b in cp.get("broadcasts") or []:
        for n in b.get("names") or []:
            if n and n not in tv:
                tv.append(n)
    notes = [n.get("headline") for n in (cp.get("notes") or []) if n.get("headline")]
    e = {"eid": str(ev.get("id")), "season": season or (ev.get("season") or {}).get("year"),
         "st": st or (ev.get("season") or {}).get("type"), "week": week if week is not None else (ev.get("week") or {}).get("number"),
         "date": cp.get("date") or ev.get("date"), "time_valid": cp.get("timeValid", True) is not False,
         "neutral": bool(cp.get("neutralSite")), "conf": bool(cp.get("conferenceCompetition")),
         "venue": {"name": venue.get("fullName"), "city": addr.get("city"), "state": addr.get("state"),
                   "indoor": venue.get("indoor")},
         "tv": tv, "notes": notes,
         "status": {"state": ty.get("state"), "completed": bool(ty.get("completed")), "name": ty.get("name"),
                    "detail": ty.get("detail"), "short": ty.get("shortDetail"), "period": stt.get("period"),
                    "clock": stt.get("displayClock")},
         "h": _team(h), "a": _team(a), "odds": _odds(cp)}
    return e


def _week_url(season, st, week):
    return f"{C.SITE}/scoreboard?groups={C.FBS_GROUP}&dates={season}&seasontype={st}&week={week}&limit=400"


def week_events(season, st, week, now=None):
    """Normalized events of one calendar week. A week that ended more than 36 h ago is kept forever once every game in it
    is final (or canceled/postponed); otherwise 10 minutes (live weeks) or 1 hour (future weeks)."""
    now = now or C.utcnow()
    ent = next((e for e in calendar(season) if e["st"] == st and e["week"] == week), None)
    end = C.parse_iso(ent["end"]) if ent else None
    start = C.parse_iso(ent["start"]) if ent else None
    url = _week_url(season, st, week)
    past = end is not None and (now - end).total_seconds() > 36 * 3600
    ttl = None if past else (600 if (start and start <= now) else 3600)
    d = C.get_json(url, ttl=ttl)
    evs = [norm_event(x, season, st, week) for x in d.get("events") or []]
    if past and any(not e["status"]["completed"] and e["status"]["state"] != "post"
                    and "CANCEL" not in (e["status"]["name"] or "") and "POSTPONED" not in (e["status"]["name"] or "")
                    for e in evs):
        d = C.get_json(url, ttl=3600)
        evs = [norm_event(x, season, st, week) for x in d.get("events") or []]
    return evs


def season_events(season, post=True, now=None, upto=None):
    """Every FBS event of the season (regular weeks, then the postseason), deduped by event id, in date order."""
    cal = calendar(season)
    weeks = [(e["st"], e["week"]) for e in cal if e["st"] == 2 or (post and e["st"] == 3)]
    if upto:
        weeks = [w for w in weeks if w[0] == 2 and w[1] <= upto]
    res = C.pmap(lambda w: week_events(season, w[0], w[1], now), weeks, workers=6)
    seen, out = set(), []
    for (st, wk), evs in zip(weeks, res):
        if isinstance(evs, Exception):
            print(f"[ncaaf_data] week {st}/{wk} failed: {evs}", file=sys.stderr)
            continue
        for e in evs:
            if e["eid"] in seen:
                continue
            seen.add(e["eid"])
            out.append(e)
    out.sort(key=lambda e: (e["date"] or "", e["eid"]))
    return out


# ============================================================================ closing lines (core API)
def closing(eid, final=True):
    """The game's line from ESPN's core odds endpoint: DraftKings first (then ESPN BET, consensus, …), never a live-odds
    provider. Home perspective: spread < 0 = home favored. Kept forever once the game is final."""
    url = f"{C.CORE}/events/{eid}/competitions/{eid}/odds"
    d = C.get_json(url, ttl=None if final else 900)
    items = [i for i in d.get("items") or [] if "live" not in ((i.get("provider") or {}).get("name") or "").lower()]
    if not items:
        return None

    def rank(i):
        n = (i.get("provider") or {}).get("name") or ""
        return ODDS_PREF.index(n) if n in ODDS_PREF else len(ODDS_PREF)
    i = sorted(items, key=rank)[0]
    ht, at = i.get("homeTeamOdds") or {}, i.get("awayTeamOdds") or {}
    sp = i.get("spread")
    out = {"prov": (i.get("provider") or {}).get("name"), "spread": float(sp) if sp is not None else None,
           "total": float(i["overUnder"]) if i.get("overUnder") not in (None, 0) else None,
           "ml_h": ht.get("moneyLine"), "ml_a": at.get("moneyLine"), "details": i.get("details")}
    out["p_h"] = C.novig(out["ml_h"], out["ml_a"])
    # open line (DraftKings carries open/close blocks)
    try:
        o = ((ht.get("open") or {}).get("pointSpread") or {}).get("american")
        out["open"] = float(o) if o not in (None, "", "OFF") else None
    except ValueError:
        out["open"] = None
    return out


# ============================================================================ standings, rankings, registry
def espn_standings(season):
    """ESPN's conference standings (order + its records), per conference id -> [entry]."""
    d = C.get_json(f"{C.SITE2}/standings?group={C.FBS_GROUP}&season={season}", ttl=1800)
    out = {}
    for c in d.get("children") or []:
        cid = str(c.get("id"))
        rows = []
        blocks = [(None, (c.get("standings") or {}).get("entries") or [])]
        blocks += [(sub.get("name"), (sub.get("standings") or {}).get("entries") or []) for sub in c.get("children") or []]
        for div, ents in blocks:
            for e in ents:
                t = e.get("team") or {}
                st = {s.get("name"): s.get("displayValue") for s in e.get("stats") or []}
                rows.append({"id": str(t.get("id")), "abbr": t.get("abbreviation"), "key": key_of(t.get("abbreviation")),
                             "loc": t.get("location"), "nick": t.get("name"), "full": t.get("displayName"),
                             "div": (div or "").replace(c.get("shortName") or "", "").strip(" -") or div,
                             "overall": st.get("overall"), "conf": st.get("vs. Conf."), "home": st.get("Home"),
                             "away": st.get("Away"), "streak": st.get("streak"), "seed": st.get("playoffSeed")})
        out[cid] = {"abbr": c.get("abbreviation"), "name": c.get("name"), "rows": rows}
    return out


def registry(season, events=None):
    """{teams: {id: {...}}, confs: {KEY: {...}}} for the FBS: membership from ESPN standings, colors from the season's
    scoreboards (every FBS team appears), falling back to the packaged snapshot."""
    st = espn_standings(season)
    snap = load_snapshot(season)
    colors = {}
    for e in events or []:
        for s in ("h", "a"):
            t = e[s]
            if t.get("color"):
                colors[t["id"]] = (t["color"], t.get("alt"))
    teams, confs = {}, {}
    for cid, blk in st.items():
        meta = CONFS.get(cid)
        if not meta:
            print(f"[ncaaf_data] unknown conference id {cid} ({blk.get('name')}) — add it to CONFS", file=sys.stderr)
            continue
        ck = meta[0]
        confs[ck] = {"id": cid, "key": ck, "short": meta[1], "name": meta[2], "tier": meta[3], "members": [], "divs": {}}
        for r in blk["rows"]:
            col, alt = colors.get(r["id"]) or ((snap.get(r["id"]) or {}).get("color"), (snap.get(r["id"]) or {}).get("alt"))
            div = r["div"] if r["div"] and r["div"] != blk.get("name") else None
            teams[r["id"]] = {"id": r["id"], "abbr": r["abbr"], "key": r["key"], "loc": r["loc"], "nick": r["nick"],
                              "full": r["full"], "conf": ck, "div": div, "color": col or "555555", "alt": alt or "ffffff"}
            confs[ck]["members"].append(r["id"])
            if div:
                confs[ck]["divs"].setdefault(div, []).append(r["id"])
    keys = [t["key"] for t in teams.values()]
    dup = {k for k in keys if keys.count(k) > 1}
    for t in teams.values():
        if t["key"] in dup:
            t["key"] = t["key"] + t["id"]
    return {"season": season, "teams": teams, "confs": confs}


def snapshot_path(season):
    return os.path.join(REFS, f"teams_{season}.json")


def load_snapshot(season):
    for y in (season, season - 1):
        p = snapshot_path(y)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return (json.load(f).get("teams") or {})
    return {}


def rankings(season=None):
    """Latest polls: {poll: {name, week, date, ranks: [{rank, id, key, abbr, pts, fpv, prev, rec}], others: [...]}}.
    poll keys: ap, usa (AFCA Coaches), cfp (College Football Playoff, from its first release)."""
    url = f"{C.SITE}/rankings" + (f"?seasons={season}" if season else "")
    d = C.get_json(url, ttl=1800)
    out = {}
    for p in d.get("rankings") or []:
        ty = (p.get("type") or "").lower()
        nm = p.get("name") or ""
        k = "cfp" if ("playoff" in nm.lower() or ty == "cfp") else ("ap" if ty == "ap" else ("usa" if ty == "usa" else ty))
        if k not in ("ap", "usa", "cfp"):
            continue
        ranks = []
        for r in p.get("ranks") or []:
            t = r.get("team") or {}
            ranks.append({"rank": r.get("current"), "prev": r.get("previous"), "pts": r.get("points"),
                          "fpv": r.get("firstPlaceVotes"), "id": str(t.get("id")), "abbr": t.get("abbreviation"),
                          "key": key_of(t.get("abbreviation")), "rec": r.get("recordSummary"), "trend": r.get("trend")})
        others = [{"id": str((r.get("team") or {}).get("id")), "pts": r.get("points")} for r in p.get("others") or []]
        out[k] = {"name": nm, "short": p.get("shortName"), "week": (p.get("occurrence") or {}).get("displayValue"),
                  "date": p.get("date"), "headline": p.get("headline"), "ranks": ranks, "others": others}
    return out


# ============================================================================ team season stats
STAT_PICK = {
    "passing": ["netPassingYards", "netPassingYardsPerGame", "passingAttempts", "completions", "completionPct",
                "yardsPerPassAttempt", "passingTouchdowns", "interceptions", "sacks", "sackYardsLost"],
    "rushing": ["rushingAttempts", "rushingYards", "yardsPerRushAttempt", "rushingTouchdowns", "rushingYardsPerGame",
                "rushingBigPlays", "totalOffensivePlays", "totalYards", "totalPoints", "totalPointsPerGame"],
    "receiving": ["receivingBigPlays"],
    "miscellaneous": ["firstDowns", "thirdDownConvs", "thirdDownAttempts", "thirdDownConvPct", "fourthDownConvs",
                      "fourthDownAttempts", "totalPenalties", "totalPenaltyYards", "possessionTimeSeconds",
                      "redzoneScoringPct", "redzoneTouchdownPct", "totalTakeaways", "totalGiveaways", "turnOverDifferential",
                      "fumblesLost"],
    "defensive": ["sacks", "tacklesForLoss", "passesDefended"],
    "defensiveInterceptions": ["interceptions"],
    "kicking": ["fieldGoalsMade", "fieldGoalAttempts", "fieldGoalPct"],
    "punting": ["netAvgPuntYards"],
    "returning": ["kickReturnTouchdowns", "puntReturnTouchdowns"],
    "general": ["gamesPlayed"],
}


def team_stats(season, tid, ttl=6 * 3600):
    """{'us': {cat.stat: value}, 'opp': {...}} from ESPN's team statistics (offense and what opponents did against it)."""
    d = C.get_json(f"{C.SITE}/teams/{tid}/statistics?season={season}", ttl=ttl)
    res = d.get("results") or {}

    def flat(blk):
        # 'stats' arrives as {categories: [...]}, 'opponent' as the bare list of categories
        cats = blk if isinstance(blk, list) else ((blk or {}).get("categories") or [])
        out = {}
        for cat in cats:
            want = STAT_PICK.get(cat.get("name"))
            if not want:
                continue
            for s in cat.get("stats") or []:
                if s.get("name") in want:
                    v = s.get("value")
                    try:
                        out[f"{cat['name']}.{s['name']}"] = float(v) if v is not None else None
                    except (TypeError, ValueError):
                        pass
        return out
    return {"us": flat(res.get("stats")), "opp": flat(res.get("opponent"))}


# ============================================================================ one game
BOX_KEYS = ["firstDowns", "thirdDownEff", "fourthDownEff", "totalYards", "netPassingYards", "completionAttempts",
            "yardsPerPass", "rushingYards", "rushingAttempts", "yardsPerRushAttempt", "totalPenaltiesYards", "turnovers",
            "fumblesLost", "interceptions", "possessionTime"]


def summary(eid, final=None):
    """Compact game summary: linescores, team box, scoring plays, ESPN win probability (home), drives count, the line."""
    url = f"{C.SITE}/summary?event={eid}"
    d = C.get_json(url, ttl=None if final else 60)
    hdr = ((d.get("header") or {}).get("competitions") or [{}])[0]
    teams = {}
    for c in hdr.get("competitors") or []:
        t = c.get("team") or {}
        teams[c.get("homeAway")] = {"id": str(t.get("id")), "abbr": t.get("abbreviation"),
                                    "score": int(c["score"]) if str(c.get("score") or "").isdigit() else None,
                                    "ls": [x.get("displayValue") for x in c.get("linescores") or []],
                                    "winner": c.get("winner")}
    box = {}
    for t in (d.get("boxscore") or {}).get("teams") or []:
        tid = str((t.get("team") or {}).get("id"))
        box[tid] = {s.get("name"): s.get("displayValue") for s in t.get("statistics") or [] if s.get("name") in BOX_KEYS}
    sp = []
    for p in d.get("scoringPlays") or []:
        sp.append({"q": (p.get("period") or {}).get("number"), "clock": (p.get("clock") or {}).get("displayValue"),
                   "tid": str((p.get("team") or {}).get("id")), "type": (p.get("scoringType") or {}).get("abbreviation"),
                   "text": p.get("text"), "h": p.get("homeScore"), "a": p.get("awayScore")})
    wp = [round(float(x.get("homeWinPercentage") or 0), 4) for x in d.get("winprobability") or []]
    drives = (d.get("drives") or {}).get("previous") or []
    dr = []
    for x in drives:
        dr.append({"tid": str((x.get("team") or {}).get("id")), "res": x.get("displayResult") or x.get("result"),
                   "plays": x.get("offensivePlays"), "yds": x.get("yards"), "q": ((x.get("start") or {}).get("period") or {}).get("number")})
    pc = None
    for p in d.get("pickcenter") or []:
        prov = (p.get("provider") or {}).get("name") or ""
        if "live" in prov.lower():
            continue
        pc = {"prov": prov, "spread": p.get("spread"), "total": p.get("overUnder"),
              "ml_h": (p.get("homeTeamOdds") or {}).get("moneyLine"), "ml_a": (p.get("awayTeamOdds") or {}).get("moneyLine")}
        break
    gi = d.get("gameInfo") or {}
    st = (hdr.get("status") or {}).get("type") or {}
    return {"eid": str(eid), "teams": teams, "box": box, "scoring": sp, "wp": wp, "drives": dr, "pick": pc,
            "attendance": gi.get("attendance"), "status": {"state": st.get("state"), "completed": st.get("completed"),
                                                          "detail": st.get("detail")}}


# ============================================================================ CLI
def _fmt_event(e, reg=None):
    d = C.parse_iso(e["date"])
    kick = (C.ct_day(d) + " " + (C.ct_time(d) + " CT" if e["time_valid"] else "TBD")) if d else C.DASH
    h, a = e["h"], e["a"]

    def nm(t):
        return (f"#{t['rank']} " if t.get("rank") else "") + (t["abbr"] or "?")
    m = f"{nm(a)} {'vs' if e['neutral'] else '@'} {nm(h)}"
    if e["status"]["completed"]:
        res = f"{a['abbr']} {a['score']}–{h['score']} {h['abbr']} (final)"
    elif e["status"]["state"] == "in":
        res = f"{a['abbr']} {a['score']}–{h['score']} {h['abbr']} ({e['status']['short']})"
    else:
        o = e.get("odds")
        res = (C.line_txt(o["spread"], h["abbr"], a["abbr"]) + (f", total {C.fmt(o['total'])}" if o and o.get("total") else "")
               + f" ({o['prov']})") if o and o.get("spread") is not None else "line not posted"
    return f"{kick:<24} {m:<26} {('/'.join(e['tv']) or '—'):<14} {res}"


def cmd_clock(a):
    ph = phase(a.season)
    print(f"[ncaaf clock] {C.stamp_ct()} · season {ph['season']} · phase {ph['phase']} · {ph.get('label') or ''}")
    for e in calendar(ph["season"]):
        print(f"  {'REG' if e['st'] == 2 else 'POST'} {e['label']:<10} {e['detail'] or ''}")
    return ph


def _pick_week(a):
    cw = current_week(a.season)
    st, wk = (2, a.week) if a.week else (cw["st"], cw["week"])
    return st, wk


def cmd_slate(a):
    st, wk = _pick_week(a)
    evs = week_events(a.season, st, wk)
    if a.top:
        evs = [e for e in evs if e["h"].get("rank") or e["a"].get("rank")]
    if a.json:
        return evs
    print(f"[ncaaf slate] {a.season} {'week ' + str(wk) if st == 2 else 'postseason'} · {len(evs)} FBS games · fetched {C.stamp_ct()}")
    for e in evs:
        print("  " + _fmt_event(e))
    return evs


def conf_table(season, events, reg):
    """Conference standings computed from the games: conference record (conference games only), overall record, PF/PA."""
    teams = reg["teams"]
    rows = {tid: {"id": tid, "cw": 0, "cl": 0, "w": 0, "l": 0, "pf": 0, "pa": 0, "streak": []} for tid in teams}
    for e in events:
        if not e["status"]["completed"] or e["st"] != 2:
            continue
        h, a = e["h"], e["a"]
        if h["score"] is None or a["score"] is None:
            continue
        for me, op in ((h, a), (a, h)):
            r = rows.get(me["id"])
            if r is None:
                continue
            win = me["score"] > op["score"]
            r["w" if win else "l"] += 1
            r["pf"] += me["score"]
            r["pa"] += op["score"]
            r["streak"].append("W" if win else "L")
            if e["conf"] and op["id"] in teams and teams[op["id"]]["conf"] == teams[me["id"]]["conf"] and teams[me["id"]]["conf"] != "IND":
                r["cw" if win else "cl"] += 1
    for r in rows.values():
        s = r.pop("streak")
        n = 0
        for x in reversed(s):
            if x == s[-1]:
                n += 1
            else:
                break
        r["strk"] = f"{s[-1]}{n}" if s else C.DASH
    return rows


def cmd_standings(a):
    evs = season_events(a.season, post=False)
    reg = registry(a.season, evs)
    rows = conf_table(a.season, evs, reg)
    esp = espn_standings(a.season)
    out = {}
    for ck in CONF_ORDER:
        cf = reg["confs"].get(ck)
        if not cf:
            continue
        mem = sorted(cf["members"], key=lambda t: (-(rows[t]["cw"] - rows[t]["cl"]), -rows[t]["cw"], -(rows[t]["w"] - rows[t]["l"])))
        out[ck] = [dict(rows[t], key=reg["teams"][t]["key"], abbr=reg["teams"][t]["abbr"]) for t in mem]
        if a.conf and a.conf.upper() != ck:
            continue
        if not a.json:
            print(f"\n{cf['short']} ({len(mem)})          conf   overall   PF   PA  strk")
            for t in mem:
                r = rows[t]
                print(f"  {reg['teams'][t]['abbr']:<6} {r['cw']:>3}–{r['cl']:<3} {r['w']:>3}–{r['l']:<3} {r['pf']:>5} {r['pa']:>4}  {r['strk']}")
    # cross-check against ESPN's own records
    bad = []
    for cid, blk in esp.items():
        for r in blk["rows"]:
            mine = rows.get(r["id"])
            if mine and r.get("overall") and r["overall"] != f"{mine['w']}-{mine['l']}":
                bad.append(f"{r['abbr']} ESPN {r['overall']} vs games {mine['w']}-{mine['l']}")
    if not a.json:
        print(f"\n[ncaaf standings] ESPN overall-record check: {'all agree' if not bad else str(len(bad)) + ' differ: ' + '; '.join(bad[:8])}")
    return out


def cmd_rankings(a):
    R = rankings(a.season)
    if a.json:
        return R
    for k in ([a.poll] if a.poll else ["cfp", "ap", "usa"]):
        p = R.get(k)
        if not p:
            print(f"[ncaaf rankings] {k}: not released")
            continue
        print(f"\n{p['name']} — {p.get('headline') or ''} ({p.get('date')})")
        for r in p["ranks"]:
            print(f"  {r['rank']:>2}. {r['abbr']:<6} {r.get('rec') or '':<6} {('' if r.get('pts') is None else int(r['pts'])):>5}  prev {r.get('prev')}")
    return R


def cmd_team(a):
    evs = season_events(a.season)
    reg = registry(a.season, evs)
    k = a.key.upper()
    t = next((x for x in reg["teams"].values() if x["key"] == k or x["abbr"] == a.key or x["id"] == a.key), None)
    if not t:
        sys.exit(f"[ncaaf team] unknown team {a.key}")
    mine = [e for e in evs if t["id"] in (e["h"]["id"], e["a"]["id"])]
    print(f"[ncaaf team] {t['full']} ({t['abbr']}, {CONF_BY_KEY[t['conf']]['short']}) · {len(mine)} games · fetched {C.stamp_ct()}")
    for e in mine:
        print("  " + _fmt_event(e))
    return mine


def cmd_game(a):
    s = summary(a.eid)
    cl = closing(a.eid, final=bool(s["status"].get("completed")))
    if a.json:
        return {"summary": s, "closing": cl}
    h, aw = s["teams"].get("home") or {}, s["teams"].get("away") or {}
    print(f"[ncaaf game] {aw.get('abbr')} {aw.get('score')} @ {h.get('abbr')} {h.get('score')} · {s['status'].get('detail')}")
    print(f"  by quarter: {aw.get('abbr')} {' '.join(aw.get('ls') or [])} | {h.get('abbr')} {' '.join(h.get('ls') or [])}")
    if cl:
        print(f"  line ({cl['prov']}): {C.line_txt(cl['spread'], h.get('abbr'), aw.get('abbr'))}, total {C.fmt(cl.get('total'))}")
    for tid, b in s["box"].items():
        print(f"  box {tid}: " + ", ".join(f"{k} {v}" for k, v in b.items()))
    for p in s["scoring"]:
        print(f"  Q{p['q']} {p['clock']} {p['type']}: {p['text']} ({p['a']}–{p['h']})")
    return s


def cmd_lines(a):
    st, wk = _pick_week(a)
    evs = week_events(a.season, st, wk)
    fin = [e for e in evs if e["status"]["completed"]]
    cls = C.pmap(lambda e: closing(e["eid"], True), fin, workers=8)
    cmap = {e["eid"]: (c if not isinstance(c, Exception) else None) for e, c in zip(fin, cls)}
    out = []
    for e in evs:
        o = cmap.get(e["eid"]) if e["status"]["completed"] else e.get("odds")
        out.append({"eid": e["eid"], "away": e["a"]["abbr"], "home": e["h"]["abbr"], "line": o,
                    "kind": "closing" if e["status"]["completed"] else "current"})
        if not a.json:
            txt = (C.line_txt(o["spread"], e["h"]["abbr"], e["a"]["abbr"]) + f" · total {C.fmt(o.get('total'))} · {o.get('prov')}") if o and o.get("spread") is not None else "not posted"
            print(f"  {e['a']['abbr']:>6} @ {e['h']['abbr']:<6} {('closing' if e['status']['completed'] else 'current'):<8} {txt}")
    return out


def cmd_registry(a):
    evs = season_events(a.season, post=False)
    reg = registry(a.season, evs)
    n = len(reg["teams"])
    print(f"[ncaaf registry] {a.season}: {n} FBS teams in {len(reg['confs'])} conferences: "
          + ", ".join(f"{c['short']} {len(c['members'])}" for c in reg["confs"].values()))
    if a.write:
        os.makedirs(REFS, exist_ok=True)
        snap = {"season": a.season, "built": C.stamp_ct(), "source": "ESPN standings (membership) + scoreboards (colors)",
                "teams": reg["teams"], "confs": reg["confs"]}
        with open(snapshot_path(a.season), "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=1, ensure_ascii=False)
        print(f"  wrote {snapshot_path(a.season)}")
    return reg


def cmd_verify(a):
    rows, bad = [], 0
    season = a.season

    def chk(name, fn, test):
        nonlocal bad
        try:
            v = fn()
            ok, note = test(v)
        except Exception as e:  # noqa: BLE001
            ok, note = False, f"{type(e).__name__}: {e}"
        rows.append((("✅" if ok else "❌"), name, note))
        if not ok:
            bad += 1
    cw = current_week(season)
    chk("calendar", lambda: calendar(season), lambda v: (len(v) >= 15, f"{len(v)} entries"))
    chk("scoreboard (this week)", lambda: week_events(season, cw["st"], cw["week"]),
        lambda v: (len(v) > 0, f"{len(v)} events, {sum(1 for e in v if e.get('odds'))} with DraftKings odds"))
    chk("standings", lambda: espn_standings(season), lambda v: (sum(len(b['rows']) for b in v.values()) >= 130,
                                                               f"{sum(len(b['rows']) for b in v.values())} FBS teams"))
    chk("rankings", lambda: rankings(season), lambda v: ("ap" in v, ", ".join(f"{k} {len(p['ranks'])}" for k, p in v.items())))
    prev = week_events(season, 2, max(1, cw["week"] - 1)) if cw["st"] == 2 else []
    fin = [e for e in prev if e["status"]["completed"]]
    if fin:
        chk("closing line (core odds)", lambda: closing(fin[0]["eid"]), lambda v: (bool(v and v.get("spread") is not None),
                                                                                   f"{v and v.get('prov')} {v and v.get('details')}"))
        chk("game summary", lambda: summary(fin[0]["eid"], True), lambda v: (bool(v["box"]), f"{len(v['scoring'])} scoring plays, {len(v['wp'])} WP points"))
        tid = fin[0]["h"]["id"]
        chk("team statistics", lambda: team_stats(season, tid), lambda v: (len(v["us"]) > 20 and len(v["opp"]) > 20,
                                                                          f"{len(v['us'])} + {len(v['opp'])} fields"))
    for r in rows:
        print(f"  {r[0]} {r[1]:<26} {r[2]}")
    print(f"[ncaaf verify] {len(rows) - bad}/{len(rows)} ok · {C.stats_line()}")
    if a.strict and bad:
        sys.exit(1)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=C.season_of())
    ap.add_argument("--json", action="store_true")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("clock")
    s = sp.add_parser("slate"); s.add_argument("--week", type=int); s.add_argument("--top", action="store_true")
    s = sp.add_parser("standings"); s.add_argument("--conf")
    s = sp.add_parser("rankings"); s.add_argument("--poll", choices=["ap", "usa", "cfp"])
    s = sp.add_parser("team"); s.add_argument("key")
    s = sp.add_parser("game"); s.add_argument("eid")
    s = sp.add_parser("lines"); s.add_argument("--week", type=int)
    s = sp.add_parser("registry"); s.add_argument("--write", action="store_true")
    s = sp.add_parser("verify"); s.add_argument("--strict", action="store_true")
    # global flags after the subcommand too
    for p in sp.choices.values():
        p.add_argument("--season", type=int, default=argparse.SUPPRESS)
        p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    a = ap.parse_args()
    fn = {"clock": cmd_clock, "slate": cmd_slate, "standings": cmd_standings, "rankings": cmd_rankings, "team": cmd_team,
          "game": cmd_game, "lines": cmd_lines, "registry": cmd_registry, "verify": cmd_verify}[a.cmd]
    out = fn(a)
    if a.json:
        print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
