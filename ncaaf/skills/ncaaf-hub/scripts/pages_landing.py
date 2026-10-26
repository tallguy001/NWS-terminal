#!/usr/bin/env python3
"""pages_landing — the league home (#NCAAF): hero + strip, this week's games, the polls, the CFP picture and odds, the
conference races, the power board and efficiency map, team stats, the season so far (with the HOUSE MODEL's own scorecard
against the closing market), the calendar and every team by conference. Every number comes from the pull."""
import math
import sys

sys.dont_write_bytecode = True
import hub_common as HC  # noqa: E402

C = HC.C
E = HC.E
DASH, DOT, EN, MINUS, HM = HC.DASH, HC.DOT, HC.EN, HC.MINUS, HC.HM
P4 = ["SEC", "B1G", "B12", "ACC"]
G6 = ["AAC", "CUSA", "MAC", "MWC", "P12", "SBC"]


def render(X):
    P = X.P
    nav, parts = [], []
    wk = X.week
    wk_ev = [e for e in X.ev if e["st"] == 2 and e["week"] == wk]
    fin_all = [e for e in X.ev if e["status"]["completed"]]
    parts.append(hero(X, wk, wk_ev, fin_all))
    parts.append(games(X, wk, wk_ev)); nav.append(("games", f"Week {wk}"))
    parts.append(rankings(X)); nav.append(("rankings", "Rankings"))
    parts.append(playoff(X)); nav.append(("playoff", "Playoff"))
    parts.append(odds(X)); nav.append(("odds", "Odds"))
    parts.append(conf_races(X)); nav.append(("confs", "Conferences"))
    parts.append(power(X)); nav.append(("power", "Power"))
    parts.append(efficiency(X)); nav.append(("efficiency", "Efficiency"))
    parts.append(team_stats(X)); nav.append(("teamstats", "Team stats"))
    parts.append(pulse(X, fin_all)); nav.append(("pulse", "Trends"))
    parts.append(calendar(X)); nav.append(("calendar", "Calendar"))
    parts.append(index(X)); nav.append(("allteams", "All teams"))
    status = f"Week {wk} {DOT} {len(wk_ev)} FBS games {DOT} {len(fin_all)} final"
    return "\n".join(parts), [list(n) for n in nav], status


# ============================================================================ hero
def hero(X, wk, wk_ev, fin_all):
    P = X.P
    done = sum(1 for e in wk_ev if e["status"]["completed"])
    prog = []
    for c in X.reg_weeks:
        cls = "done" if c["week"] < wk else ("now" if c["week"] == wk else "")
        prog.append(f'<i class="{cls}" title="Week {c["week"]} · {E(c.get("detail") or "")}"></i>')
    post = [c for c in X.cal if c["st"] == 3]
    for c in post:
        prog.append(f'<i class="" title="{E(c["label"])} · {E(c.get("detail") or "")}"></i>')
    reg_total = sum(1 for e in X.ev if e["st"] == 2)
    reg_fin = sum(1 for e in X.ev if e["st"] == 2 and e["status"]["completed"])
    h = ['  <div class="lp-hero"><div class="lp-hero-in">',
         f'    <div class="lp-k">College football {DOT} FBS {DOT} {X.season} season {DOT} {len(X.teams)} teams in {len(X.confs) - 1} conferences + independents</div>',
         f'    <div class="lp-t">{X.season} <span>season</span></div>',
         f'    <div class="lp-sub"><b>Week {wk}</b> {DOT} {E(X.week_range(wk))} {DOT} {done} of {len(wk_ev)} played {DOT} '
         f'{reg_fin} of {reg_total} regular-season FBS games final {DOT} built {E(P["built_ct"])}</div>',
         f'    <div class="lp-prog" aria-hidden="true">{"".join(prog)}</div><div class="lp-progc"><span>Week 1</span>'
         f'<span>CFP title game {DOT} Mon Jan 25</span></div>',
         '  </div></div>']
    # snapshot
    cells = []
    ap = (X.rk.get("ap") or {}).get("ranks") or []
    if ap:
        r = ap[0]
        cells.append(cell("AP No. 1", f'{HC.chip(r["id"])}{E(X.record(r["id"]))}',
                          f'{X.team_link(r["id"])} {DOT} {int(r.get("fpv") or 0)} first-place votes'))
    unb = sorted([t for t, r in X.rec.items() if r["l"] == 0 and r["w"] > 0], key=lambda t: -X.rat[t]["net"])
    cells.append(cell("Unbeaten", f'{len(unb)}<small> teams</small>',
                      " ".join(f'{HC.chip(t)}' for t in unb[:6]) + (f" +{len(unb) - 6}" if len(unb) > 6 else "") if unb else "none left"))
    top = max(X.rat, key=lambda t: X.rat[t]["net"])
    cells.append(cell(f"Power #1 {HM}", f'{HC.chip(top)}{C.signed(X.rat[top]["net"])}<small> pts</small>',
                      f'{X.team_link(top)} {DOT} vs an average FBS team, neutral field'))
    fav = max(X.sim, key=lambda t: X.sim[t]["p_champ"])
    kt = X.kf.get("title") or {}
    kfav = max(kt, key=lambda t: kt[t]["p"]) if kt else None
    cells.append(cell(f"Title favorite {HM}", f'{HC.chip(fav)}{C.pct1(X.sim[fav]["p_champ"])}',
                      f'{X.team_link(fav)} {DOT} {X.smeta["sims"]:,} simulations'
                      + (f' {DOT} Kalshi: {E(X.abbr(kfav))} {C.pct0(kt[kfav]["p"])}' if kfav else "")))
    seeds = X.today.get("seeds") or []
    if X.cfp:
        c1 = min(X.cfp, key=X.cfp.get)
        cells.append(cell("CFP No. 1", f'{HC.chip(c1)}{E(X.record(c1))}',
                          f'{X.team_link(c1)} {DOT} committee, {E((X.rk.get("cfp") or {}).get("week") or "")}'))
    elif seeds:
        cells.append(cell(f"No. 1 seed today {HM}", f'{HC.chip(seeds[0])}{E(X.record(seeds[0]))}',
                          f'{X.team_link(seeds[0])} {DOT} committee proxy; first CFP ranking Tue Nov 3'))
    fbs2 = [e for e in fin_all if e["st"] == 2 and e["h"]["id"] in X.teams and e["a"]["id"] in X.teams]
    pts = sum(e["h"]["score"] + e["a"]["score"] for e in fbs2)
    cells.append(cell("Scoring", f'{C.fmt(pts / (2 * len(fbs2)) if fbs2 else None)}<small> pts</small>',
                      f'per team per game {DOT} {len(fbs2)} FBS v FBS finals'))
    h.append('  <div class="snap">' + "".join(cells) + "</div>")
    return "\n".join(h)


def cell(k, v, note):
    return f'<div class="cell"><div class="k">{k}</div><div class="v">{v}</div><div class="note">{note}</div></div>'


# ============================================================================ this week's games
def sb_card(X, e, foot_extra=""):
    st = X.state(e)
    t, day, utc = X.when(e)
    cls = {"final": "fin", "live": "live", "underway": "live", "off": "fin"}.get(st, "")
    head = {"final": "Final", "live": E(e["status"].get("short") or "Live"), "underway": "Under way", "off": E(e["status"].get("detail") or "Postponed")}.get(st, f"{day} {DOT} {t}")
    tv = E(" / ".join(e["tv"][:2])) if e["tv"] else ("TV TBA" if st == "pre" else "")
    rows = []
    w = X.winner(e)
    for s in ("a", "h"):
        side = e[s]
        tid = side["id"]
        nm = E(X.loc(tid, side))
        link = f'<a href="#{E(X.key(tid))}">{X.rank_html(tid)}{nm}<small>{E(X.record(tid)) if tid in X.teams else "FCS"}</small></a>' \
            if tid in X.teams else f'<span>{nm}<small>FCS</small></span>'
        sc = "" if side["score"] is None or st == "pre" else str(side["score"])
        rows.append(f'<div class="sb-r">{HC.chip(tid, side.get("abbr"))}{link}<span class="sc{" win" if w == tid else ""}">{sc}</span></div>')
    foot = []
    if st == "final":
        cv = X.cover(e)
        mk = X.mk_txt(e, e.get("cl"))
        if mk:
            foot.append(f"Closing {E(mk)}" + (f", total {C.fmt(e['cl']['total'])}" if e["cl"].get("total") else "")
                        + (f" {DOT} {cv[0]}" + (f", {cv[1]}" if cv[1] else "") if cv else ""))
        m, sub = X.hm_txt(e, short=True)
        if m != DASH:
            foot.append(f'{HM} pregame {m}')
    else:
        m, sub = X.hm_txt(e, short=True)
        foot.append(f'{HM} {m} {DOT} {sub}')
        mk = X.mk_txt(e)
        foot.append(f"DraftKings {E(mk)}" if mk else "DraftKings not posted")
        kt = X.kal_txt(e)
        if kt:
            foot.append(f"Kalshi {kt[0]}")
    if e["neutral"]:
        foot.append("neutral site")
    gl = X.game_link(e)
    return (f'<div class="sb {cls}"><div class="sb-h"><b>{head}</b><span>{tv}</span></div>{"".join(rows)}'
            f'<div class="sb-f">{" · ".join(foot)}{(" · " + gl) if gl else ""}{foot_extra}</div></div>')


def featured(X, evs, n=24):
    def key(e):
        ra, rh = X.ap.get(e["a"]["id"]), X.ap.get(e["h"]["id"])
        both = 1 if (ra and rh) else 0
        one = 1 if (ra or rh) else 0
        q = min(X.rat.get(e["a"]["id"], {}).get("net", -40), X.rat.get(e["h"]["id"], {}).get("net", -40))
        return (-both, -one, -q)
    pick = sorted(evs, key=key)[:n]
    return sorted(pick, key=lambda e: (e["date"] or "", e["eid"]))


def games(X, wk, wk_ev):
    out = [HC.sec("games", f"Week {wk}", f'{E(X.week_range(wk))} {DOT} ESPN kickoffs (Central) {DOT} {HM} vs DraftKings {DOT} Kalshi beside')]
    feats = featured(X, wk_ev)
    out.append(f'    <p class="lp-live">Games to watch: every game with an AP Top 25 team, then the best of the rest by {HM} rating '
               f'{DOT} <a class="wk-a" href="#W{wk}">All {len(wk_ev)} games in the Week {wk} slate ›</a></p>')
    out.append('    <div class="sb-g">' + "".join(sb_card(X, e) for e in feats) + "</div>")
    # last week's upsets of ranked teams
    prev = [e for e in X.ev if e["st"] == 2 and e["week"] == wk - 1 and e["status"]["completed"]]
    ups = []
    for e in prev:
        w = X.winner(e)
        los = e["a"] if w == e["h"]["id"] else e["h"]
        win = e["h"] if w == e["h"]["id"] else e["a"]
        if los.get("rank") and (not win.get("rank") or win["rank"] > los["rank"]):
            ups.append((los["rank"], e, los, win))
    if ups:
        ups.sort(key=lambda x: x[0])
        chips = []
        for r, e, los, win in ups:
            chips.append(f'<span class="res"><b class="l">#{r} {E(X.abbr(los["id"], los))}</b> lost {e[("h" if los is e["h"] else "a")]["score"]}{EN}'
                         f'{e[("a" if los is e["h"] else "h")]["score"]} to {HC.chip(win["id"], win.get("abbr"))}'
                         f'{X.team_link(win["id"], win, X.abbr(win["id"], win))}{(" " + X.game_link(e, "›", "wk-a")) if X.game_link(e) else ""}</span>')
        out.append(f'    <div class="sub-h">Week {wk - 1}: ranked teams beaten by lower-ranked or unranked teams</div>'
                   f'<div class="res-row">{"".join(chips)}</div>')
    out.append("  </section>")
    return "\n".join(out)


# ============================================================================ polls
def rankings(X):
    out = [HC.sec("rankings", "Rankings", f'AP and AFCA Coaches polls{" and the CFP committee" if X.cfp else ""} via ESPN {DOT} {HM} power beside')]
    items = []
    for k, lab in (("cfp", "CFP committee"), ("ap", "AP Top 25"), ("usa", "Coaches")):
        p = X.rk.get(k)
        if p:
            items.append((f"rk-{k}", lab, poll_board(X, p, k)))
    items.append(("rk-hm", "HOUSE MODEL top 25", hm_board(X)))
    if not X.cfp:
        out.append('    <p class="muted-p" style="margin-top:0">The College Football Playoff committee releases its first ranking '
                   'on Tuesday, November 3 (then Nov 10, 17, 24, Dec 1; the final ranking and bracket on Selection Day, Sunday Dec 6).</p>')
    out.append(HC.tabs("rk", items, "tap a header to sort · a team opens its page"))
    out.append("  </section>")
    return "\n".join(out)


def poll_board(X, p, k):
    rows = [("row", r, "") for r in p["ranks"]]
    cols = [
        {"g": "Rank", "h": "#", "c": "rkc", "f": lambda r: str(r["rank"]), "sk": lambda r: r["rank"], "asc": True},
        {"g": "Team", "h": "Team", "c": "l", "f": lambda r: X.team_cell(r["id"], sub=X.conf_short(X.teams[r["id"]]["conf"]) if r["id"] in X.teams else "")},
        {"g": "Team", "h": "Record", "f": lambda r: E(X.record(r["id"]))},
        {"g": "Poll", "h": "Points", "d": 3, "f": lambda r: (f'{int(r["pts"]):,}' + (f'<span class="l2">{int(r["fpv"])} first</span>' if r.get("fpv") else "")) if r.get("pts") is not None else DASH,
         "sk": lambda r: r.get("pts")},
        {"g": "Poll", "h": "Prev", "d": 2, "f": lambda r: str(r["prev"]) if r.get("prev") and r["prev"] <= 25 else "NR", "sk": lambda r: r.get("prev") if r.get("prev") and r["prev"] <= 25 else 30, "asc": True},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Power", "f": lambda r: hm_pow(X, r["id"]), "sk": lambda r: (X.rat.get(r["id"]) or {}).get("net")},
        {"g": "HOUSE MODEL", "gs": "House", "h": "P(CFP)", "f": lambda r: C.pct1((X.sim.get(r["id"]) or {}).get("p_cfp")), "sk": lambda r: (X.sim.get(r["id"]) or {}).get("p_cfp")},
        {"g": "Kalshi", "h": "CFP", "d": 1, "t": "Kalshi YES price, 'to make the playoff' (KXNCAAFPLAYOFF)",
         "f": lambda r: kx(X, "playoff", r["id"]), "sk": lambda r: (X.kf.get("playoff", {}).get(r["id"]) or {}).get("p")},
    ]
    t = HC.rb_table(cols, rows, 3, "lp-poll", sort_default=0)
    return HC.brd(E(p["name"]), E(p.get("headline") or ""), t,
                  f'ESPN rankings feed {DOT} {E((p.get("date") or "")[:10])} {DOT} {HM} power = points better than an average FBS team '
                  f'on a neutral field (rank of {len(X.teams)})')


def hm_pow(X, tid):
    r = X.rat.get(tid)
    if not r:
        return DASH
    return f'<b>{C.signed(r["net"])}</b><span class="l2">{C.ordn(r["rk"])}</span>'


def kx(X, kind, tid, conf=None):
    d = (X.kf.get("conf") or {}).get(conf, {}) if kind == "conf" else (X.kf.get(kind) or {})
    r = d.get(tid)
    if not r:
        return DASH
    return f'{C.pct0(r["p"])}' + (' <span class="kx">thin</span>' if r.get("thin") else "")


def hm_board(X):
    top = sorted(X.rat, key=lambda t: -X.rat[t]["net"])[:25]
    rows = [("row", t, "") for t in top]
    cols = [
        {"g": "Rank", "h": "#", "c": "rkc", "f": lambda t: str(X.rat[t]["rk"]), "sk": lambda t: X.rat[t]["rk"], "asc": True},
        {"g": "Team", "h": "Team", "c": "l", "f": lambda t: X.team_cell(t, sub=X.conf_short(X.teams[t]["conf"]))},
        {"g": "Team", "h": "Record", "f": lambda t: E(X.record(t))},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Net", "f": lambda t: f'<span class="vp">{C.signed(X.rat[t]["net"])}{HC.pc(X.rat[t]["pct"])}</span>', "sk": lambda t: X.rat[t]["net"]},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Off", "d": 2, "f": lambda t: C.signed(X.rat[t]["off"]), "sk": lambda t: X.rat[t]["off"]},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Def", "d": 2, "f": lambda t: C.signed(X.rat[t]["def"]), "sk": lambda t: X.rat[t]["def"]},
        {"g": "Polls", "h": "AP", "d": 1, "f": lambda t: str(X.ap[t]) if t in X.ap else "NR", "sk": lambda t: X.ap.get(t, 30), "asc": True},
        {"g": "Odds", "gs": "Odds", "h": "P(CFP)", "f": lambda t: C.pct1(X.sim[t]["p_cfp"]), "sk": lambda t: X.sim[t]["p_cfp"]},
    ]
    t = HC.rb_table(cols, rows, 2, "lp-poll", sort_default=0)
    return HC.brd(f"{HM} top 25", f"ratings through Week {X.model['through']} {DOT} {X.model['finals']} finals this season",
                  t, "Net = offense + defense: points better than an average FBS team on a neutral field. Results only; the market is never an input.")


# ============================================================================ CFP picture
def picture_from_ranking(X, order):
    """The 2026 bid rules applied to a ranking (list of team ids, best first) with the conference leaders as champions."""
    leaders = X.today.get("leaders") or {}
    rank = {t: i for i, t in enumerate(order)}
    big = 999
    aq = [leaders[c] for c in P4 if c in leaders]
    g6 = [leaders[c] for c in G6 if c in leaders]
    if g6:
        aq.append(min(g6, key=lambda t: (rank.get(t, big), -X.rat[t]["net"])))
    nd = next((t for t in X.teams if X.teams[t]["key"] == "ND"), None)
    top = order[:12]
    fld = list(top)
    for t in aq:
        if t not in fld:
            fld.append(t)
    prot = set(aq) | ({nd} if nd in top else set())
    while len(fld) > 12:
        fld.remove(max((t for t in fld if t not in prot), key=lambda t: rank.get(t, big)))
    seeds = sorted([t for t in fld if rank.get(t, big) < 12], key=lambda t: rank[t]) + \
        sorted([t for t in fld if rank.get(t, big) >= 12], key=lambda t: (rank.get(t, big), -X.rat[t]["net"]))
    out4 = [t for t in order if t not in seeds][:4]
    return seeds, set(aq), out4


def bk_team(X, sd, t, aq):
    s = X.sim[t]
    return (f'<div class="bk-t{" aq" if t in aq else ""}"><span class="sd">{sd}</span>{HC.chip(t)}'
            f'<span class="nm"><b>{X.team_link(t)}</b><small>{E(X.record(t))} {DOT} {E(X.conf_short(X.teams[t]["conf"]))}</small></span>'
            f'<span class="pr"><b>{C.pct0(s["p_cfp"])}</b>P(CFP)</span></div>')


def playoff(X):
    if X.cfp:
        order = [r["id"] for r in sorted((X.rk.get("cfp") or {}).get("ranks", []), key=lambda r: r["rank"])]
        rest = [t for t in X.today.get("rank", []) if t not in order]
        seeds, aq, out4 = picture_from_ranking(X, order + rest)
        basis = (f'the committee’s ranking ({E((X.rk.get("cfp") or {}).get("week") or "")}) with today’s conference leaders as champions, '
                 f'the 2026 bid rules applied')
    else:
        seeds, aq, out4 = picture_from_ranking(X, X.today.get("rank", []))
        basis = (f'{HM} committee proxy (record against schedule + rating + conference title, fitted to the committee’s final '
                 f'rankings 2014–2025) with today’s conference leaders as champions')
    out = [HC.sec("playoff", "Playoff picture", f'if the season ended today {DOT} 12 teams {DOT} right: {HM} P(CFP)')]
    out.append(f'    <p class="muted-p" style="margin-top:0">Basis: {basis}. Five automatic bids (ACC, Big Ten, Big 12 and SEC champions; the '
               f'best champion of the American, C-USA, MAC, Mountain West, Pac-12 and Sun Belt), seven at-large; Notre Dame is in if top 12; '
               f'straight seeding, byes to seeds 1–4; an automatic qualifier outside the top 12 takes the lowest seed. AQ = automatic qualifier.</p>')
    if len(seeds) >= 12:
        sd = {i + 1: t for i, t in enumerate(seeds)}
        byes = "".join(f'<div class="bk-m">{bk_team(X, k, sd[k], aq)}</div>' for k in (1, 2, 3, 4))
        fr = "".join(f'<div class="bk-m"><div class="bk-host">at {E(X.loc(sd[hi]))} {DOT} winner plays No. {q}</div>'
                     f'{bk_team(X, hi, sd[hi], aq)}{bk_team(X, lo, sd[lo], aq)}</div>'
                     for hi, lo, q in ((5, 12, 4), (6, 11, 3), (7, 10, 2), (8, 9, 1)))
        out.append(f'    <div class="bk"><div class="bk-col"><h5>First-round byes {DOT} seeds 1–4</h5>{byes}</div>'
                   f'<div class="bk-col"><h5>First round {DOT} Dec 18–19 {DOT} higher seed hosts</h5>{fr}</div></div>')
        out.append('    <div class="sub-h">First four out</div><div class="bk-out">'
                   + "".join(f'<span>{HC.chip(t)}{X.team_link(t)} {E(X.record(t))} {DOT} {HM} {C.pct0(X.sim[t]["p_cfp"])}</span>' for t in out4)
                   + "</div>")
    # contenders board
    cont = sorted([t for t in X.sim if X.sim[t]["p_cfp"] >= 0.005], key=lambda t: -X.sim[t]["p_cfp"])
    out.append(odds_board(X, cont, "lp-cfp", f"CFP contenders {DOT} {len(cont)} teams at 0.5% or better",
                          "the HOUSE MODEL season simulation; Kalshi columns are YES prices as quoted, never blended"))
    out.append("  </section>")
    return "\n".join(out)


def odds_board(X, ids, cls, title, sub):
    rows = [("row", t, "") for t in ids]
    S = X.sim
    cols = [
        {"g": "Team", "h": "#", "c": "rkc", "f": lambda t: "", "sk": None},
        {"g": "Team", "h": "Team", "c": "l", "f": lambda t: X.team_cell(t, sub=X.conf_short(X.teams[t]["conf"]))},
        {"g": "Team", "h": "Rec", "f": lambda t: E(X.record(t)), "d": 5},
        {"g": "Regular season", "gs": "Season", "h": "Proj W", "f": lambda t: f'<b>{C.fmt(S[t]["w"])}</b><span class="l2">{S[t]["w10"]}–{S[t]["w90"]}</span>', "sk": lambda t: S[t]["w"], "d": 4},
        {"g": "Regular season", "gs": "Season", "h": "Bowl", "t": "six wins (at most one against FCS)", "f": lambda t: C.pct0(S[t]["p_bowl"]), "sk": lambda t: S[t]["p_bowl"], "d": 6},
        {"g": "Conference", "gs": "Conf", "h": "Title game", "f": lambda t: C.pct0(S[t]["p_ccg"]), "sk": lambda t: S[t]["p_ccg"], "d": 3},
        {"g": "Conference", "gs": "Conf", "h": "Champion", "f": lambda t: C.pct1(S[t]["p_conf"]), "sk": lambda t: S[t]["p_conf"], "d": 2},
        {"g": "College Football Playoff", "gs": "CFP", "h": "Make it", "f": lambda t: f"<b>{C.pct1(S[t]['p_cfp'])}</b>", "sk": lambda t: S[t]["p_cfp"]},
        {"g": "College Football Playoff", "gs": "CFP", "h": "Bye", "f": lambda t: C.pct1(S[t]["p_bye"]), "sk": lambda t: S[t]["p_bye"], "d": 3},
        {"g": "College Football Playoff", "gs": "CFP", "h": "Semis", "f": lambda t: C.pct1(S[t]["p_sf"]), "sk": lambda t: S[t]["p_sf"], "d": 4},
        {"g": "College Football Playoff", "gs": "CFP", "h": "Title", "f": lambda t: f"<b>{C.pct1(S[t]['p_champ'])}</b>", "sk": lambda t: S[t]["p_champ"]},
        {"g": "Kalshi", "h": "CFP", "t": "KXNCAAFPLAYOFF YES price", "f": lambda t: kx(X, "playoff", t), "sk": lambda t: (X.kf.get("playoff", {}).get(t) or {}).get("p"), "d": 1},
        {"g": "Kalshi", "h": "Title", "t": "KXNCAAF YES price", "f": lambda t: kx(X, "title", t), "sk": lambda t: (X.kf.get("title", {}).get(t) or {}).get("p"), "d": 1},
    ]
    cols[0]["f"] = lambda t, _o=ids: str(_o.index(t) + 1)
    t = HC.rb_table(cols, rows, 6, cls, sort_default=7)
    foot = (f'{HM} season simulation: {X.smeta["sims"]:,} seasons (seed {X.smeta["seed"]}) from {X.smeta["done"]} finals and '
            f'{X.smeta["remaining"]} games to play. Integrity: CFP spots sum to {X.smeta["sum_cfp"]:.1f}, titles to {X.smeta["sum_champ"]:.3f}. '
            f'Kalshi: {"YES prices read " + E((X.P["kalshi"].get("fmeta") or {}).get("read_utc") or "") if X.kal_ok else E("not read this build (" + X.kal_why + ")")}.')
    return HC.brd(title, sub, t, foot)


# ============================================================================ odds
def odds(X):
    S = X.sim
    out = [HC.sec("odds", "Season odds", f'{HM} season simulation {DOT} {X.smeta["sims"]:,} runs {DOT} Kalshi beside')]
    top = sorted(S, key=lambda t: -S[t]["p_champ"])[:12]
    kt = X.kf.get("title") or {}
    lad = HC.ladder([(f'{HC.chip(t)} {X.team_link(t)}', f'{E(X.record(t))} {DOT} reach the final {C.pct1(S[t]["p_final"])}', S[t]["p_champ"], "",
                      (f'<small style="display:block;font-size:11px;color:var(--ink3);font-style:normal">Kalshi {C.pct0(kt[t]["p"])}</small>' if t in kt else ""))
                     for t in top])
    # expected CFP teams by conference
    exp = []
    for ck in X.conf_order:
        mem = X.confs[ck]["members"]
        ev = sum(S[t]["p_cfp"] for t in mem)
        exp.append((ck, ev, sum(S[t]["p_champ"] for t in mem)))
    exp.sort(key=lambda x: -x[1])
    rows = "".join(f'<dt><a class="wk-a" href="#C-{ck}">{E(X.conf_short(ck))}</a></dt><dd>{C.fmt(ev, 2)} teams {DOT} title {C.pct1(pc)}</dd>' for ck, ev, pc in exp)
    how = (f'<div class="how"><div class="k" style="font-size:11px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.06em">'
           f'Expected CFP teams by conference {HM}</div><dl>{rows}</dl>'
           f'<p class="muted-p">Sums of each member’s chance to make the 12-team field (they add to 12). '
           f'Committee proxy: top-12 overlap with the committee’s final ranking {E(str((X.model.get("committee") or {}).get("top12_overlap_mean", "—")))} '
           f'of 12 on average, 2014–2025.</p></div>')
    out.append(f'    <div class="proj-g"><div class="paper"><div class="sub-h" style="margin-top:0;padding-top:0;border-top:0">National title {DOT} top 12 {HM}</div>{lad}</div>'
               f'<div class="paper">{how}</div></div>')
    allt = sorted(S, key=lambda t: -S[t]["p_cfp"] * 1000 - S[t]["w"])
    out.append(odds_board(X, allt, "lp-odds", f"All {len(allt)} FBS teams", "sortable · default by P(CFP)"))
    out.append("  </section>")
    return "\n".join(out)


# ============================================================================ conference races
def conf_races(X):
    S = X.sim
    out = [HC.sec("confs", "Conference races", f'{HM} title-game and title odds {DOT} Kalshi champion prices beside')]
    cards = []
    facts_cal = {x["date"]: x["what"] for x in (X.facts.get("calendar") or [])}
    for ck in X.conf_order:
        if ck == "IND":
            continue
        cf = X.confs[ck]
        mem = sorted(cf["members"], key=lambda t: (-S[t]["p_ccg"], -X.rat[t]["net"]))[:6]
        rows = "".join(f'<tr><td><span class="tm">{HC.chip(t)}{X.team_link(t)}</span></td><td>{E(X.conf_record(t))}</td>'
                       f'<td>{E(X.record(t))}</td><td>{C.pct0(S[t]["p_ccg"])}</td><td><b>{C.pct0(S[t]["p_conf"])}</b></td>'
                       f'<td>{kx(X, "conf", t, ck)}</td></tr>' for t in mem)
        kxs = "Kalshi" if (X.kf.get("conf") or {}).get(ck) else "Kalshi"
        cards.append(f'<div class="cr"><div class="cr-h"><a href="#C-{ck}">{E(cf["short"])}</a><small>{len(cf["members"])} teams'
                     f'{" · divisions" if cf.get("divs") else ""}</small></div><table><thead><tr><th>Team</th><th>Conf</th><th>All</th>'
                     f'<th title="HOUSE MODEL: reach the title game">Title gm</th><th title="HOUSE MODEL: win the conference">Champ</th><th title="Kalshi champion YES price">{kxs}</th></tr></thead><tbody>{rows}</tbody></table>'
                     f'<div class="cr-f"><a class="wk-a" href="#C-{ck}">Full standings and odds ›</a></div></div>')
    out.append('    <div class="cr-g">' + "".join(cards) + "</div>")
    out.append(f'    <p class="muted-p">Title-game participants in the simulation: the two best conference records (Sun Belt: the East and West '
               f'winners); a two-way tie goes to head-to-head, anything else to the simulated strength — each league’s published tiebreakers '
               f'are longer, so this is an approximation. Title games are played on neutral sites.</p>')
    out.append("  </section>")
    return "\n".join(out)


# ============================================================================ power
def power(X):
    R, S, rec = X.rat, X.sim, X.rec
    res = X.today.get("resume") or {}
    ids = sorted(R, key=lambda t: -R[t]["net"])
    rows = [("row", t, "") for t in ids]
    cols = [
        {"g": "Rank", "h": "#", "c": "rkc", "f": lambda t: str(R[t]["rk"]), "sk": lambda t: R[t]["rk"], "asc": True},
        {"g": "Team", "h": "Team", "c": "l", "f": lambda t: X.team_cell(t, sub=X.conf_short(X.teams[t]["conf"]))},
        {"g": "Team", "h": "Rec", "f": lambda t: E(X.record(t)), "d": 5},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Net", "f": lambda t: f'<span class="vp">{C.signed(R[t]["net"])}{HC.pc(R[t]["pct"])}</span>', "sk": lambda t: R[t]["net"]},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Offense", "f": lambda t: f'<span class="vp">{C.signed(R[t]["off"])}{HC.pc(R[t]["pct_off"])}</span>', "sk": lambda t: R[t]["off"], "d": 2},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Defense", "f": lambda t: f'<span class="vp">{C.signed(R[t]["def"])}{HC.pc(R[t]["pct_def"])}</span>', "sk": lambda t: R[t]["def"], "d": 2},
        {"g": "Schedule", "h": "Played", "t": "mean HOUSE MODEL net of opponents played (rank, 1 = hardest)",
         "f": lambda t: (f'{C.signed(rec[t]["sos_played"])}<span class="l2">{C.ordn(rec[t]["sos_played_rk"])}</span>' if rec[t]["sos_played"] is not None else DASH),
         "sk": lambda t: rec[t]["sos_played"], "d": 3},
        {"g": "Schedule", "h": "Left", "t": "mean HOUSE MODEL net of opponents still to play",
         "f": lambda t: (f'{C.signed(rec[t]["sos_left"])}<span class="l2">{C.ordn(rec[t]["sos_left_rk"])}</span>' if rec[t]["sos_left"] is not None else DASH),
         "sk": lambda t: rec[t]["sos_left"], "d": 4},
        {"g": "Résumé", "h": "vs elite", "t": "wins minus the wins an elite (12th-best) team would expect against the same schedule so far",
         "f": lambda t: C.signed((res.get(t) or {}).get("w", 0) - (res.get(t) or {}).get("E", 0), 2) if t in res else DASH,
         "sk": lambda t: ((res.get(t) or {}).get("w", 0) - (res.get(t) or {}).get("E", 0)) if t in res else None, "d": 3},
        {"g": "Polls", "h": "AP", "f": lambda t: str(X.ap[t]) if t in X.ap else DASH, "sk": lambda t: X.ap.get(t, 30), "asc": True, "d": 1},
    ]
    t = HC.rb_table(cols, rows, 5, "lp-power", sort_default=0)
    out = [HC.sec("power", "Power ratings", f'{HM} {DOT} all {len(ids)} FBS teams {DOT} through Week {X.model["through"]}')]
    test = X.model.get("test_all") or {}
    out.append(HC.brd(f"{HM} ratings", "points better than an average FBS team on a neutral field; offense = points scored above average, "
                      "defense = points prevented", t,
                      f'Each score is modeled as league average + offense − opposing defense ± half the home edge ({C.fmt(X.model["hfa"])} points); '
                      f'ridge-shrunk toward a prior (last season’s final rating regressed {int(round(100 * (1 - X.model["params"]["rho"])))}% '
                      f'toward the team’s current conference). FCS opponents share a group rating ({C.signed(X.model["fcs_group"])}). '
                      f'Held-out {E("–".join(map(str, (X.model.get("calibration") or {}).get("test_seasons") or [])))}: margin error '
                      f'{C.fmt(test.get("mae_house"), 2)} points vs the closing line’s {C.fmt(test.get("mae_market"), 2)} — the market is better.'))
    out.append("  </section>")
    return "\n".join(out)


# ============================================================================ efficiency map
def efficiency(X):
    R = X.rat
    ids = list(R)
    xs = [R[t]["off"] for t in ids]
    ys = [R[t]["def"] for t in ids]
    x0, x1 = math.floor(min(xs) / 5) * 5, math.ceil(max(xs) / 5) * 5
    y0, y1 = math.floor(min(ys) / 5) * 5, math.ceil(max(ys) / 5) * 5
    W, H, L, T, Rr, B = 980, 620, 70, 30, 956, 564

    def px(v):
        return L + (v - x0) / (x1 - x0) * (Rr - L)

    def py(v):
        return B - (v - y0) / (y1 - y0) * (B - T)
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="HOUSE MODEL offense against defense for all {len(ids)} FBS teams">']
    for v in range(int(x0), int(x1) + 1, 5):
        g.append(f'<line class="sc-gd" x1="{px(v):.1f}" y1="{T}" x2="{px(v):.1f}" y2="{B}"/><text class="sc-tk" x="{px(v):.1f}" y="{B + 19}" text-anchor="middle">{C.signed(v, 0)}</text>')
    for v in range(int(y0), int(y1) + 1, 5):
        g.append(f'<line class="sc-gd" x1="{L}" y1="{py(v):.1f}" x2="{Rr}" y2="{py(v):.1f}"/><text class="sc-tk" x="{L - 8}" y="{py(v) + 4:.1f}" text-anchor="end">{C.signed(v, 0)}</text>')
    g.append(f'<line class="sc-avg" x1="{px(0):.1f}" y1="{T}" x2="{px(0):.1f}" y2="{B}"/><line class="sc-avg" x1="{L}" y1="{py(0):.1f}" x2="{Rr}" y2="{py(0):.1f}"/>')
    g.append(f'<rect x="{L}" y="{T}" width="{Rr - L}" height="{B - T}" fill="none" class="sc-ax"/>')
    g.append(f'<text class="sc-q" x="{Rr - 8}" y="{T + 16}" text-anchor="end">Good offense · good defense</text>'
             f'<text class="sc-q" x="{L + 8}" y="{B - 10}">Bad offense · bad defense</text>'
             f'<text class="sc-q" x="{L + 8}" y="{T + 16}">Defense carries it</text>'
             f'<text class="sc-q" x="{Rr - 8}" y="{B - 10}" text-anchor="end">Offense carries it</text>'
             f'<text class="sc-lb" x="{(L + Rr) / 2:.0f}" y="{H - 12}" text-anchor="middle">Offense: points above average → better</text>'
             f'<text class="sc-lb" transform="translate(16 {(T + B) / 2:.0f}) rotate(-90)" text-anchor="middle">Defense: points prevented → better</text>')
    show = set(sorted(ids, key=lambda t: -R[t]["net"])[:25]) | set(X.ap)
    order = sorted(ids, key=lambda t: (t in show, R[t]["net"]))
    for t in order:
        tm = X.teams[t]
        tip = (f'<b>{E(tm["full"])}</b>{E(X.record(t))} · net {C.signed(R[t]["net"])} ({C.ordn(R[t]["rk"])}) · offense '
               f'{C.signed(R[t]["off"])} ({C.ordn(R[t]["rk_off"])}) · defense {C.signed(R[t]["def"])} ({C.ordn(R[t]["rk_def"])})')
        x, y = px(R[t]["off"]), py(R[t]["def"])
        if t in show:
            w_ = 9 + 7.2 * len(tm["abbr"])
            g.append(f'<g class="sc-pt tm-{E(tm["key"])}" tabindex="0" data-tip="{E(tip)}"><title>{E(tm["full"])}</title>'
                     f'<rect x="{x - w_ / 2:.1f}" y="{y - 10:.1f}" width="{w_:.0f}" height="20" rx="2"/>'
                     f'<text x="{x:.1f}" y="{y + 4.5:.1f}" text-anchor="middle">{E(tm["abbr"])}</text></g>')
        else:
            g.append(f'<g class="sc-pt sc-dot tm-{E(tm["key"])}" tabindex="0" data-tip="{E(tip)}"><title>{E(tm["full"])}</title>'
                     f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5"/></g>')
    g.append("</svg>")
    out = [HC.sec("efficiency", "Efficiency map", f'{HM} offense against defense {DOT} all {len(ids)} teams')]
    out.append(HC.brd("Who wins with what", "chips: the AP Top 25 and the house top 25; dots: everyone else (hover or tab for any team)",
                      f'<div class="sc-wrap">{"".join(g)}</div>', "dashed lines: the FBS average (0). Opponent-adjusted points per game, "
                      "not raw yards: a defense that faced three top-10 offenses is credited for it."))
    out.append("  </section>")
    return "\n".join(out)


# ============================================================================ team stats
def team_stats(X):
    defs = {d[0]: d for d in X.stat_defs}
    ids = sorted(X.stats, key=lambda t: -X.rat[t]["net"])

    def col(k, d=0, pc=True, label=None, sub=None):
        _, lab, side, hib, nd, unit = defs[k]

        def f(t):
            v, rk, p = X.stat(t, k)
            if v is None:
                return DASH
            txt = C.fmt(v, nd) + ("%" if unit == "%" else "")
            if k == "top":
                txt = f"{int(v // 60)}:{int(v % 60):02d}"
            return f'<span class="vp">{txt}{HC.pc(p) if pc and p is not None else ""}</span>'
        c = {"g": sub or "Per game", "h": label or lab, "f": f, "sk": (lambda t, _k=k: X.stat(t, _k)[0]), "asc": hib is False}
        if d:
            c["d"] = d
        return c
    base = [{"g": "Team", "h": "Team", "c": "l", "f": lambda t: X.team_cell(t, sub=X.conf_short(X.teams[t]["conf"]))}]
    off = base + [col("ppg", label="Pts"), col("ypp", label="Yds/play", sub="Efficiency"), col("ypg", 4, False, "Yds", "Per game"),
                  col("rypa", 3, True, "Yds/carry", "Efficiency"), col("pypa", 2, True, "Yds/pass", "Efficiency"),
                  col("cmp", 5, False, "Cmp%", "Efficiency"), col("3d", 3, True, "3rd down", "Efficiency"),
                  col("rypg", 6, False, "Rush yds", "Per game"), col("pypg", 6, False, "Pass yds", "Per game")]
    dfn = base + [col("papg", label="Pts allowed"), col("dypp", label="Yds/play", sub="Efficiency allowed"),
                  col("dypg", 4, False, "Yds", "Per game"), col("drypa", 3, True, "Yds/carry", "Efficiency allowed"),
                  col("dpypa", 2, True, "Yds/pass", "Efficiency allowed"), col("d3d", 3, True, "3rd down", "Efficiency allowed"),
                  col("sacks", 5, True, "Sacks", "Per game"), col("tfl", 6, False, "TFL", "Per game")]
    misc = base + [col("tom", label="TO margin", sub="Turnovers"), col("take", 2, True, "Takeaways", "Turnovers"),
                   col("give", 2, True, "Giveaways", "Turnovers"), col("sackr", 4, False, "Sacks taken", "Discipline"),
                   col("pen", 3, True, "Penalty yds", "Discipline"), col("top", 5, False, "Possession", "Discipline"),
                   col("fg", 4, False, "FG%", "Kicking"), col("punt", 5, False, "Net punt", "Kicking")]
    rows = [("row", t, "") for t in ids]
    note = (f'ESPN team statistics for every game played (FCS opponents included) {DOT} circles: percentile among the {len(ids)} FBS teams '
            f'on the locked scale (red is better, whichever way the stat runs)')
    items = [("ts-off", "Offense", HC.brd("Offense", "per game and per play", HC.rb_table(off, rows, 6, "lp-team", sort_default=1), note)),
             ("ts-def", "Defense", HC.brd("Defense", "what opponents did against them", HC.rb_table(dfn, rows, 6, "lp-team", sort_default=1), note)),
             ("ts-misc", "Turnovers & discipline", HC.brd("Turnovers, discipline and kicking", "", HC.rb_table(misc, rows, 5, "lp-team", sort_default=1), note))]
    out = [HC.sec("teamstats", "Team stats", f'all {len(ids)} FBS teams {DOT} ESPN team statistics {DOT} sortable')]
    out.append(HC.tabs("ts", items, "tap a header to sort · a team opens its page"))
    out.append("  </section>")
    return "\n".join(out)


# ============================================================================ season so far
def pulse(X, fin_all):
    reg = [e for e in fin_all if e["st"] == 2]
    fb2 = [e for e in reg if e["h"]["id"] in X.teams and e["a"]["id"] in X.teams]
    lined = [e for e in reg if e.get("cl") and e["cl"].get("spread") not in (None, 0)]
    fav_su = sum(1 for e in lined if (e["cl"]["spread"] < 0) == (e["h"]["score"] > e["a"]["score"]))
    ats_w = ats_l = ats_p = 0
    for e in lined:
        x = (e["h"]["score"] - e["a"]["score"]) + e["cl"]["spread"]
        fav_home = e["cl"]["spread"] < 0
        if abs(x) < 1e-9:
            ats_p += 1
        elif (x > 0) == fav_home:
            ats_w += 1
        else:
            ats_l += 1
    tot = [e for e in reg if e.get("cl") and e["cl"].get("total")]
    over = sum(1 for e in tot if e["h"]["score"] + e["a"]["score"] > e["cl"]["total"])
    under = sum(1 for e in tot if e["h"]["score"] + e["a"]["score"] < e["cl"]["total"])
    home = [e for e in fb2 if not e["neutral"]]
    hw = sum(1 for e in home if e["h"]["score"] > e["a"]["score"])
    fcs = [e for e in reg if (e["h"]["id"] in X.teams) != (e["a"]["id"] in X.teams)]
    fcs_up = [e for e in fcs if X.winner(e) not in X.teams]
    ups = [e for e in lined if (e["cl"]["spread"] < 0) != (e["h"]["score"] > e["a"]["score"])]
    big = max(ups, key=lambda e: abs(e["cl"]["spread"]), default=None)
    hi = max(reg, key=lambda e: e["h"]["score"] + e["a"]["score"], default=None)
    one = sum(1 for e in fb2 if abs(e["h"]["score"] - e["a"]["score"]) <= 8)
    # HOUSE MODEL scorecard (walk-forward pregame lines this season)
    sc = [e for e in fb2 if e.get("hm_pre") and e.get("cl") and e["cl"].get("spread") is not None]
    mae_h = sum(abs(e["hm_pre"]["line"] - (e["h"]["score"] - e["a"]["score"])) for e in sc) / len(sc) if sc else None
    mae_m = sum(abs(-e["cl"]["spread"] - (e["h"]["score"] - e["a"]["score"])) for e in sc) / len(sc) if sc else None
    bh = sum((e["hm_pre"]["p"] - (1 if e["h"]["score"] > e["a"]["score"] else 0)) ** 2 for e in sc) / len(sc) if sc else None
    pm = [(e["cl"].get("p_h"), 1 if e["h"]["score"] > e["a"]["score"] else 0) for e in sc if e["cl"].get("p_h") is not None]
    bm = sum((p - y) ** 2 for p, y in pm) / len(pm) if pm else None
    hfav = sum(1 for e in sc if (e["hm_pre"]["p"] >= 0.5) == (e["h"]["score"] > e["a"]["score"]))
    cells = [
        ("Favorites straight up", f"{fav_su}{EN}{len(lined) - fav_su}", f"{C.pct0(fav_su / len(lined)) if lined else DASH}", "by the closing line (pick’ems left out)"),
        ("Favorites against the spread", f"{ats_w}{EN}{ats_l}{EN}{ats_p}", f"{C.pct0(ats_w / max(1, ats_w + ats_l))}", "covers, misses, pushes against the closing line"),
        ("Totals", f"{over}{EN}{under}", "over–under", f"{len(tot)} games with a closing total"),
        ("Home teams", f"{hw}{EN}{len(home) - hw}", C.pct0(hw / len(home)) if home else DASH, "FBS v FBS, neutral sites left out"),
        ("FCS upsets", f"{len(fcs_up)}", f"of {len(fcs)}", "FBS v FCS games won by the FCS team"),
        ("One-score games", f"{one}", f"of {len(fb2)}", "FBS v FBS decided by 8 points or fewer"),
        ("Biggest upset by the line", f"{C.fmt(abs(big['cl']['spread']))}" if big else DASH, "points",
         (f"{E(X.score_txt(big))} {DOT} {E(X.week_label(big))} {DOT} {E(X.mk_txt(big, big['cl']))}" if big else "")),
        ("Highest-scoring game", f"{hi['h']['score'] + hi['a']['score']}" if hi else DASH, "points", (f"{E(X.score_txt(hi))} {DOT} {E(X.week_label(hi))}" if hi else "")),
        (f"{HM} scorecard", f"{C.fmt(mae_h, 2)}", "pts error", f"walk-forward on {len(sc)} FBS finals; the closing line {C.fmt(mae_m, 2)} "
         f"{DOT} Brier {C.fmt(bh, 3)} vs {C.fmt(bm, 3)} {DOT} favorite won {C.pct0(hfav / len(sc)) if sc else DASH}"),
    ]
    out = [HC.sec("pulse", "Season so far", f'{len(reg)} regular-season finals {DOT} ESPN scores and closing lines (core odds)')]
    out.append('    <div class="ps-g">' + "".join(f'<div class="ps"><div class="k">{k}</div><div class="v">{v}<small>{s}</small></div><div class="d">{d}</div></div>'
                                              for k, v, s, d in cells) + "</div>")
    out.append(f'    <p class="muted-p">The {HM} scorecard re-fits the ratings before every week with only the games already played, '
               f'then prices that week — the same walk-forward the calibration used. A model that beats the closing line here would be a bug '
               f'until proven otherwise; this one does not.</p>')
    out.append("  </section>")
    return "\n".join(out)


# ============================================================================ calendar + index
def calendar(X):
    f = X.facts
    out = [HC.sec("calendar", "Calendar", f'verified {E(f.get("verified") or "")} {DOT} C confirmed {DOT} R reported {DOT} U unpublished')]
    today = C.to_ct(X.now).strftime("%Y-%m-%d")
    items = []
    for x in f.get("calendar") or []:
        past = x["date"] < today
        d = C.parse_iso(x["date"] + "T17:00Z")
        items.append(f'<li class="{"past" if past else ""}"><b>{E(C.ct_day(d, True)) if d else E(x["date"])}</b><span>{E(x["what"])}</span>'
                     f'<span class="tag {E(x.get("tag") or "")}">{E(x.get("tag") or "")}</span></li>')
    cfp = f.get("cfp") or {}
    last = f.get("last_season") or {}
    out.append(f'    <div class="proj-g"><div class="paper"><ul class="cal-l">{"".join(items)}</ul></div>'
               f'<div class="paper"><div class="how"><div class="k" style="font-size:11px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.06em">The 2026–27 playoff</div>'
               f'<p style="margin-top:8px">{E(cfp.get("format") or "")}</p><p>{E(cfp.get("seeding") or "")}</p>'
               f'<p class="muted-p">{E(cfp.get("expansion") or "")} <span class="tag {E(cfp.get("expansion_tag") or "")}">{E(cfp.get("expansion_tag") or "")}</span></p>'
               f'<div class="sub-h">Last season</div><p><b>{E(last.get("champion") or "")}</b> {DOT} {E(last.get("title_game") or "")} {DOT} {E(last.get("record") or "")}</p>'
               f'<p class="muted-p">Sources: {E(cfp.get("source") or "")}; {E(last.get("source") or "")}.</p></div></div></div>')
    out.append("  </section>")
    return "\n".join(out)


def index(X):
    out = [HC.sec("allteams", f"All {len(X.teams)} teams", "by conference, in conference-standings order")]
    blocks = []
    for ck in X.conf_order:
        cf = X.confs[ck]
        mem = sorted(cf["members"], key=lambda t: (-(X.rec[t]["cw"] - X.rec[t]["cl"]), -X.rec[t]["cw"], -X.rat[t]["net"]))
        lis = "".join(f'<li><a href="#{E(X.key(t))}">{HC.chip(t)}<span>{E(X.loc(t))}</span></a></li>' for t in mem)
        blocks.append(f'<div class="idx"><h5><a href="#C-{ck}">{E(cf["short"])}</a> {DOT} {len(mem)}</h5><ul>{lis}</ul></div>')
    out.append('    <div class="idx-g">' + "".join(blocks) + "</div>")
    out.append("  </section>")
    return "\n".join(out)
