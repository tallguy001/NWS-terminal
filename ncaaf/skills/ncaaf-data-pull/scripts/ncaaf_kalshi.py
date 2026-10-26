#!/usr/bin/env python3
"""ncaaf_kalshi — Kalshi exchange prices for college football (kalshi-v1, the NFL / NBA / EPL hubs' port), read-only.

Source: Kalshi's public Trade API v2 (https://api.elections.kalshi.com/trade-api/v2; no key). Series read:
  * KXNCAAFGAME     one event per game, two YES markets "<team> wins" (ticker KXNCAAFGAME-26OCT27DELWKU = DEL at WKU,
                    away first). Kalshi's college codes are not ESPN's (MTU = MTSU, JVST = JXST, MOSU = MOST), so a market is
                    paired to a team by its own team name (yes_sub_title, normalised: "Missouri St." = "Missouri State"),
                    then by code; both teams and the kickoff's Eastern date within 1 day must agree.
  * KXNCAAF         national champion (one market per team); KXNCAAFPLAYOFF  CFP qualifiers (one per team);
    conference champions KXNCAAFSEC, KXNCAAFB10, KXNCAAFB12, KXNCAAFACC, KXNCAAFAAC, KXNCAAFMWC, KXNCAAFSBELT, KXNCAAFMAC,
    KXNCAAFCUSA, KXNCAAFPAC12 — the current season's event only.

The price (the sibling hubs' honesty rules, unchanged):
  * per market: the YES mid when both sides are quoted within 10¢, else the last trade; nothing when neither exists;
  * a game: the two "wins" prices normalised to 100 (no-vig); a book whose raw prices sum outside 90–110¢ is not priced;
  * not started -> the book at read time; started or final -> the PRE-KICKOFF price: the last hourly candle ending at or
    before kickoff, stepping back an hour (at most twice) when that hour moved 20¢ — never an in-play price;
  * futures: each team's YES price as quoted (not normalised: "to make the playoff" markets are independent binaries);
  * never blended with the HOUSE MODEL or DraftKings, never an input to any computed number; a Kalshi–DraftKings gap is a
    disagreement between two markets, not an edge. Thin = under 1,000 contracts or a spread over 4¢.

    python3 ncaaf_kalshi.py --season 2026 [--week N]      prints what attaches to a week's games and the futures (no writes)
Library: games(events, teams_index, now) -> (recs {eid: rec}, meta); futures(teams_index, season) -> (F, meta).
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ncaaf_common as C  # noqa: E402

MARK = "kalshi-v1"
API = C.KALSHI
S_GAME = "KXNCAAFGAME"
FUT = {"title": "KXNCAAF", "playoff": "KXNCAAFPLAYOFF"}
CONF_SERIES = {"SEC": "KXNCAAFSEC", "B1G": "KXNCAAFB10", "B12": "KXNCAAFB12", "ACC": "KXNCAAFACC", "AAC": "KXNCAAFAAC",
               "MWC": "KXNCAAFMWC", "SBC": "KXNCAAFSBELT", "MAC": "KXNCAAFMAC", "CUSA": "KXNCAAFCUSA", "P12": "KXNCAAFPAC12"}
UA = "ncaaf-hub/1.0 (personal analytics)"
MAX_SPREAD = 0.10
INPLAY_RANGE = 0.20
MAX_STEPS = 2
LOOKBACK_H = 24
MAX_CANDLES = 9000
MAX_TICKERS = 99
PACE = 0.35
THIN_VOL = 1000
THIN_SPREAD = 0.04
DATE_WINDOW = 1
UTC = timezone.utc
STATS = dict(req=0, fail=0, r429=0)
_LAST = [0.0]
MON = {m: i + 1 for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}
EV_RE = re.compile(r"^[A-Z]+-(\d{2})([A-Z]{3})(\d{2})([A-Z0-9]{4,12})$")
ALIAS = {"miami fl": "miami", "appalachian state": "app state", "louisiana monroe": "ul monroe",
         "north carolina state": "nc state", "umass": "massachusetts", "southern mississippi": "southern miss",
         "hawaii": "hawaii", "san jose state": "san jose state", "ole miss": "ole miss", "mississippi": "ole miss",
         "louisiana lafayette": "louisiana", "texas san antonio": "utsa", "central florida": "ucf",
         "connecticut": "uconn", "brigham young": "byu", "southern methodist": "smu", "southern california": "usc",
         "miami oh": "miami oh", "army west point": "army", "florida international": "fiu", "florida atlantic": "fau"}


def norm(s):
    s = (s or "").lower().replace("&", "").replace("'", "").replace("’", "").replace("é", "e").replace("ʻ", "")
    s = re.sub(r"\bst\.?$", "state", s.strip())
    s = re.sub(r"(?<=\w)\s+st\.\s", " state ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = " ".join(s.split())
    return ALIAS.get(s, s)


def index(teams):
    """{normalised name or code -> team id} from {id: {loc, full, abbr, ...}} (FBS registry plus any FCS teams seen)."""
    ix = {}
    for t in teams.values():
        for n in (t.get("loc"), t.get("full"), t.get("short")):
            if n:
                ix.setdefault("n:" + norm(n), t["id"])
        if t.get("abbr"):
            ix.setdefault("c:" + t["abbr"].upper(), t["id"])
    return ix


def who(ix, name, code):
    return ix.get("n:" + norm(name)) or ix.get("c:" + (code or "").upper())


# ---------------------------------------------------------------- transport
def _get(path, params=None, tries=8):
    url = API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    for k in range(tries):
        wait = PACE - (time.time() - _LAST[0])
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.time()
        try:
            STATS["req"] += 1
            r = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(r, timeout=45) as f:
                return json.load(f)
        except urllib.error.HTTPError as ex:
            STATS["r429"] += 1 if ex.code == 429 else 0
            if ex.code in (429, 500, 502, 503, 504) and k < tries - 1:
                time.sleep(min(8.0, 0.5 * 2 ** k) + random.random() * 0.3)
                continue
            STATS["fail"] += 1
            return None
        except Exception:  # noqa: BLE001
            if k < tries - 1:
                time.sleep(min(8.0, 0.5 * 2 ** k))
                continue
            STATS["fail"] += 1
            return None
    return None


def _f(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _ts(iso):
    d = C.parse_iso(iso) if isinstance(iso, str) else iso
    return int(d.timestamp()) if d else None


def ev_date(tk):
    m = EV_RE.match(tk or "")
    if not m or m.group(2) not in MON:
        return None
    try:
        return date(2000 + int(m.group(1)), MON[m.group(2)], int(m.group(3)))
    except ValueError:
        return None


def markets(series, min_close_ts=None, status=None):
    out, cur = [], ""
    for _ in range(25):
        p = dict(series_ticker=series, limit=1000)
        if min_close_ts:
            p["min_close_ts"] = min_close_ts
        if status:
            p["status"] = status
        if cur:
            p["cursor"] = cur
        d = _get("/markets", p)
        if d is None:
            return None if not out else out
        out += d.get("markets") or []
        cur = d.get("cursor") or ""
        if not cur or not d.get("markets"):
            break
    return out


def _side_price(bid, ask, last):
    if bid is not None and ask is not None and bid > 0 and ask < 1 and ask >= bid and ask - bid <= MAX_SPREAD:
        return (bid + ask) / 2, ask - bid
    if last is not None and 0 < last < 1:
        return last, (ask - bid) if (bid is not None and ask is not None and bid > 0 and ask < 1) else None
    return None, None


def px_now(m):
    p, s = _side_price(_f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars")), _f(m.get("last_price_dollars")))
    return p, s, _f(m.get("volume_fp")) or 0.0


def _cd(c, k, f="close_dollars"):
    return _f((c.get(k) or {}).get(f)) if isinstance(c.get(k), dict) else None


def prefetch(jobs):
    rows = sorted(((tk, cut) for tks, cut in jobs for tk in tks), key=lambda x: x[1])
    batches, cur = [], []
    for tk, cut in rows:
        trial = cur + [(tk, cut)]
        t0, t1 = min(c for _, c in trial) - LOOKBACK_H * 3600, max(c for _, c in trial) + 3600
        hrs = (t1 - t0) // 3600 + 2
        if cur and (len(trial) * hrs > MAX_CANDLES or len(trial) > MAX_TICKERS):
            batches.append(cur)
            cur = [(tk, cut)]
        else:
            cur = trial
    if cur:
        batches.append(cur)
    out, ok = {}, 0
    for b in batches:
        t0, t1 = min(c for _, c in b) - LOOKBACK_H * 3600, max(c for _, c in b) + 3600
        d = _get("/markets/candlesticks", dict(market_tickers=",".join(t for t, _ in b), start_ts=t0, end_ts=t1,
                                                period_interval=60))
        if d is None:
            continue
        ok += 1
        for x in d.get("markets") or []:
            out[x.get("market_ticker")] = sorted((c for c in (x.get("candlesticks") or []) if c.get("end_period_ts")),
                                                 key=lambda c: c["end_period_ts"])
    return out if (ok or not batches) else None


def pre_cut(tks, cut, CS, steps=MAX_STEPS):
    ends = sorted({c["end_period_ts"] for t in tks for c in (CS.get(t) or []) if c["end_period_ts"] <= cut}, reverse=True)
    stepped = 0
    for e_ in ends[:steps + 1]:
        rng = 0.0
        for t in tks:
            c = next((x for x in (CS.get(t) or []) if x["end_period_ts"] == e_), None)
            if c:
                rng = max(rng, (_cd(c, "price", "high_dollars") or 0) - (_cd(c, "price", "low_dollars") or 0))
        if rng >= INPLAY_RANGE:
            stepped += 1
            continue
        return e_, stepped
    return None


def px_at(tk, e_, CS):
    cs = CS.get(tk) or []
    c = next((x for x in reversed(cs) if x["end_period_ts"] <= e_), None)
    if c is None:
        return None, None, 0.0
    last = _cd(c, "price") or _cd(c, "price", "previous_dollars")
    p, s = _side_price(_cd(c, "yes_bid"), _cd(c, "yes_ask"), last)
    vol = sum((_f(x.get("volume_fp")) or 0) for x in cs if e_ - LOOKBACK_H * 3600 < x["end_period_ts"] <= e_)
    return p, s, vol


# ---------------------------------------------------------------- games
def games(events, ix, now=None, log=None):
    """events: normalized ESPN events (ncaaf_data.norm_event). -> ({eid: rec}, meta).
    rec = {tk, pre (bool), at_iso, p_home, c_home, c_away, sum, sp, vol, thin, stepped}."""
    log = log or (lambda s: None)
    now = now or datetime.now(UTC)
    nowts = int(now.timestamp())
    for k in STATS:
        STATS[k] = 0
    meta = dict(ok=False, why="", mark=MARK, source=API, series=[S_GAME], read_utc=now.strftime("%Y-%m-%d %H:%M UTC"),
                games=0, events=0, matched=0, priced=0, pre=0, now=0, thin=0, unmatched=[], unusable=[], unnamed=[])
    G = [e for e in events if _ts(e.get("date"))]
    meta["games"] = len(G)
    if not G:
        meta.update(ok=True, why="no games to price")
        return {}, meta
    since = min(_ts(e["date"]) for e in G) - 2 * 86400
    gm = markets(S_GAME, since)
    if gm is None:
        meta["why"] = "Kalshi unreachable (game markets)"
        meta.update(req=STATS["req"], fail=STATS["fail"], r429=STATS["r429"])
        return {}, meta
    meta["ok"] = True
    byev = defaultdict(list)
    for m in gm:
        byev[m.get("event_ticker") or ""].append(m)
    evs, unnamed = [], set()
    for tk, rows in byev.items():
        d = ev_date(tk)
        if not d:
            continue
        side = {}
        for m in sorted(rows, key=lambda m: m.get("created_time") or ""):
            tid = who(ix, m.get("yes_sub_title"), m["ticker"].rsplit("-", 1)[-1])
            if tid:
                side[tid] = m
            else:
                unnamed.add(m.get("yes_sub_title"))
        if len(side) == 2:
            evs.append(dict(tk=tk, date=d, side=side, pair=frozenset(side)))
    meta["events"] = len(evs)
    meta["unnamed"] = sorted(x for x in unnamed if x)[:40]
    by_pair = defaultdict(list)
    for ev in evs:
        by_pair[ev["pair"]].append(ev)
    used, jobs = set(), []
    for e in G:
        st = _ts(e["date"])
        d_et = datetime.fromtimestamp(st, tz=UTC).astimezone(C.ET).date() if C.ET else datetime.fromtimestamp(st, tz=UTC).date()
        best = None
        for ev in by_pair.get(frozenset((e["h"]["id"], e["a"]["id"])), []):
            if ev["tk"] in used:
                continue
            dd = abs((d_et - ev["date"]).days)
            if dd <= DATE_WINDOW and (best is None or dd < best[0]):
                best = (dd, ev)
        if not best:
            meta["unmatched"].append(f"{e['a']['abbr']}@{e['h']['abbr']}")
            continue
        ev = best[1]
        used.add(ev["tk"])
        meta["matched"] += 1
        gmk = [ev["side"][e["h"]["id"]], ev["side"][e["a"]["id"]]]
        started = e["status"]["state"] in ("in", "post") or st <= nowts \
            or any(m.get("status") not in ("active", "open", "initialized", "unopened") for m in gmk)
        jobs.append(dict(e=e, ev=ev, gmk=gmk, cut=min(st, nowts) if started else None))
    CS = {}
    if any(j["cut"] for j in jobs):
        CS = prefetch([([m["ticker"] for m in j["gmk"]], j["cut"]) for j in jobs if j["cut"]])
        if CS is None:
            meta["candles_failed"] = True
            CS = {}
    recs = {}
    for j in jobs:
        e, gmk = j["e"], j["gmk"]
        rec = dict(tk=j["ev"]["tk"], pre=bool(j["cut"]), stepped=0)
        if j["cut"]:
            pc = pre_cut([m["ticker"] for m in gmk], j["cut"], CS)
            if not pc:
                meta.setdefault("nocandle", 0)
                meta["nocandle"] = meta.get("nocandle", 0) + 1
                continue
            e_, rec["stepped"] = pc
            ph, sh, vh = px_at(gmk[0]["ticker"], e_, CS)
            pa, sa, va = px_at(gmk[1]["ticker"], e_, CS)
            rec["at_iso"] = datetime.fromtimestamp(e_, tz=UTC).strftime("%Y-%m-%dT%H:%MZ")
        else:
            ph, sh, vh = px_now(gmk[0])
            pa, sa, va = px_now(gmk[1])
            rec["at_iso"] = now.strftime("%Y-%m-%dT%H:%MZ")
        if ph is None or pa is None:
            continue
        sm = ph + pa
        if not (0.90 <= sm <= 1.10):
            meta["unusable"].append(f"{e['a']['abbr']}@{e['h']['abbr']} ({round(100 * sm)}¢)")
            continue
        sp = max(x for x in (sh, sa, 0.0) if x is not None)
        vol = max(vh, va)
        rec.update(p_home=round(ph / sm, 4), c_home=round(100 * ph), c_away=round(100 * pa), sum=round(100 * sm),
                   sp=round(100 * sp), vol=int(round(vol)), thin=bool(vol < THIN_VOL or sp > THIN_SPREAD))
        recs[e["eid"]] = rec
        meta["priced"] += 1
        meta["pre" if rec["pre"] else "now"] += 1
        meta["thin"] += 1 if rec["thin"] else 0
    meta.update(req=STATS["req"], fail=STATS["fail"], r429=STATS["r429"])
    log(f"Kalshi games: {meta['priced']} priced of {meta['games']} ({meta['pre']} pre-kickoff, {meta['now']} books, "
        f"{meta['thin']} thin), {len(meta['unmatched'])} unmatched, {meta['req']} calls")
    return recs, meta


# ---------------------------------------------------------------- futures
def _season_event(ms, season):
    """The event of a futures series for `season`: its ticker suffix is the season's end year (KXNCAAF-27 = 2026-27) or the
    season year (KXNCAAFPLAYOFF-26, KXNCAAFSEC-26); the newest event with open markets wins."""
    by = defaultdict(list)
    for m in ms or []:
        by[m.get("event_ticker") or ""].append(m)
    cands = []
    for ev, rows in by.items():
        suf = ev.rsplit("-", 1)[-1]
        if suf.isdigit() and int(suf) in (season % 100, (season + 1) % 100):
            if any(m.get("status") in ("active", "open") for m in rows):
                cands.append((int(suf), ev, rows))
    if not cands:
        return None, []
    cands.sort()
    # national title uses the end year; playoff/conference use the start year — both resolve to the single open event
    return cands[-1][1], cands[-1][2]


def futures(ix, season):
    """-> ({'title': {tid: rec}, 'playoff': {tid: rec}, 'conf': {CONF: {tid: rec}}}, meta). rec = {p, sp, vol, thin, tk}."""
    for k in STATS:
        STATS[k] = 0
    F, meta = {"title": {}, "playoff": {}, "conf": {}}, dict(ok=False, why="", read_utc=C.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                                                           events={}, unnamed=[])
    series = [("title", FUT["title"], None), ("playoff", FUT["playoff"], None)] + [("conf", s, ck) for ck, s in CONF_SERIES.items()]
    any_ok, unnamed = False, set()
    for kind, s, ck in series:
        ms = markets(s, status="open")
        if ms is None:
            continue
        any_ok = True
        ev, rows = _season_event(ms, season)
        if not ev:
            continue
        meta["events"][ck or kind] = ev
        out = {}
        for m in rows:
            tid = who(ix, m.get("yes_sub_title"), m["ticker"].rsplit("-", 1)[-1])
            if not tid:
                unnamed.add(m.get("yes_sub_title"))
                continue
            p, sp, vol = px_now(m)
            if p is None:
                continue
            out[tid] = dict(p=round(p, 4), sp=round(100 * sp) if sp is not None else None, vol=int(round(vol)),
                            thin=bool(vol < THIN_VOL or (sp is not None and sp > THIN_SPREAD) or sp is None), tk=m["ticker"])
        if kind == "conf":
            F["conf"][ck] = out
        else:
            F[kind] = out
    meta["ok"] = any_ok
    meta["why"] = "" if any_ok else "Kalshi unreachable (futures)"
    meta["unnamed"] = sorted(x for x in unnamed if x)[:30]
    meta.update(req=STATS["req"], fail=STATS["fail"], r429=STATS["r429"])
    return F, meta


def main():
    import ncaaf_data as D
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=C.season_of())
    ap.add_argument("--week", type=int)
    a = ap.parse_args()
    cw = D.current_week(a.season)
    wk = a.week or cw["week"]
    evs = D.week_events(a.season, 2, wk)
    allev = D.season_events(a.season, post=False)
    reg = D.registry(a.season, allev)
    seen = dict(reg["teams"])
    for e in allev:
        for s in ("h", "a"):
            seen.setdefault(e[s]["id"], e[s])
    ix = index(seen)
    recs, meta = games(evs, ix, log=print)
    for e in evs:
        r = recs.get(e["eid"])
        txt = (f"{e['h']['abbr']} {C.pct1(r['p_home'])} ({'pre-kickoff' if r['pre'] else 'book'}, {r['c_home']}¢/{r['c_away']}¢, "
               f"{r['vol']:,} contracts{', thin' if r['thin'] else ''})") if r else "—"
        print(f"  {e['a']['abbr']:>6} @ {e['h']['abbr']:<6} {txt}")
    print("  unmatched:", ", ".join(meta["unmatched"]) or "none", "· unnamed:", ", ".join(meta["unnamed"][:10]) or "none")
    F, fm = futures(ix, a.season)
    print(f"[ncaaf_kalshi futures] events {fm['events']} · unnamed {fm['unnamed'][:10]} · {fm['req']} calls")
    for kind in ("title", "playoff"):
        top = sorted(F[kind].items(), key=lambda kv: -kv[1]["p"])[:8]
        print(f"  {kind}: " + ", ".join(f"{seen[t]['abbr']} {C.pct0(r['p'])}" for t, r in top))
    for ck, d in F["conf"].items():
        top = sorted(d.items(), key=lambda kv: -kv[1]["p"])[:4]
        print(f"  {ck}: " + ", ".join(f"{seen[t]['abbr']} {C.pct0(r['p'])}" for t, r in top))


if __name__ == "__main__":
    main()
