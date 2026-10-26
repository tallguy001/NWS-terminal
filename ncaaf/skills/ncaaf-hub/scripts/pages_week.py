#!/usr/bin/env python3
"""pages_week — the league schedule, one view per week (#W1 … #W15, #WP the postseason): header with the week strip and a
summary, then every FBS game grouped by day and slot (Central time): kickoff, matchup, TV, the result or the HOUSE MODEL,
the line (closing on a final, DraftKings before), against the line (cover, or house − market gap), Kalshi."""
import sys
from collections import OrderedDict

sys.dont_write_bytecode = True
import hub_common as HC  # noqa: E402

C = HC.C
E = HC.E
DASH, DOT, EN, MINUS, HM = HC.DASH, HC.DOT, HC.EN, HC.MINUS, HC.HM


def slot(X, e):
    d = C.parse_iso(e["date"])
    if not d:
        return "TBA", "Date TBA"
    if not e.get("time_valid", True):
        de = d.astimezone(C.ET) if C.ET else d
        return f"{de.strftime('%A')} · time TBA", de.strftime("%a %b ") + str(de.day)
    c = C.to_ct(d)
    day = c.strftime("%A")
    if day == "Saturday":
        hr = c.hour
        nm = "Saturday early" if hr < 14 else ("Saturday afternoon" if hr < 18 else "Saturday night")
        if hr >= 21:
            nm = "Saturday late night"
        return nm, c.strftime("%a %b ") + str(c.day)
    if hr_night(c):
        return f"{day} night", c.strftime("%a %b ") + str(c.day)
    return day, c.strftime("%a %b ") + str(c.day)


def hr_night(c):
    return c.hour >= 17


def render(X, w):
    if w == "P":
        evs = sorted([e for e in X.ev if e["st"] == 3], key=lambda e: (e["date"] or "", e["eid"]))
        title, rng, key = "Postseason", "bowls and the College Football Playoff", "wP"
    else:
        evs = sorted([e for e in X.ev if e["st"] == 2 and e["week"] == w], key=lambda e: (e["date"] or "", e["eid"]))
        title, rng, key = f"Week {w}", X.week_range(w), f"wk{w}"
    fin = [e for e in evs if e["status"]["completed"]]
    state = "Complete" if evs and len(fin) == len(evs) else ("Upcoming" if not fin else f"{len(fin)} of {len(evs)} final")
    pills = []
    for c in X.reg_weeks:
        wk = c["week"]
        cls = "done" if wk < X.week else ("now" if wk == X.week else "")
        on = wk == w
        pills.append(f'<a class="wk-p {cls}{" on" if on else ""}" href="#W{wk}" title="Week {wk}, {E(c.get("detail") or "")}"'
                     f'{" aria-current=" + chr(34) + "page" + chr(34) if on else ""}>{wk}</a>')
    if any(e["st"] == 3 for e in X.ev):
        pills.append(f'<a class="wk-p{" on" if w == "P" else ""}" href="#WP" title="Postseason">P</a>')
    # summary
    summ = []
    lined = [e for e in fin if e.get("cl") and e["cl"].get("spread") not in (None, 0)]
    if fin:
        fsu = sum(1 for e in lined if (e["cl"]["spread"] < 0) == (e["h"]["score"] > e["a"]["score"]))
        ats = [((e["h"]["score"] - e["a"]["score"]) + e["cl"]["spread"], e["cl"]["spread"] < 0) for e in lined]
        aw = sum(1 for x, fh in ats if abs(x) > 1e-9 and (x > 0) == fh)
        al = sum(1 for x, fh in ats if abs(x) > 1e-9 and (x > 0) != fh)
        summ.append(f"{len(fin)} final {DOT} favorites {fsu}{EN}{len(lined) - fsu} straight up, {aw}{EN}{al} against the closing line")
        def upset(e):
            w_ = X.winner(e)
            if not w_:
                return False
            los = e["a"] if w_ == e["h"]["id"] else e["h"]
            win = e["h"] if los is e["a"] else e["a"]
            return bool(los.get("rank")) and (not win.get("rank") or win["rank"] > los["rank"])
        ups = sum(1 for e in fin if upset(e))
        if ups:
            summ.append(f"{ups} ranked teams beaten by lower-ranked or unranked teams")
    pre = [e for e in evs if not e["status"]["completed"]]
    if pre:
        posted = [e for e in pre if (e.get("odds") or {}).get("spread") is not None]
        gaps = [e for e in posted if abs(e["hm"]["line"] + e["odds"]["spread"]) >= 3]
        summ.append(f"{len(pre)} to play {DOT} DraftKings lines on {len(posted)}"
                    + (f" {DOT} {len(gaps)} where the {HM} line is 3+ points off the market" if posted else ""))
    head = ('  <div class="wk-head">\n'
            f'    <div class="wk-k">{X.season} {"postseason" if w == "P" else "regular season"} {DOT} FBS schedule</div>\n'
            f'    <div class="wk-t">{title}<small>{E(rng)} {DOT} {len(evs)} games {DOT} {state}</small></div>\n'
            f'    <nav class="wk-strip" aria-label="Weeks">{"".join(pills)}</nav>\n'
            f'    <p class="wk-sum">{" · ".join(summ) if summ else "No FBS games listed"}</p>\n  </div>')
    groups = OrderedDict()
    for e in evs:
        s, day = slot(X, e)
        groups.setdefault((s, day), []).append(e)
    rows, nav = [], []
    for i, ((s, day), gl) in enumerate(groups.items()):
        sid = f"{key}-s{i + 1}"
        rows.append(("grp", f'<span id="{sid}">{E(s)}</span><small> {DOT} {E(day)} {DOT} {len(gl)} game{"s" if len(gl) != 1 else ""}</small>'))
        rows += [("row", e, "wk-g") for e in gl]
        nav.append((sid, s.replace("Saturday", "Sat").replace(" · time TBA", " TBA")))

    def kick(e):
        t_, day, utc = X.when(e)
        st = X.state(e)
        if st in ("live", "underway"):
            t_ = e["status"].get("short") or "Under way"
        tv = E(" / ".join(e["tv"])) if e["tv"] else ""
        return f'<b>{E(t_)}</b><span class="l2">{E(day)}{(" · " + E(utc)) if utc else ""}</span>' + (f'<span class="l2 alt alt-tv">{tv}</span>' if tv else "")

    def matchup(e):
        w_ = X.winner(e)
        out = []
        for s, pre in (("a", ""), ("h", "vs" if e["neutral"] else "at")):
            side = e[s]
            tid = side["id"]
            nm = E(X.loc(tid, side))
            rk = X.rank_html(tid) if tid in X.teams else ""
            sc = "" if side["score"] is None or not e["status"]["completed"] else f' <span class="wm-s{" win" if w_ == tid else ""}">{side["score"]}</span>'
            inner = f'<b>{rk}{nm}</b><small>{E(X.record(tid)) if tid in X.teams else "FCS"}</small>'
            if tid in X.teams:
                inner = f'<a class="tl2" href="#{E(X.key(tid))}" style="display:contents">{inner}</a>'
            out.append(f'<div class="wm-t"><i>{pre}</i>{HC.chip(tid, side.get("abbr"))}<span class="wm-n">{inner}</span>{sc}</div>')
        v = e["venue"]
        vl = ", ".join(x for x in (v.get("name"), v.get("city"), v.get("state")) if x)
        tags = []
        if e["neutral"]:
            tags.append("neutral site")
        if X.is_title(e):
            tags.append("conference championship")
        elif e["conf"]:
            tags.append("conference")
        if e["notes"] and not X.is_title(e):
            tags.append(e["notes"][0])
        return (f'<div class="wm">{"".join(out)}<span class="l2 v-l">{E(vl)}{(" · " + E(" · ".join(tags))) if tags else ""}</span>'
                f'<span class="l2 v-s">{E(", ".join(x for x in (v.get("city"), v.get("state")) if x))}</span></div>')

    def res(e):
        st = X.state(e)
        gl = X.game_link(e, "Game page ›", "wk-a")
        if st == "final":
            w_ = X.winner(e)
            ws = e["h"] if w_ == e["h"]["id"] else e["a"]
            ls = e["a"] if ws is e["h"] else e["h"]
            m, sub = X.hm_txt(e, short=True)
            return (f'<b>{E(X.abbr(w_, ws))} by {ws["score"] - ls["score"]}</b>'
                    + (f'<span class="l2">pregame {HM} {m}</span>' if m != DASH else "") + (f'<span class="l2">{gl}</span>' if gl else ""))
        if st in ("live", "underway"):
            return f'<b>Under way</b>' + (f'<span class="l2">{gl}</span>' if gl else "")
        if st == "off":
            return E(e["status"].get("detail") or "Postponed")
        m, sub = X.hm_txt(e)
        mk = e.get("odds") or {}
        toss = ""
        if mk.get("spread") is not None and (e["hm"]["p"] >= 0.5) != (mk["spread"] < 0) and abs(mk["spread"]) > 0.4:
            toss = f'<span class="l2"><span class="flag">house and market favor different sides</span></span>'
        return f'<b>{m}</b><span class="l2">{HM} {DOT} {sub}</span>{toss}' + (f'<span class="l2">{gl}</span>' if gl else "")

    def line(e):
        o = X.line_of(e)
        if not o or o.get("spread") is None:
            return f'{DASH}<span class="l2">{"no line" if e["status"]["completed"] else "not posted"}</span>'
        tt = f'total {C.fmt(o["total"])}' if o.get("total") else ""
        mp = o.get("p_h")
        extra = ""
        if mp is not None and not e["status"]["completed"]:
            fav, pf = (e["h"], mp) if mp >= 0.5 else (e["a"], 1 - mp)
            extra = f' {DOT} {E(X.abbr(fav["id"], fav))} {C.pct0(pf)}'
        return f'{E(X.mk_txt(e, o))}<span class="l2">{tt}{extra}</span>'

    def vsl(e):
        if e["status"]["completed"]:
            cv = X.cover(e)
            return (f'{E(cv[0])}' + (f'<span class="l2">{E(cv[1])}</span>' if cv[1] else "")) if cv else DASH
        o = e.get("odds") or {}
        if o.get("spread") is None:
            return DASH
        gap = e["hm"]["line"] + o["spread"]           # house home margin − market home margin
        side = e["h"] if gap > 0 else e["a"]
        cls = ' class="gap"' if abs(gap) >= 3 else ""
        return f'<b{cls}>{C.fmt(abs(gap))}</b><span class="l2">house leans {E(X.abbr(side["id"], side))}</span>'

    def kal(e):
        k = X.kal_txt(e)
        return f'{k[0]}<span class="l2">{E(k[1])}</span>' if k else DASH
    cols = [
        {"g": "Game", "h": "Kickoff · CT", "c": "l", "f": kick},
        {"g": "Game", "h": "Matchup", "c": "l", "f": matchup},
        {"g": "Game", "h": "TV", "c": "l wrap", "d": 1, "f": lambda e: E(" / ".join(e["tv"])) or ("TBA" if not e["status"]["completed"] else DASH)},
        {"g": "Result or HOUSE MODEL", "gs": "Result / house", "h": "Winner · P(win)", "c": "wres", "f": res},
        {"g": "Line", "h": "Closing or DraftKings", "d": 4, "f": line, "t": "finals: the closing line (ESPN core odds); upcoming: DraftKings via ESPN"},
        {"g": "Against the line", "gs": "vs line", "h": "Cover · gap", "d": 3, "f": vsl,
         "t": "finals: who covered and the total; upcoming: the HOUSE MODEL line minus the market's, highlighted at 3+ points"},
        {"g": "Kalshi", "h": "Win", "d": 2, "f": kal, "t": "Kalshi game market, no-vig; a started game shows its pre-kickoff price"},
    ]
    tb = HC.rb_table(cols, rows, 4, "wkb")
    note = f'{E(rng)} {DOT} ESPN kickoffs and TV {DOT} {HM} vs DraftKings'
    sec = HC.sec(key, f"{title} games", note)
    body = (f'{sec}    <div class="brd" data-games="{len(evs)}">\n      <div class="brd-b">{tb}</div>\n'
            f'      <div class="brd-f">Finals: the closing line from ESPN’s core odds (DraftKings, else ESPN BET) and the walk-forward {HM} '
            f'pregame line. Upcoming: {HM} win chance, line and total; DraftKings spread, total and no-vig moneyline. Kalshi on this week’s '
            f'and last week’s games. Every FBS game is listed, FCS opponents included.</div>\n    </div>\n  </section>')
    status = f"{title} {DOT} {len(evs)} games {DOT} {state}"
    return head + "\n" + body, [list(n) for n in nav], status
