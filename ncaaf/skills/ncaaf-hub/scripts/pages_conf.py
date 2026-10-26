#!/usr/bin/env python3
"""pages_conf — one page per conference (#C-<CONF>): hero and strip, standings with HOUSE MODEL odds and Kalshi, the title
race, this week's games involving the conference, the members' power board and the non-conference record."""
import sys

sys.dont_write_bytecode = True
import hub_common as HC  # noqa: E402
import pages_team as PT  # noqa: E402
import pages_landing as PL  # noqa: E402

C = HC.C
E = HC.E
DASH, DOT, EN, MINUS, HM = HC.DASH, HC.DOT, HC.EN, HC.MINUS, HC.HM


def render(X, ck):
    cf = X.confs[ck]
    mem = cf["members"]
    S = X.sim
    nav, parts = [], []
    order = PT.conf_order(X, ck)
    # non-conference record
    nc = {"fbs_w": 0, "fbs_l": 0, "p4_w": 0, "p4_l": 0, "fcs_w": 0, "fcs_l": 0}
    for e in X.ev:
        if e["st"] != 2 or not e["status"]["completed"] or e["h"]["score"] is None:
            continue
        for me, op in ((e["h"], e["a"]), (e["a"], e["h"])):
            if me["id"] not in mem:
                continue
            if op["id"] in mem:
                continue
            won = me["score"] > op["score"]
            if op["id"] in X.teams:
                nc["fbs_w" if won else "fbs_l"] += 1
                if X.teams[op["id"]]["conf"] in ("SEC", "B1G", "B12", "ACC") or X.teams[op["id"]]["key"] == "ND":
                    nc["p4_w" if won else "p4_l"] += 1
            else:
                nc["fcs_w" if won else "fcs_l"] += 1
    fav = max(mem, key=lambda t: S[t]["p_conf"]) if ck != "IND" else max(mem, key=lambda t: S[t]["p_cfp"])
    kc = (X.kf.get("conf") or {}).get(ck) or {}
    kfav = max(kc, key=lambda t: kc[t]["p"]) if kc else None
    best = max(mem, key=lambda t: X.rat[t]["net"])
    title_line = next((x["what"] for x in (X.facts.get("calendar") or []) if cf["short"] in x["what"] and "Championship" in x["what"]), "")
    h = ['  <div class="lp-hero"><div class="lp-hero-in">',
         f'    <div class="lp-k">College football {DOT} {X.season} {DOT} {"FBS independents" if ck == "IND" else "conference"}</div>',
         f'    <div class="lp-t">{E(cf["short"])} <span>{"race" if ck != "IND" else "independents"}</span></div>',
         f'    <div class="lp-sub"><b>{E(cf["name"])}</b> {DOT} {len(mem)} teams'
         + (f' {DOT} divisions: {E(", ".join(cf["divs"]))}' if cf.get("divs") else "")
         + (f' {DOT} {E(title_line)}' if title_line else "") + "</div>",
         '  </div></div>']
    cells = []
    if ck != "IND":
        lead = order[0]
        cells.append(PL.cell("Leader", f'{HC.chip(lead)}{E(X.conf_record(lead))}', f'{X.team_link(lead)} {DOT} {E(X.record(lead))} overall'))
        cells.append(PL.cell(f"Title favorite {HM}", f'{HC.chip(fav)}{C.pct1(S[fav]["p_conf"])}', f'{X.team_link(fav)} {DOT} title game {C.pct0(S[fav]["p_ccg"])}'))
        if kfav:
            cells.append(PL.cell("Kalshi favorite", f'{HC.chip(kfav)}{C.pct0(kc[kfav]["p"])}', f'{X.team_link(kfav)} {DOT} YES price'))
    cells.append(PL.cell(f"Best team {HM}", f'{HC.chip(best)}{C.signed(X.rat[best]["net"])}<small> pts</small>', f'{X.team_link(best)} {DOT} {C.ordn(X.rat[best]["rk"])} in FBS'))
    exp = sum(S[t]["p_cfp"] for t in mem)
    cells.append(PL.cell(f"CFP teams {HM}", C.fmt(exp, 2), "expected in the 12-team field"))
    cells.append(PL.cell("Non-conference", f'{nc["fbs_w"]}{EN}{nc["fbs_l"]}', f'v FBS {DOT} v power {nc["p4_w"]}{EN}{nc["p4_l"]} {DOT} v FCS {nc["fcs_w"]}{EN}{nc["fcs_l"]}'))
    h.append('  <div class="snap">' + "".join(cells[:6]) + "</div>")
    parts.append("\n".join(h))
    if ck != "IND":
        parts.append("\n".join([HC.sec("standings", "Standings", f'{HM} title-game and title odds {DOT} Kalshi champion price'),
                                PT.conf_board(X, ck), "  </section>"]))
        nav.append(("standings", "Standings"))
        top = sorted(mem, key=lambda t: -S[t]["p_conf"])[:10]
        lad = HC.ladder([(f'{HC.chip(t)} {X.team_link(t)}', f'{E(X.conf_record(t))} conf {DOT} title game {C.pct1(S[t]["p_ccg"])}',
                          S[t]["p_conf"], "", (f'<small style="display:block;font-size:11px;color:var(--ink3);font-style:normal">Kalshi {C.pct0(kc[t]["p"])}</small>' if t in kc else ""))
                         for t in top])
        parts.append("\n".join([HC.sec("race", "Title race", f'{HM} {DOT} {X.smeta["sims"]:,} simulated seasons'),
                                f'    <div class="paper">{lad}<p class="muted-p">Sums: title game {C.fmt(X.smeta["sum_conf"][ck]["p_ccg"], 3)} '
                                f'(two places), champion {C.fmt(X.smeta["sum_conf"][ck]["p_conf"], 3)}.</p></div>', "  </section>"]))
        nav.append(("race", "Title race"))
    wk = X.week
    gs = [e for e in X.ev if e["st"] == 2 and e["week"] == wk and (e["h"]["id"] in mem or e["a"]["id"] in mem)]
    if gs:
        parts.append("\n".join([HC.sec("games", f"Week {wk}", f'{len(gs)} games involving the {E(cf["short"])}'),
                                '    <div class="sb-g">' + "".join(PL.sb_card(X, e) for e in sorted(gs, key=lambda e: e["date"] or "")) + "</div>",
                                f'    <p class="lp-live"><a class="wk-a" href="#W{wk}">The full Week {wk} slate ›</a></p>', "  </section>"]))
        nav.append(("games", f"Week {wk}"))
    R = X.rat
    ids = sorted(mem, key=lambda t: -R[t]["net"])
    rows = [("row", t, "") for t in ids]
    cols = [
        {"g": "Rank", "h": "FBS", "c": "rkc", "f": lambda t: str(R[t]["rk"]), "sk": lambda t: R[t]["rk"], "asc": True},
        {"g": "Team", "h": "Team", "c": "l", "f": lambda t: X.team_cell(t)},
        {"g": "Team", "h": "Rec", "f": lambda t: E(X.record(t))},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Net", "f": lambda t: f'<span class="vp">{C.signed(R[t]["net"])}{HC.pc(R[t]["pct"])}</span>', "sk": lambda t: R[t]["net"]},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Off", "d": 2, "f": lambda t: f'<span class="vp">{C.signed(R[t]["off"])}{HC.pc(R[t]["pct_off"])}</span>', "sk": lambda t: R[t]["off"]},
        {"g": "HOUSE MODEL", "gs": "House", "h": "Def", "d": 2, "f": lambda t: f'<span class="vp">{C.signed(R[t]["def"])}{HC.pc(R[t]["pct_def"])}</span>', "sk": lambda t: R[t]["def"]},
        {"g": "Odds", "h": "Proj W", "d": 1, "f": lambda t: C.fmt(S[t]["w"]), "sk": lambda t: S[t]["w"]},
        {"g": "Odds", "h": "Bowl", "d": 3, "f": lambda t: C.pct0(S[t]["p_bowl"]), "sk": lambda t: S[t]["p_bowl"]},
        {"g": "Odds", "h": "CFP", "f": lambda t: C.pct1(S[t]["p_cfp"]), "sk": lambda t: S[t]["p_cfp"]},
    ]
    parts.append("\n".join([HC.sec("power", "Power", f'{HM} ratings {DOT} FBS rank of {len(X.teams)}'),
                            HC.brd(f'{E(cf["short"])} by {HM} rating', "points better than an average FBS team, neutral field",
                                   HC.rb_table(cols, rows, 3, "lp-power", sort_default=0), "Circles: percentile among all FBS teams."),
                            "  </section>"]))
    nav.append(("power", "Power"))
    status = f'{len(mem)} teams' + (f' {DOT} leader {X.abbr(order[0])} {X.conf_record(order[0])}' if ck != "IND" else "")
    return "\n".join(parts), [list(n) for n in nav], status
