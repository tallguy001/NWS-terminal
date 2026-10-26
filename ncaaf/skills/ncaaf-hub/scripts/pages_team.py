#!/usr/bin/env python3
"""pages_team — one page per FBS team (#<KEY>): hero (record, conference place, AP rank, HOUSE MODEL projected wins on the
schedule's axis, next-game bug with house / DraftKings / Kalshi and the stakes), snapshot, conference standings, season odds
(ladder + seed distribution), schedule and results, ratings and the percentile profile, record check (computed reads) and
team stats. Every number from the pull; reads are rule-based sentences over those numbers."""
import sys

sys.dont_write_bytecode = True
import hub_common as HC  # noqa: E402

C = HC.C
E = HC.E
DASH, DOT, EN, MINUS, HM = HC.DASH, HC.DOT, HC.EN, HC.MINUS, HC.HM


def conf_order(X, ck, members=None):
    mem = members or X.confs[ck]["members"]

    def k(t):
        r = X.rec[t]
        cg = r["cw"] + r["cl"]
        return (-(r["cw"] / cg if cg else 0), -r["cw"], -(r["w"] / max(1, r["w"] + r["l"])), -X.rat[t]["net"])
    return sorted(mem, key=k)


def conf_place(X, tid):
    t = X.teams[tid]
    ck = t["conf"]
    if ck == "IND":
        return None, None
    cf = X.confs[ck]
    if t.get("div") and cf.get("divs"):
        order = conf_order(X, ck, cf["divs"][t["div"]])
        return order.index(tid) + 1, f'{t["div"]} Division'
    order = conf_order(X, ck)
    return order.index(tid) + 1, cf["short"]


def render(X, tid):
    t = X.teams[tid]
    S = X.sim[tid]
    nav, parts = [], []
    parts.append(hero(X, tid))
    parts.append(snap(X, tid))
    parts.append(two_line(X, tid))
    if t["conf"] != "IND":
        parts.append(standings(X, tid)); nav.append(("standings", "Standings"))
    parts.append(odds(X, tid)); nav.append(("odds", "Odds"))
    parts.append(schedule(X, tid)); nav.append(("schedule", "Schedule"))
    parts.append(ratings(X, tid)); nav.append(("ratings", "Ratings"))
    parts.append(record_check(X, tid)); nav.append(("record", "Record check"))
    parts.append(team_stats(X, tid)); nav.append(("teamstats", "Team stats"))
    pl, lab = conf_place(X, tid)
    status = f"{X.record(tid)}" + (f" {DOT} {C.ordn(pl)} {lab}" if pl else f" {DOT} Independent") + (f" {DOT} AP No. {X.ap[tid]}" if tid in X.ap else "")
    return "\n".join(parts), [list(n) for n in nav], status


# ============================================================================ hero
def n_reg_games(X, tid):
    return sum(1 for e in X.by_team[tid] if e["st"] == 2 and not X.is_title(e) and "CANCEL" not in (e["status"].get("name") or ""))


def hero(X, tid):
    t = X.teams[tid]
    S = X.sim[tid]
    r = X.rec[tid]
    ng = n_reg_games(X, tid)
    pl, lab = conf_place(X, tid)
    nxt = X.next_game(tid)
    sub = ("<b>House team</b> " + DOT + " " if HC.HOUSE["id"] == tid else "") + f"{X.season} season {DOT} {E(X.conf_short(t['conf']))}"
    if t.get("div"):
        sub += f" ({E(t['div'])})"
    if nxt:
        opp = nxt["a"] if nxt["h"]["id"] == tid else nxt["h"]
        at = "vs" if nxt["neutral"] else ("at" if nxt["a"]["id"] == tid else "vs")
        sub += f" {DOT} {E(X.week_label(nxt))} {at} {E(X.loc(opp['id'], opp))}"
    ly = X.last.get(tid)
    if ly:
        sub += f'<br><b>{X.season - 1}</b>: {ly["w"]}{EN}{ly["l"]}' + (f" {DOT} {E(ly['end'])}" if ly.get("end") else "")
    lead = []
    if pl:
        lead.append(f"{C.ordn(pl)} in the {E(lab)}")
    if tid in X.ap:
        lead.append(f"AP No. {X.ap[tid]}")
    if tid in X.cfp:
        lead.append(f"CFP No. {X.cfp[tid]}")
    # projected-wins band on the schedule's axis
    ax = max(ng, 1)
    lo, hi, mean = S["w10"], S["w90"], S["w"]
    left = 100 * lo / ax
    width = max(1.5, 100 * (hi - lo) / ax)
    lyw = ly["w"] if ly else None
    ticks = sorted({0, ax, round(ax / 3), round(2 * ax / 3), int(round(mean))})
    band = (f'<div class="wband" role="img" aria-label="HOUSE MODEL projected regular-season wins {C.fmt(mean)}, 10th to 90th percentile {lo} to {hi} on a {ax}-game axis">'
            f'<div class="wb-track"><span class="wb-axis"></span><span class="wb-band" style="left:{left:.1f}%;width:{width:.1f}%"></span>'
            + (f'<span class="wb-ly" style="left:{min(100, 100 * lyw / ax):.1f}%" title="{X.season - 1}: {lyw} wins"></span>' if lyw is not None else "")
            + f'<span class="wb-mean" style="left:{100 * mean / ax:.1f}%"></span></div>'
            f'<div class="wb-ticks">' + "".join(f'<span style="left:{100 * v / ax:.1f}%">{v}</span>' for v in ticks) + '</div>'
            f'<div class="wb-cap"><span>{HM} regular-season wins, 10th–90th percentile <b>{lo}–{hi}</b> {DOT} mean <b>{C.fmt(mean)}</b> of {ax}</span>'
            + (f'<span><i>▼</i> {X.season - 1}: {lyw} wins (all games)</span>' if lyw is not None else "") + '</div></div>')
    chase = (f'<div class="chase">{HM} <b>{C.fmt(mean)}</b> wins {DOT} CFP <b>{C.pct1(S["p_cfp"])}</b> {DOT} '
             + (f'{E(X.conf_short(t["conf"]))} title {C.pct1(S["p_conf"])} {DOT} ' if t["conf"] != "IND" else "")
             + f'national title {C.pct1(S["p_champ"])} {DOT} bowl eligible {C.pct0(S["p_bowl"])}.</div>')
    loc, nick = E(t["loc"]), E(t["nick"] or "")
    h = ['  <div class="hero">', '    <div class="hero-l">',
         f'      <div class="hero-team">{loc} <span class="brew">{nick}</span></div>',
         f'      <div class="hero-sub">{sub}</div>',
         f'      <div class="streakrow"><div class="streaknum">{E(X.record(tid))}</div><div class="lead">{" · ".join(lead) or E(X.conf_short(t["conf"]))}</div></div>',
         f'      {band}', f'      {chase}', '    </div>', game_bug(X, tid, nxt), '  </div>']
    return "\n".join(h)


def game_bug(X, tid, e):
    if not e:
        e = X.last_game(tid)
        if not e:
            return '    <aside class="gb" aria-label="Next game"><div class="gb-h">Season<span>complete</span></div></aside>'
    me = e["h"] if e["h"]["id"] == tid else e["a"]
    op = e["a"] if me is e["h"] else e["h"]
    home = me is e["h"]
    t_, day, utc = X.when(e)
    st = X.state(e)
    rows = []
    for side, where in ((me, "neutral" if e["neutral"] else ("home" if home else "away")),
                        (op, "neutral" if e["neutral"] else ("away" if home else "home"))):
        sid = side["id"]
        sc = "" if side["score"] is None or st == "pre" else str(side["score"])
        recs = (X.record(sid) if sid in X.teams else "FCS") + f" {DOT} {where}"
        nm = E(X.loc(sid, side))
        nm = f'<a href="#{E(X.key(sid))}" style="color:inherit;text-decoration:none">{nm}</a>' if sid in X.teams and sid != tid else nm
        rows.append(f'<div class="gb-t{" dim" if st == "final" and X.winner(e) != sid else ""}">{HC.chip(sid, side.get("abbr"))}'
                    f'<span class="nm">{X.rank_html(sid)}{nm}<span class="rec">{E(recs)}</span></span><span class="sc">{sc}</span></div>')
    kind = "Conference game" if e["conf"] else ("Conference championship" if X.is_title(e) else "Non-conference game")
    if e["neutral"]:
        kind += " · neutral site"
    meta = [("Kickoff", f"<b>{E(day)}</b> {E(t_)}" + (f" ({E(utc)})" if utc else "")),
            ("Venue", E(", ".join(x for x in (e["venue"].get("name"), e["venue"].get("city"), e["venue"].get("state")) if x))),
            ("TV", E(" / ".join(e["tv"])) or "TBA")]
    hm = e.get("hm") if st != "final" else e.get("hm_pre")
    if hm:
        p = hm["p"] if home else 1 - hm["p"]
        ln = C.line_txt(-hm["line"], X.abbr(e["h"]["id"], e["h"]), X.abbr(e["a"]["id"], e["a"]))
        meta.append(("House", f'{HM} <b>{E(X.abbr(tid))} {C.pct1(p)}</b> to win {DOT} line {E(ln)} {DOT} total {C.fmt(hm["total"])}'
                     + (" (pregame, walk-forward)" if st == "final" else ""), "hmrow"))
    o = X.line_of(e)
    if o and o.get("spread") is not None:
        mkp = o.get("p_h")
        mk = (f'{E(X.mk_txt(e, o))}' + (f" {DOT} total {C.fmt(o['total'])}" if o.get("total") else "")
              + (f" {DOT} {E(X.abbr(tid))} {C.pct1(mkp if home else 1 - mkp)} (moneyline, no-vig)" if mkp is not None else "")
              + f" {DOT} {E(o.get('prov') or 'DraftKings')}" + (" (closing)" if st in ("final", "live") else ""))
        meta.append(("Market", mk))
    else:
        meta.append(("Market", "DraftKings not posted"))
    k = X.kg.get(e["eid"])
    if k:
        pk = k["p_home"] if home else 1 - k["p_home"]
        meta.append(("Kalshi", f'{E(X.abbr(tid))} {C.pct1(pk)} {DOT} {"pre-kickoff" if k.get("pre") else "book"}{" · thin" if k.get("thin") else ""}'))
    stk = (X.sim.get(tid) or {}).get("stakes")
    if stk and stk.get("eid") == e["eid"] and st == "pre":
        cw, cl = stk["cfp"]
        if cw is not None and cl is not None and (cw >= 0.01 or cl >= 0.01):
            meta.append(("Stakes", f'{HM} CFP <b>{C.pct0(cw)} with a win, {C.pct0(cl)} with a loss</b> {DOT} {C.pct0(X.sim[tid]["p_cfp"])} now'))
        else:
            bw, bl = stk["bowl"]
            if bw is not None and bl is not None and 0.02 < X.sim[tid]["p_bowl"] < 0.98:
                meta.append(("Stakes", f'{HM} bowl eligible <b>{C.pct0(bw)} with a win, {C.pct0(bl)} with a loss</b>'))
    gl = X.game_link(e, "Game page ›", "wk-a")
    res = kind if st != "final" else f'{"W" if X.winner(e) == tid else "L"} {X.score_txt(e, tid)} {DOT} Final'
    return ('    <aside class="gb" aria-label="Next game">\n'
            f'      <div class="gb-h">{E(X.week_label(e))}<span>{E(day)}</span></div>\n      ' + "\n      ".join(rows) + "\n"
            f'      <div class="gb-res">{res}</div>\n      <div class="gb-meta">\n'
            + "".join(f'        <div class="{m[2] if len(m) > 2 else ""}"><span class="k">{m[0]}</span><span>{m[1]}</span></div>\n' for m in meta)
            + (f'        <div><span class="k">Page</span><span>{gl}</span></div>\n' if gl else "")
            + '      </div>\n    </aside>')


def snap(X, tid):
    t = X.teams[tid]
    r = X.rec[tid]
    S = X.sim[tid]
    R = X.rat[tid]
    ly = X.last.get(tid)
    cells = [
        ("Record", E(X.record(tid)), f'home {r["hw"]}{EN}{r["hl"]} {DOT} road {r["aw"]}{EN}{r["al"]}'
         + (f' {DOT} neutral {r["nw"]}{EN}{r["nl"]}' if r["nw"] + r["nl"] else "")
         + (f' {DOT} conference {r["cw"]}{EN}{r["cl"]}' if t["conf"] != "IND" else "")
         + f' {DOT} points {C.signed(r["pf"] - r["pa"], 0)} ({r["pf"]}{EN}{r["pa"]})'),
        ("Proj W", C.fmt(S["w"]), f'10th–90th {S["w10"]}–{S["w90"]} {DOT} {HM}'),
        ("Power", f'{C.signed(R["net"])}<small> pts</small>', f'{C.ordn(R["rk"])} of {len(X.teams)} {DOT} {HM}'),
        ("P(CFP)", C.pct1(S["p_cfp"]), f'bye {C.pct1(S["p_bye"])} {DOT} title {C.pct1(S["p_champ"])} {DOT} {HM}'),
        (("Conf title" if t["conf"] != "IND" else "Bowl eligible"),
         (C.pct1(S["p_conf"]) if t["conf"] != "IND" else C.pct0(S["p_bowl"])),
         (f'title game {C.pct1(S["p_ccg"])} {DOT} {HM}' if t["conf"] != "IND" else f'six wins {DOT} {HM}')),
        ("Last season", f'{ly["w"]}{EN}{ly["l"]}' if ly else DASH, E(ly.get("end") or "") if ly else "not FBS"),
    ]
    return '  <div class="snap">' + "".join(f'<div class="cell"><div class="k">{k}</div><div class="v">{v}</div><div class="note">{n}</div></div>'
                                           for k, v, n in cells) + "</div>"


# ============================================================================ the two-number rule
def _gb(a, b):
    """games between two conference records (a ahead of b when positive)."""
    return ((a["cw"] - b["cw"]) + (b["cl"] - a["cl"])) / 2.0


def conf_games_left(X, tid):
    fb = {t: v["conf"] for t, v in X.teams.items()}
    return sum(1 for e in X.by_team[tid] if e["st"] == 2 and not e["status"]["completed"] and e["conf"]
               and fb.get(e["h"]["id"]) == fb.get(e["a"]["id"]) and not X.is_title(e) and X.state(e) != "off")


def two_numbers(X, tid):
    """(conference-race sentence, CFP-cut sentence): the operator's two-number rule, college form."""
    t = X.teams[tid]
    ck = t["conf"]
    conf_s = None
    if ck != "IND":
        cf = X.confs[ck]
        if t.get("div") and cf.get("divs"):
            order, cut, where = conf_order(X, ck, cf["divs"][t["div"]]), 1, f'{t["div"]} Division lead'
        else:
            order, cut, where = conf_order(X, ck), 2, "title-game line"
        pos = order.index(tid) + 1
        me = X.rec[tid]
        left = conf_games_left(X, tid)
        if pos <= cut and len(order) > cut:
            o = order[cut]
            g = _gb(me, X.rec[o])
            conf_s = (f'{E(cf["short"])}: in the {"division lead" if cut == 1 else "title game today"} ({E(X.conf_record(tid))}), '
                      + (f'{C.fmt(g)} game{"s" if g != 1 else ""} ahead of {E(X.loc(o))} ({E(X.conf_record(o))})' if g > 0
                         else f'tied with {E(X.loc(o))} ({E(X.conf_record(o))}) on record')
                      + f' {DOT} {left} conference game{"s" if left != 1 else ""} left')
        else:
            c = order[cut - 1]
            g = _gb(X.rec[c], me)
            conf_s = (f'{E(cf["short"])}: {C.fmt(g)} game{"s" if g != 1 else ""} behind the {where} '
                      f'({E(X.loc(c))}, {E(X.conf_record(c))}) at {E(X.conf_record(tid))}' if g > 0 else
                      f'{E(cf["short"])}: level with {E(X.loc(c))} ({E(X.conf_record(c))}) at the {where}, behind on the order')
            conf_s += f' {DOT} {left} conference game{"s" if left != 1 else ""} left'
    if X.cfp:
        r = X.cfp.get(tid)
        basis = f'the committee’s ranking ({E((X.rk.get("cfp") or {}).get("week") or "")})'
    else:
        order = X.today.get("rank") or []
        r = order.index(tid) + 1 if tid in order else None
        basis = f'the {HM} committee proxy (the committee ranks from Nov 3)'
    if r is None:
        cfp_s = f'CFP: outside the top 25 of {basis}'
    elif r <= 12:
        cfp_s = f'CFP: No. {r} in {basis} — {12 - r} place{"s" if 12 - r != 1 else ""} inside the 12-team cut, before automatic bids'
    else:
        cfp_s = f'CFP: No. {r} in {basis} — {r - 12} place{"s" if r - 12 != 1 else ""} outside the 12-team cut, before automatic bids'
    return conf_s, cfp_s


def two_line(X, tid):
    a, b = two_numbers(X, tid)
    parts = [x for x in (a, b) if x]
    sep = ' <span class="tn-sep">·</span> '
    return f'  <div class="paper tn-p"><p class="tn-line"><b>Two numbers.</b> {sep.join(parts)}.</p></div>'


# ============================================================================ standings
def standings(X, tid):
    t = X.teams[tid]
    ck = t["conf"]
    cf = X.confs[ck]
    return "\n".join([HC.sec("standings", f'{E(cf["short"])} standings', f'conference record first {DOT} {HM} odds {DOT} Kalshi champion price'),
                      conf_board(X, ck, highlight=tid), "  </section>"])


def conf_board(X, ck, highlight=None):
    cf = X.confs[ck]
    S = X.sim
    rows = []
    if cf.get("divs") and len(cf["divs"]) == 2:
        for dv, mem in cf["divs"].items():
            rows.append(("grp", f"{E(dv)} Division"))
            rows += [("row", tt, "us" if tt == highlight else "") for tt in conf_order(X, ck, mem)]
    else:
        rows = [("row", tt, "us" if tt == highlight else "") for tt in conf_order(X, ck)]
    order = [r[1] for r in rows if r[0] == "row"]
    cols = [
        {"g": "Team", "h": "#", "c": "rkc", "f": lambda tt: str(order.index(tt) + 1)},
        {"g": "Team", "h": "Team", "c": "l", "f": lambda tt: X.team_cell(tt)},
        {"g": "Conference", "gs": "Conf", "h": "W–L", "f": lambda tt: f'<b>{E(X.conf_record(tt))}</b>', "sk": lambda tt: X.rec[tt]["cw"] - X.rec[tt]["cl"]},
        {"g": "Overall", "h": "W–L", "f": lambda tt: E(X.record(tt)), "sk": lambda tt: X.rec[tt]["w"] - X.rec[tt]["l"]},
        {"g": "Overall", "h": "PF", "d": 4, "f": lambda tt: str(X.rec[tt]["pf"]), "sk": lambda tt: X.rec[tt]["pf"]},
        {"g": "Overall", "h": "PA", "d": 4, "f": lambda tt: str(X.rec[tt]["pa"]), "sk": lambda tt: X.rec[tt]["pa"], "asc": True},
        {"g": "Overall", "h": "Strk", "d": 5, "f": lambda tt: E(X.rec[tt]["strk"] or DASH)},
        {"g": "Overall", "h": "AP", "d": 3, "f": lambda tt: str(X.ap[tt]) if tt in X.ap else DASH, "sk": lambda tt: X.ap.get(tt, 30), "asc": True},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Power", "d": 2, "f": lambda tt: f'{C.signed(X.rat[tt]["net"])}<span class="l2">{C.ordn(X.rat[tt]["rk"])}</span>', "sk": lambda tt: X.rat[tt]["net"]},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Conf W", "d": 6, "t": "projected conference wins", "f": lambda tt: C.fmt(S[tt]["cw"]), "sk": lambda tt: S[tt]["cw"]},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Title game", "f": lambda tt: C.pct1(S[tt]["p_ccg"]), "sk": lambda tt: S[tt]["p_ccg"]},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Champion", "f": lambda tt: f'<b>{C.pct1(S[tt]["p_conf"])}</b>', "sk": lambda tt: S[tt]["p_conf"]},
        {"g": "Kalshi", "h": "Champ", "d": 1, "t": "Kalshi conference champion YES price",
         "f": lambda tt: (C.pct0(((X.kf.get("conf") or {}).get(ck) or {}).get(tt, {}).get("p")) if (((X.kf.get("conf") or {}).get(ck) or {}).get(tt)) else DASH),
         "sk": lambda tt: (((X.kf.get("conf") or {}).get(ck) or {}).get(tt) or {}).get("p")},
    ]
    tb = HC.rb_table(cols, rows, 6, "stand")
    foot = (f'Order: conference win percentage, then conference wins, overall record and the {HM} rating — not the league’s published '
            f'tiebreakers. Conference games only in the conference record (the Pac-12’s Week 13 flex game counts as non-conference). '
            f'{HM}: {X.smeta["sims"]:,} simulated seasons; the title game takes the two best conference records'
            + (" (division winners)" if cf.get("divs") else "") + ".")
    return HC.brd(f'{E(cf["name"])}', f'{len(cf["members"])} teams', tb, foot)


# ============================================================================ odds
def odds(X, tid):
    t = X.teams[tid]
    S = X.sim[tid]
    kt = (X.kf.get("title") or {}).get(tid)
    kp = (X.kf.get("playoff") or {}).get(tid)
    kc = ((X.kf.get("conf") or {}).get(t["conf"]) or {}).get(tid)

    def kxs(r):
        return f'<small style="display:block;font-size:11px;color:var(--ink3);font-style:normal">Kalshi {C.pct0(r["p"])}</small>' if r else ""
    rows = [("Bowl eligible", "six wins, at most one against FCS", S["p_bowl"], "", ""),
            ("8+ regular-season wins", "", S["p_w8"], "", ""),
            ("10+ regular-season wins", "", S["p_w10"], "", "")]
    if X.rec[tid]["l"] == 0:
        rows.append(("Unbeaten regular season", "", S["p_unbeaten"], "", ""))
    if t["conf"] != "IND":
        rows += [(f'{E(X.conf_short(t["conf"]))} title game', "the two best conference records" + (" (division winners)" if X.confs[t["conf"]].get("divs") else ""), S["p_ccg"], "sep", ""),
                 (f'{E(X.conf_short(t["conf"]))} champion', "", S["p_conf"], "", kxs(kc))]
    rows += [("Make the playoff", "12-team field", S["p_cfp"], "sep", kxs(kp)),
             ("First-round bye", "seeds 1–4", S["p_bye"], "", ""),
             ("Quarterfinal", "bye or a first-round win", S["p_qf"], "", ""),
             ("Semifinal", "", S["p_sf"], "", ""),
             ("Title game", "Allegiant Stadium, Jan 25", S["p_final"], "", ""),
             ("Win the national title", "", S["p_champ"], "", kxs(kt))]
    lad = HC.ladder(rows)
    seeds = S["p_seed"]
    mx = max(max(seeds), 1 - S["p_cfp"], 1e-9)
    bars = "".join(f'<div class="sdb"><i style="height:{max(2, 100 * p / mx):.0f}%"></i><b>{C.pct0(p)}</b><span>#{i + 1}</span></div>' for i, p in enumerate(seeds))
    bars += f'<div class="sdb out"><i style="height:{max(2, 100 * (1 - S["p_cfp"]) / mx):.0f}%"></i><b>{C.pct0(1 - S["p_cfp"])}</b><span>out</span></div>'
    left = sum(1 for e in X.by_team[tid] if e["st"] == 2 and not e["status"]["completed"] and X.state(e) != "off")
    how = (f'<div class="how"><div class="k" style="font-size:11px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.06em">'
           f'Projected wins {HM}</div><div class="big">{C.fmt(S["w"])}<small>W</small></div><dl>'
           f'<dt>10th–90th</dt><dd>{S["w10"]}–{S["w90"]} regular-season wins</dd>'
           f'<dt>Conference</dt><dd>{C.fmt(S["cw"])}–{C.fmt(S["cl"])} projected</dd>'
           f'<dt>Committee proxy</dt><dd>median rank {S["rank_med"]} of {len(X.teams)} at season’s end</dd>'
           f'<dt>Simulations</dt><dd>{X.smeta["sims"]:,} seasons (seed {X.smeta["seed"]})</dd>'
           f'<dt>Games left</dt><dd>{left} regular-season games</dd></dl>'
           f'<div class="sub-h" style="margin-top:14px">CFP seed distribution</div><div class="sdg">{bars}</div>'
           f'<p class="muted-p">Each simulation draws every team’s strength once around its {HM} rating (its own standard error, '
           f'±{C.fmt(X.rat[tid]["se"])} points here), plays the remaining schedule, the conference title games and the bracket '
           f'(first round on the higher seed’s campus, home edge {C.fmt(X.model["hfa"])}; later rounds neutral).</p></div>')
    out = [HC.sec("odds", "Season odds", f'{HM} season simulation {DOT} {X.smeta["sims"]:,} runs {DOT} Kalshi beside, never blended'),
           f'    <div class="proj-g"><div class="paper">{lad}</div><div class="paper">{how}</div></div>', "  </section>"]
    return "\n".join(out)


# ============================================================================ schedule
def schedule(X, tid):
    evs = [e for e in X.by_team[tid]]
    nxt = X.next_game(tid)
    rows = [("row", e, "us" if nxt and e["eid"] == nxt["eid"] else "") for e in evs]

    def opp(e):
        me_home = e["h"]["id"] == tid
        o = e["a"] if me_home else e["h"]
        pre = "vs" if e["neutral"] or me_home else "at"
        sub = []
        if X.is_title(e):
            sub.append("conference championship")
        elif e["conf"]:
            sub.append("conference")
        if e["neutral"]:
            sub.append("neutral: " + (e["venue"].get("name") or ""))
        if e["notes"] and not X.is_title(e):
            sub.append(e["notes"][0])
        rk = X.rank_html(o["id"]) if o["id"] in X.teams else ""
        nm = E(X.loc(o["id"], o))
        nm = f'<a class="tl2" href="#{E(X.key(o["id"]))}"><b>{rk}{nm}</b></a>' if o["id"] in X.teams else f"<b>{nm}</b>"
        return f'<span class="tm">{pre} {HC.chip(o["id"], o.get("abbr"))}<span class="nm2">{nm}<small>{E(" · ".join(sub)) if sub else (E(X.record(o["id"])) if o["id"] in X.teams else "FCS")}</small></span></span>'

    def when(e):
        t_, day, utc = X.when(e)
        wl = X.week_label(e)
        wlk = f'<a class="wk-a" href="#W{e["week"]}">Wk {e["week"]}</a>' if e["st"] == 2 else "Post"
        return f'<b>{wlk} {DOT} {E(day)}</b><span class="l2">{E(t_)}</span>'

    def result(e):
        st = X.state(e)
        if st == "final":
            w = X.winner(e) == tid
            hm = e.get("hm_pre")
            pre = ""
            if hm:
                p = hm["p"] if e["h"]["id"] == tid else 1 - hm["p"]
                pre = f'<span class="l2">pregame {HM} {C.pct0(p)}</span>'
            gl = X.game_link(e, "›", "wk-a")
            return f'<span class="sch-res {"w" if w else "l"}">{"W" if w else "L"} {X.score_txt(e, tid)}</span> {gl}{pre}'
        if st in ("live", "underway"):
            return f'<b>{E(e["status"].get("short") or "Under way")}</b>'
        if st == "off":
            return E(e["status"].get("detail") or "Postponed")
        hm = e.get("hm")
        p = hm["p"] if e["h"]["id"] == tid else 1 - hm["p"]
        ln = C.line_txt(-hm["line"], X.abbr(e["h"]["id"], e["h"]), X.abbr(e["a"]["id"], e["a"]))
        gl = X.game_link(e, "›", "wk-a")
        return f'<b>{C.pct1(p)}</b> {gl}<span class="l2">{E(ln)}</span>'

    def line(e):
        st = X.state(e)
        o = X.line_of(e)
        if not o or o.get("spread") is None:
            return f'{DASH}<span class="l2">{"no line" if st == "final" else "not posted"}</span>'
        txt = E(X.mk_txt(e, o))
        if st == "final":
            cv = X.cover(e)
            me_home = e["h"]["id"] == tid
            if cv:
                x = (e["h"]["score"] - e["a"]["score"]) + o["spread"]
                mine = (x > 0) == me_home if abs(x) > 1e-9 else None
                lab = "push" if mine is None else ("covered" if mine else "did not cover")
                return f'{txt}<span class="l2">closing {DOT} {lab}</span>'
            return f'{txt}<span class="l2">closing</span>'
        return f'{txt}<span class="l2">' + (f'total {C.fmt(o["total"])} {DOT} ' if o.get("total") else "") + 'DraftKings</span>'

    def kal(e):
        k = X.kg.get(e["eid"])
        if not k:
            return DASH
        p = k["p_home"] if e["h"]["id"] == tid else 1 - k["p_home"]
        return f'{C.pct0(p)}<span class="l2">{"pre-kickoff" if k.get("pre") else "book"}{" · thin" if k.get("thin") else ""}</span>'
    cols = [
        {"g": "Game", "h": "Week · date", "c": "l", "f": when},
        {"g": "Game", "h": "Opponent", "c": "l", "f": opp},
        {"g": "Game", "h": "TV", "c": "l wrap", "d": 2, "f": lambda e: E(" / ".join(e["tv"])) or DASH},
        {"g": "Result or HOUSE MODEL", "gs": "Result / house", "h": "Score · P(win)", "f": result},
        {"g": "Line", "h": "Closing or DraftKings", "d": 1, "f": line},
        {"g": "Kalshi", "h": "Win", "d": 3, "f": kal},
    ]
    tb = HC.rb_table(cols, rows, 3, "sched", house=False)
    r = X.rec[tid]
    left = sum(1 for e in evs if not e["status"]["completed"])
    out = [HC.sec("schedule", "Schedule & results", f'{r["w"]}{EN}{r["l"]} {DOT} {left} to play {DOT} ESPN kickoffs (Central) and TV'),
           HC.brd("Every game", f'finals with the closing line and whether {E(X.teams[tid]["loc"])} covered; upcoming games with the {HM} and DraftKings', tb,
                  f'{HM} pregame on a final = the walk-forward line (ratings fit only on the games before that week). Kalshi on this week’s and last '
                  f'week’s games only; a started game shows its pre-kickoff price.'), "  </section>"]
    return "\n".join(out)


# ============================================================================ ratings & percentiles
def card(k, val, unit, p, rank_txt, desc, box=""):
    return (f'<div class="pq-card"><div class="pq-k">{k}</div><div class="pq-main">{HC.pc(p, big=True)}<div class="pq-n">'
            f'<div class="pq-v"><b>{val}</b><small>{unit}</small></div><div class="pq-r">{rank_txt}</div></div></div>'
            f'<div class="pq-d">{desc}</div>' + (f'<div class="pq-box">{box}</div>' if box else "") + "</div>")


def ratings(X, tid):
    R = X.rat[tid]
    n = len(X.teams)
    r = X.rec[tid]
    sp = r["sos_played_rk"]
    sp_p = None if sp is None else 100 * (n - sp) / (n - 1)
    v11 = X.model.get("version") == "v1.1"
    cards = [card("Overall · power", C.signed(R["net"]), "pts", R["pct"], f'{HC.pct_word(R["pct"])} {DOT} {C.ordn(R["rk"])} of {n}',
                  "Points better than an average FBS team on a neutral field: offense plus defense, opponent-adjusted.",
                  f'preseason prior {C.signed(sum(R["prior"]))} {DOT} {R["n"]} games in the fit {DOT} ±{C.fmt(R["se"])}'),
             card("Offense", C.signed(R["off"]), "pts", R["pct_off"], f'{HC.pct_word(R["pct_off"])} {DOT} {C.ordn(R["rk_off"])} of {n}',
                  ("Offensive share, in points: scoring against the same defenses plus run and pass efficiency, with a turnover-luck "
                   "correction." if v11 else "Points scored above what an average offense would score against the same defenses.")),
             card("Defense", C.signed(R["def"]), "pts", R["pct_def"], f'{HC.pct_word(R["pct_def"])} {DOT} {C.ordn(R["rk_def"])} of {n}',
                  ("Defensive share, in points: points prevented against the same offenses plus run and pass efficiency allowed, with "
                   "a turnover-luck correction." if v11 else "Points prevented below what an average defense would allow to the same offenses.")),
             card("Schedule played", C.signed(r["sos_played"]) if r["sos_played"] is not None else DASH, "pts", sp_p,
                  (f'{C.ordn(sp)} hardest of {n}' if sp else DASH),
                  f'Mean {HM} net rating of the opponents faced so far (FCS opponents at their own rating).',
                  (f'still to play: {C.signed(r["sos_left"])} {DOT} {C.ordn(r["sos_left_rk"])} hardest' if r["sos_left"] is not None else "nothing left"))]
    defs = {d[0]: d for d in X.stat_defs}

    def bar(k):
        _, lab, side, hib, nd, unit = defs[k]
        v, rk, p = X.stat(tid, k)
        if v is None:
            return ""
        txt = C.fmt(v, nd) + ("%" if unit == "%" else "")
        return HC.pbar(E(lab), txt, p, f"{C.ordn(rk)} of {n}" if rk else "")
    grp = [("Offense", "per game and per play · ESPN team statistics", ["ppg", "ypp", "rypa", "pypa", "cmp", "3d", "sackr", "give"]),
           ("Defense", "what opponents managed against them", ["papg", "dypp", "drypa", "dpypa", "d3d", "sacks", "tfl", "take"]),
           ("Ball security, discipline, kicking", "", ["tom", "pen", "fg", "punt"])]
    pbg = "".join(f'<div class="pb-grp"><div class="pb-h">{g}<small>{s}</small></div><div class="pb-rows">{"".join(bar(k) for k in ks)}</div></div>'
                  for g, s, ks in grp)
    reads = rating_reads(X, tid)
    out = [HC.sec("ratings", "Ratings &amp; percentiles", f'{HM} through Week {X.model["through"]} {DOT} percentiles among {n} FBS teams'),
           f'    <div class="paper"><div class="pq-g pq-4">{"".join(cards)}</div>'
           f'<div class="sub-h pq-sub">Team profile <small>{X.season} {DOT} ESPN team statistics, every game (FCS opponents included) {DOT} ranks out of {n}, 1 = best</small></div>'
           f'<div class="pb-g">{pbg}</div>{HC.read_block(reads)}</div>', "  </section>"]
    return "\n".join(out)


def rating_reads(X, tid):
    R = X.rat[tid]
    out = []
    n = len(X.teams)
    if abs(R["off"] - R["def"]) >= 6:
        side = "offense" if R["off"] > R["def"] else "defense"
        out.append(f'The {side} carries it: {C.signed(R["off"])} on offense ({C.ordn(R["rk_off"])}) against {C.signed(R["def"])} on defense ({C.ordn(R["rk_def"])}).')
    if X.ap.get(tid) and abs(X.ap[tid] - R["rk"]) >= 10:
        out.append(f'The AP voters have them at No. {X.ap[tid]}; the {HM} ranks them {C.ordn(R["rk"])} — '
                   + ("the record is ahead of the margins." if R["rk"] > X.ap[tid] else "the margins are better than the poll position."))
    elif not X.ap.get(tid) and R["rk"] <= 20:
        out.append(f'Unranked in the AP poll, but {C.ordn(R["rk"])} by the {HM} — the margins say top 20.')
    prior = sum(R["prior"])
    if R["n"] >= 5 and abs(R["net"] - prior) >= 7:
        out.append(f'Moved {C.signed(R["net"] - prior)} points from its preseason prior ({C.signed(prior)}) — '
                   + ("well ahead of where last season pointed." if R["net"] > prior else "well behind where last season pointed."))
    return out


# ============================================================================ record check
def record_check(X, tid):
    r = X.rec[tid]
    res = (X.today.get("resume") or {}).get(tid) or {}
    n = len(X.teams)
    w, l = r["w"], r["l"]
    tiles = []
    if r["pyth"] is not None:
        d = w - r["pyth"]
        tiles.append(("Pythagorean wins", C.fmt(r["pyth"]), f"of {r['gp']} games",
                      f'From points scored and allowed (exponent 2.37). Actual {w}: {C.signed(d)} — '
                      + ("ahead of the points" if d >= 1 else ("behind the points" if d <= -1 else "in line with the points")) + "."))
    tiles.append((f"Rating-expected wins {HM}", C.fmt(r["xw"]), f"of {r['gp']}",
                  f'Sum of today’s single-game win chances for the games already played. Actual {w}: {C.signed(w - r["xw"])}.'))
    tiles.append(("One-score games", f'{r["os_w"]}{EN}{r["os_l"]}', "8 points or fewer",
                  "Close games are near coin flips over a season; a record far from even here rarely repeats."))
    v, rk, p = X.stat(tid, "tom")
    tiles.append(("Turnover margin", C.signed(v, 0) if v is not None else DASH, (f"{C.ordn(rk)} of {n}" if rk else ""),
                  "Takeaways minus giveaways (ESPN). Fumble recoveries in particular swing on luck."))
    if res:
        tiles.append(("Résumé vs an elite team", C.signed(res.get("w", 0) - res.get("E", 0), 2), "wins",
                      f'Wins minus what the 12th-best team would expect against the same schedule ({C.fmt(res.get("E"), 2)}). '
                      f'The committee proxy’s main term.'))
    tiles.append(("Against ranked teams", f'{r["rk_w"]}{EN}{r["rk_l"]}', "AP rank at kickoff", "Results against teams in the AP Top 25 the week of the game."))
    tiles.append(("FCS games", f'{r["fcs_w"]}{EN}{r["fcs_l"]}', "", "At most one FCS win counts toward bowl eligibility."))
    g = "".join(f'<div class="rt"><div class="k">{k}</div><div class="v"><b>{v}</b><small>{s}</small></div><div class="d">{d}</div></div>' for k, v, s, d in tiles)
    reads = []
    if r["pyth"] is not None and w - r["pyth"] >= 1.2:
        reads.append(f'{E(X.teams[tid]["loc"])} has won {C.fmt(w - r["pyth"])} more games than its points suggest'
                     + (f', helped by a {r["os_w"]}{EN}{r["os_l"]} mark in one-score games' if r["os_w"] > r["os_l"] + 1 else "") + " — expect some give-back.")
    elif r["pyth"] is not None and w - r["pyth"] <= -1.2:
        reads.append(f'{E(X.teams[tid]["loc"])} has won {C.fmt(r["pyth"] - w)} fewer games than its points suggest'
                     + (f' ({r["os_w"]}{EN}{r["os_l"]} in one-score games)' if r["os_l"] > r["os_w"] + 1 else "") + " — the record undersells the team.")
    if v is not None and abs(v) >= 7:
        reads.append(f'A turnover margin of {C.signed(v, 0)} is extreme; it tends to drift toward zero.')
    if r["sos_left_rk"] and r["sos_left_rk"] <= 15:
        reads.append(f'The hardest part is ahead: the remaining schedule ranks {C.ordn(r["sos_left_rk"])} hardest of {n}.')
    elif r["sos_left_rk"] and r["sos_left_rk"] >= n - 15:
        reads.append(f'The road eases: the remaining schedule ranks {C.ordn(n + 1 - r["sos_left_rk"])} easiest of {n}.')
    out = [HC.sec("record", "Record check", "is the record real? luck, schedule and the margins"),
           f'    <div class="paper"><div class="rc-g">{g}</div>{HC.read_block(reads)}</div>', "  </section>"]
    return "\n".join(out)


# ============================================================================ team stats
def team_stats(X, tid):
    n = len(X.teams)
    defs = X.stat_defs
    rows = []
    for k, lab, side, hib, nd, unit in defs:
        v, rk, p = X.stat(tid, k)
        if v is None:
            continue
        txt = C.fmt(v, nd) + ("%" if unit == "%" else "")
        if k == "top":
            txt = f"{int(v // 60)}:{int(v % 60):02d}"
        rows.append(f'<tr><td>{E(lab)}</td><td class="r"><b>{txt}</b></td><td class="r">{C.ordn(rk) if rk else DASH}</td>'
                    f'<td class="r">{HC.pc(p) if p is not None else ""}</td><td>{E({"off": "offense", "def": "defense", "misc": "other"}[side])}</td></tr>')
    tb = (f'<table class="tbl"><thead><tr><th>Stat</th><th class="r">Value</th><th class="r">FBS rank</th><th class="r">Pctl</th><th>Unit</th></tr></thead>'
          f'<tbody>{"".join(rows)}</tbody></table>')
    out = [HC.sec("teamstats", "Team stats", f'ESPN team statistics {DOT} ranks and percentiles among {n} FBS teams'),
           f'    <div class="paper">{tb}<p class="muted-p">Per game unless the stat says otherwise; games against FCS opponents included (ESPN’s totals). '
           f'Percentile circles on the locked scale: red is better for the team, whichever direction the stat runs.</p></div>', "  </section>"]
    return "\n".join(out)
