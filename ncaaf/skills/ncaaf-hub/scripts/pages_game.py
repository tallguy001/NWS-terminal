#!/usr/bin/env python3
"""pages_game — a page per game of this week and last (#G<ESPN event id>), the NFL / EPL League Hubs' games-v1 format.

Preview: hero (both teams, kickoff, venue, TV) → the line (HOUSE MODEL, DraftKings, Kalshi, side by side, never blended) →
tale of the tape (house ratings and team-stat percentiles, mirrored) → matchups (each offense against the other defense) →
form (recent results) → stakes (CFP / title-game / bowl odds with a win and with a loss).
Final: hero with the score → the score by quarter and every scoring play → team box (paired bars) → ESPN's win probability →
the forecasts against the result (HOUSE MODEL pregame walk-forward, the closing line, Kalshi's pre-kickoff price) → what it
means now (each team's CFP and title odds after the game)."""
import sys

sys.dont_write_bytecode = True
import hub_common as HC  # noqa: E402

C = HC.C
E = HC.E
DASH, DOT, EN, MINUS, HM = HC.DASH, HC.DOT, HC.EN, HC.MINUS, HC.HM


def render(X, e):
    st = X.state(e)
    final = st == "final"
    h, a = e["h"], e["a"]
    theme = X.winner(e) if final else h["id"]
    if theme not in X.teams:
        theme = a["id"] if a["id"] in X.teams else h["id"]
    label = (f'{X.abbr(a["id"], a)} {a["score"]}{EN}{h["score"]} {X.abbr(h["id"], h)}' if final
             else f'{X.abbr(a["id"], a)} {"vs" if e["neutral"] else "@"} {X.abbr(h["id"], h)}')
    parts, nav = [hero(X, e, st)], []
    if final:
        parts.append(scoring(X, e)); nav.append(("score", "Scoring"))
        parts.append(box(X, e)); nav.append(("box", "Team stats"))
        w = winprob(X, e)
        if w:
            parts.append(w); nav.append(("wp", "Win probability"))
        parts.append(forecasts(X, e)); nav.append(("forecasts", "Forecasts"))
        parts.append(means(X, e)); nav.append(("means", "What it means"))
        parts.append(tape(X, e, "Tale of the tape (today’s numbers)")); nav.append(("tape", "Tape"))
    else:
        parts.append(the_line(X, e)); nav.append(("line", "The line"))
        parts.append(tape(X, e)); nav.append(("tape", "Tale of the tape"))
        parts.append(matchups(X, e)); nav.append(("matchups", "Matchups"))
        parts.append(form(X, e)); nav.append(("form", "Form"))
        parts.append(stakes(X, e)); nav.append(("stakes", "Stakes"))
    status = (f"Final {DOT} {X.week_label(e)}" if final else f"{X.week_label(e)} {DOT} {' '.join(X.when(e)[:2][::-1])}")
    return "\n".join(parts), [list(n) for n in nav], {"label": label, "theme": theme, "status": status, "kind": "final" if final else "pre"}


def hero(X, e, st):
    h, a = e["h"], e["a"]
    t_, day, utc = X.when(e)
    final = st == "final"
    w = X.winner(e)
    rows = []
    for s, lab in (("a", "away" if not e["neutral"] else ""), ("h", "home" if not e["neutral"] else "")):
        side = e[s]
        tid = side["id"]
        nm = E(X.loc(tid, side))
        nick = E((X.teams.get(tid) or {}).get("nick") or "")
        link = f'<a href="#{E(X.key(tid))}">{nm}</a>' if tid in X.teams else nm
        sub = (X.record(tid) if tid in X.teams else "FCS") + (f" {DOT} {lab}" if lab else "") + (f" {DOT} AP No. {X.ap[tid]}" if tid in X.ap else "")
        sc = "" if side["score"] is None or not final else str(side["score"])
        rows.append(f'<div class="gx-row">{HC.chip(tid, side.get("abbr"))}<div class="gx-nm"><b>{link} <span class="brew">{nick}</span></b>'
                    f'<small>{E(sub)}</small></div><span class="gx-sc{" dim" if final and w != tid else ""}">{sc}</span></div>')
    v = e["venue"]
    vl = ", ".join(x for x in (v.get("name"), v.get("city"), v.get("state")) if x)
    kind = "conference championship" if X.is_title(e) else ("conference game" if e["conf"] else "non-conference")
    meta = [f"<b>{E(day)}</b> {E(t_)}" + (f" ({E(utc)})" if utc else ""), E(vl) + (" · neutral site" if e["neutral"] else ""),
            "TV " + (E(" / ".join(e["tv"])) or "TBA"), E(kind)]
    if e["notes"]:
        meta.append(E(e["notes"][0]))
    if final:
        att = (X.gsum.get(e["eid"]) or {}).get("attendance")
        if att:
            meta.append(f"attendance {int(att):,}")
    k = (f'{E(X.week_label(e))} {DOT} ' + ("Final" if final else ("Under way" if st in ("live", "underway") else "Preview")))
    return (f'  <div class="gx-hero"><div class="gx-k">{k}</div><div class="gx-rows">{"".join(rows)}</div>'
            f'<div class="gx-meta">{" · ".join(f"<span>{m}</span>" for m in meta)}</div></div>')


def wr(label, p, tm_key, sub=""):
    """A win-chance row: label, a bar from the middle toward the favorite, the number."""
    if p is None:
        return f'<p class="gm-wr"><span class="k">{label}</span><span class="muted-c">{sub or "not available"}</span><b>{DASH}</b></p>'
    side = "left" if p < 0.5 else "right"
    w = abs(p - 0.5) * 100
    style = f"left:{50 - w:.1f}%;width:{w:.1f}%" if side == "left" else f"left:50%;width:{w:.1f}%"
    return (f'<p class="gm-wr"><span class="k">{label}' + (f'<small style="display:block;color:var(--ink3);font-size:11px">{sub}</small>' if sub else "")
            + f'</span><span class="gm-wb tm-{E(tm_key)}"><i style="{style}"></i></span><b>{C.pct1(max(p, 1 - p))}</b></p>')


def the_line(X, e):
    h, a = e["h"], e["a"]
    hm = e["hm"]
    o = e.get("odds") or {}
    k = X.kg.get(e["eid"])
    hk = X.key(h["id"]) or "NCAAF"
    ak = X.key(a["id"]) or "NCAAF"

    def row(lab, p, sub):
        if p is None:
            return wr(lab, None, hk, sub)
        return wr(lab, p, hk if p >= 0.5 else ak, sub)
    hab, aab = X.abbr(h["id"], h), X.abbr(a["id"], a)
    rows = [row(f'{HM}', hm["p"], f'{E(C.line_txt(-hm["line"], hab, aab))} {DOT} total {C.fmt(hm["total"])}'),
            row("DraftKings", o.get("p_h"), (f'{E(X.mk_txt(e, o))} {DOT} total {C.fmt(o.get("total"))} {DOT} moneyline no-vig' if o.get("spread") is not None else "not posted")),
            row("Kalshi", k["p_home"] if k else None, (f'{"pre-kickoff" if k.get("pre") else "book"} {DOT} {k["c_home"]}¢ / {k["c_away"]}¢ {DOT} {k["vol"]:,} contracts{" · thin" if k.get("thin") else ""}' if k else ("not listed" if X.kal_ok else "not read this build")))]
    reads = []
    if o.get("spread") is not None:
        gap = hm["line"] + o["spread"]
        if abs(gap) >= 3:
            side = h if gap > 0 else a
            reads.append(f'The {HM} line is {C.fmt(abs(gap))} points more favorable to {E(X.loc(side["id"], side))} than DraftKings’ — a disagreement, '
                         f'not an edge: the closing market beat the house in every held-out season.')
        else:
            reads.append(f'The {HM} and DraftKings are within {C.fmt(abs(gap))} points.')
    if k and o.get("p_h") is not None and abs(k["p_home"] - o["p_h"]) >= 0.05:
        reads.append(f'Kalshi and DraftKings differ by {C.fmt(100 * abs(k["p_home"] - o["p_h"]), 1)} points of win chance — two markets disagreeing.')
    head = (f'<div class="gm-we"><span>{HC.chip(a["id"], a.get("abbr"))}{E(aab)} favored ←</span><span>→ {E(hab)} favored{HC.chip(h["id"], h.get("abbr"))}</span></div>')
    return "\n".join([HC.sec("line", "The line", f'{HM} beside DraftKings and Kalshi {DOT} never blended'),
                      f'    <div class="paper gm-why">{head}{"".join(rows)}{HC.read_block(reads)}</div>', "  </section>"])


def tape(X, e, title="Tale of the tape"):
    h, a = e["h"], e["a"]
    n = len(X.teams)

    def side_rows():
        rows = []
        specs = [("Power", lambda t: X.rat.get(t, {}).get("net"), lambda t: X.rat.get(t, {}).get("pct"), lambda v: C.signed(v)),
                 ("Offense", lambda t: X.rat.get(t, {}).get("off"), lambda t: X.rat.get(t, {}).get("pct_off"), lambda v: C.signed(v)),
                 ("Defense", lambda t: X.rat.get(t, {}).get("def"), lambda t: X.rat.get(t, {}).get("pct_def"), lambda v: C.signed(v))]
        for k_, lab in (("ppg", "Points per game"), ("ypp", "Yards per play"), ("rypa", "Yards per carry"), ("pypa", "Yards per pass"),
                        ("3d", "Third downs"), ("papg", "Points allowed"), ("dypp", "Yards per play allowed"), ("tom", "Turnover margin")):
            nd = next((d[4] for d in X.stat_defs if d[0] == k_), 1)
            unit = next((d[5] for d in X.stat_defs if d[0] == k_), "")
            specs.append((lab, (lambda t, _k=k_: X.stat(t, _k)[0]), (lambda t, _k=k_: X.stat(t, _k)[2]),
                          (lambda v, _nd=nd, _u=unit: C.fmt(v, _nd) + ("%" if _u == "%" else ""))))
        for lab, fv, fp, ff in specs:
            cells = []
            for tid, cls in ((a["id"], "l"), (h["id"], "r")):
                v, p = fv(tid), fp(tid)
                if v is None:
                    cells.append(f'<div class="tp-v {cls}"><span class="tp-val">{DASH}</span><span class="tp-track none"></span></div>')
                    continue
                w = 0 if p is None else max(3, min(100, p))
                col = HC.sav_color(p) if p is not None else "var(--ln2)"
                pos = f"right:{w:.1f}%" if cls == "l" else f"left:{w:.1f}%"
                bub = (f'<span class="bub" style="{pos};background:{col};color:{HC.ink(p)}" title="{E(HC.pct_word(p))}">{HC.pct_int(p)}</span>'
                       if p is not None else "")
                cells.append(f'<div class="tp-v {cls}"><span class="tp-val">{ff(v)}</span><span class="tp-track"><i class="tp-fill" '
                             f'style="width:{w:.1f}%;background:{col}"></i>{bub}</span></div>')
            rows.append(f'<div class="tp-row">{cells[0]}<div class="tp-k">{lab}</div>{cells[1]}</div>')
        return "".join(rows)

    def side(tid, s, cls):
        nm = E(X.loc(tid, s))
        meta = (X.record(tid) if tid in X.teams else "FCS") + (f" · AP No. {X.ap[tid]}" if tid in X.ap else "")
        conf = E(X.conf_short(X.teams[tid]["conf"])) if tid in X.teams else "FCS"
        return (f'<div class="tp-side {cls}"><div class="tp-meta">{HC.chip(tid, s.get("abbr"))}<span>{E(meta)}</span></div>'
                f'<div class="p-name">{nm}</div><div class="p-team">{conf}'
                + (f' {DOT} {HM} {C.ordn(X.rat[tid]["rk"])} of {n}' if tid in X.rat else "") + '</div></div>')
    body = (f'<div class="tape"><div class="tp-names">{side(a["id"], a, "")}<div class="tp-vs">vs</div>{side(h["id"], h, "r")}</div>'
            f'<div class="tp-rows">{side_rows()}</div>'
            f'<div class="mu-read"><span class="tag">How to read it</span>Bars fill to each team’s percentile among the {n} FBS teams '
            f'(red is better, whichever way the stat runs). Power, offense and defense are {HM} points; the rest are ESPN team statistics '
            f'for the season.</div></div>')
    return "\n".join([HC.sec("tape", title, f'{HM} ratings and team statistics {DOT} percentiles among {n} FBS teams'), body, "  </section>"])


def matchups(X, e):
    h, a = e["h"], e["a"]
    n = len(X.teams)
    cards = []
    for off, dfn in ((a, h), (h, a)):
        for ko, kd, lab in (("ypp", "dypp", "Yards per play"), ("rypa", "drypa", "Run game"), ("pypa", "dpypa", "Pass game"), ("3d", "d3d", "Third downs")):
            vo, ro, po = X.stat(off["id"], ko)
            vd, rd, pd = X.stat(dfn["id"], kd)
            if vo is None or vd is None or po is None or pd is None:
                continue
            diff = po - pd
            tag = ("Edge " + X.abbr(off["id"], off)) if diff >= 25 else (("Wall " + X.abbr(dfn["id"], dfn)) if diff <= -25 else
                                                                          ("Strength on strength" if po >= 65 and pd >= 65 else ("Weak on weak" if po <= 35 and pd <= 35 else "Even")))
            cards.append(f'<div class="gm-mm{" d" if diff < 0 else ""}"><div class="k">{HC.chip(off["id"], off.get("abbr"))} offense v {HC.chip(dfn["id"], dfn.get("abbr"))} defense</div>'
                         f'<div class="v">{lab}</div><div class="s">{E(X.abbr(off["id"], off))} {C.fmt(vo, 2 if ko != "3d" else 1)}{"%" if ko == "3d" else ""} '
                         f'({C.ordn(ro)}) against {E(X.abbr(dfn["id"], dfn))} allowing {C.fmt(vd, 2 if kd != "d3d" else 1)}{"%" if kd == "d3d" else ""} ({C.ordn(rd)})'
                         f'<small>{E(tag)} · percentiles {HC.pct_int(po)} v {HC.pct_int(pd)}</small></div></div>')
    if not cards:
        cards.append('<div class="gm-mo"><div class="s">Team statistics are not available for an FCS opponent.</div></div>')
    return "\n".join([HC.sec("matchups", "Matchups", f'each offense against the other defense {DOT} ESPN team statistics {DOT} ranks of {n}'),
                      f'    <div class="gm-mmg">{"".join(cards)}</div>',
                      f'    <p class="muted-p">Tags: Edge when the offense’s percentile beats the defense’s by 25+, Wall the other way; '
                      f'Strength on strength / Weak on weak when both sit above 65 or below 35. Season numbers, not adjusted for opponents.</p>', "  </section>"])


def form(X, e):
    blocks = []
    for s in ("a", "h"):
        side = e[s]
        tid = side["id"]
        if tid not in X.teams:
            continue
        past = [g for g in X.by_team[tid] if g["status"]["completed"] and g["date"] < e["date"]][-5:]
        chips = []
        for g in past:
            o = g["a"] if g["h"]["id"] == tid else g["h"]
            won = X.winner(g) == tid
            chips.append(f'<span class="res"><b class="{"w" if won else "l"}">{"W" if won else "L"}</b> {X.score_txt(g, tid)} '
                         f'{"vs" if (g["neutral"] or g["h"]["id"] == tid) else "at"} {HC.chip(o["id"], o.get("abbr"))}'
                         f'{X.team_link(o["id"], o, X.abbr(o["id"], o))}</span>')
        blocks.append(f'<div class="sub-h">{HC.chip(tid)} {E(X.loc(tid))} {DOT} last {len(past)}</div><div class="res-row">{"".join(chips) or "no games yet"}</div>')
    return "\n".join([HC.sec("form", "Form", "recent results, newest last"), f'    <div class="paper">{"".join(blocks)}</div>', "  </section>"])


def stakes(X, e):
    rows = []
    for s in ("a", "h"):
        side = e[s]
        tid = side["id"]
        if tid not in X.teams:
            continue
        stk = (X.sim.get(tid) or {}).get("stakes") or {}
        if stk.get("eid") != e["eid"]:
            continue
        S = X.sim[tid]
        for lab, key, now in (("CFP", "cfp", S["p_cfp"]), ("Title game", "ccg", S["p_ccg"]), ("Bowl eligible", "bowl", S["p_bowl"])):
            w_, l_ = stk.get(key, (None, None))
            if w_ is None or l_ is None or (max(w_, l_) < 0.005) or (min(w_, l_) > 0.995):
                continue
            rows.append(f'<tr><td><span class="tm">{HC.chip(tid)}<b>{E(X.abbr(tid))}</b></span></td><td>{lab}</td><td class="r">{C.pct1(now)}</td>'
                        f'<td class="r"><b>{C.pct1(w_)}</b></td><td class="r">{C.pct1(l_)}</td><td class="r">{C.signed(100 * (w_ - l_))} pts</td></tr>')
    tb = (f'<table class="tbl"><thead><tr><th>Team</th><th>Odds</th><th class="r">Now</th><th class="r">With a win</th><th class="r">With a loss</th>'
          f'<th class="r">Swing</th></tr></thead><tbody>{"".join(rows) or "<tr><td colspan=6>Nothing riding on it in the simulation.</td></tr>"}</tbody></table>')
    return "\n".join([HC.sec("stakes", "Stakes", f'{HM} season simulation {DOT} the same seasons split by this result'),
                      f'    <div class="paper">{tb}<p class="muted-p">A win also says something about a team’s strength, and the simulation '
                      f'keeps that (the seasons where a team wins this game are, on average, seasons where it is a little stronger).</p></div>', "  </section>"])


# ============================================================================ finals
def scoring(X, e):
    gs = X.gsum.get(e["eid"]) or {}
    T = gs.get("teams") or {}
    h, a = e["h"], e["a"]
    ls_a = (T.get("away") or {}).get("ls") or []
    ls_h = (T.get("home") or {}).get("ls") or []
    nq = max(len(ls_a), len(ls_h), 4)
    qh = "".join(f'<th>{"OT" if i == 4 and nq == 5 else (f"OT{i - 3}" if i >= 4 else str(i + 1))}</th>' for i in range(nq))

    def lr(side, ls):
        cells = "".join(f'<td>{E(str(ls[i])) if i < len(ls) else DASH}</td>' for i in range(nq))
        return f'<tr><td><span class="tm">{HC.chip(side["id"], side.get("abbr"))} {E(X.loc(side["id"], side))}</span></td>{cells}<td class="t">{side["score"]}</td></tr>'
    tbl = f'<div class="tblwrap"><table class="ls"><thead><tr><th>Team</th>{qh}<th>T</th></tr></thead><tbody>{lr(a, ls_a)}{lr(h, ls_h)}</tbody></table></div>'
    items = []
    for p in gs.get("scoring") or []:
        tid = p.get("tid")
        side = h if tid == h["id"] else (a if tid == a["id"] else {"id": tid, "abbr": "?"})
        q = p.get("q")
        qlab = f"Q{q}" if q and q <= 4 else ("OT" if q else "")
        items.append(f'<li><span class="q">{qlab} {E(p.get("clock") or "")}</span>{HC.chip(side["id"], side.get("abbr"))}'
                     f'<span>{E(p.get("text") or "")}</span><span class="s">{p.get("a")}{EN}{p.get("h")}</span></li>')
    spl = f'<ul class="spl">{"".join(items)}</ul>' if items else '<p class="muted-p">No scoring plays in the feed.</p>'
    return "\n".join([HC.sec("score", "Scoring", f'ESPN game summary {DOT} score shown away–home'),
                      f'    <div class="paper">{tbl}<div class="sub-h">Every scoring play</div>{spl}</div>', "  </section>"])


BOX = [("firstDowns", "First downs"), ("totalYards", "Total yards"), ("netPassingYards", "Passing yards"), ("completionAttempts", "Comp–att"),
       ("yardsPerPass", "Yards per pass"), ("rushingYards", "Rushing yards"), ("rushingAttempts", "Rushes"), ("yardsPerRushAttempt", "Yards per rush"),
       ("thirdDownEff", "Third downs"), ("fourthDownEff", "Fourth downs"), ("turnovers", "Turnovers"), ("totalPenaltiesYards", "Penalties–yards"),
       ("possessionTime", "Possession")]


def _num(s):
    try:
        if s is None:
            return None
        s = str(s)
        if ":" in s:
            m, x = s.split(":")[:2]
            return int(m) * 60 + int(x)
        if "-" in s:
            a_, b_ = s.split("-")[:2]
            return float(a_) / float(b_) if float(b_) else 0.0
        return float(s)
    except (ValueError, TypeError):
        return None


def box(X, e):
    gs = X.gsum.get(e["eid"]) or {}
    B = gs.get("box") or {}
    h, a = e["h"], e["a"]
    ba, bh = B.get(a["id"]) or {}, B.get(h["id"]) or {}
    if not ba and not bh:
        return "\n".join([HC.sec("box", "Team stats", "ESPN box score"), '    <div class="paper"><p>Box score not in the feed yet.</p></div>', "  </section>"])
    lower_better = {"turnovers", "totalPenaltiesYards"}
    rows = []
    for k, lab in BOX:
        va, vh = ba.get(k), bh.get(k)
        if va is None and vh is None:
            continue
        na, nh = _num(va), _num(vh)
        if k == "totalPenaltiesYards":
            na, nh = _num((va or "").split("-")[-1]), _num((vh or "").split("-")[-1])
        if k in ("completionAttempts",):
            na, nh = _num((va or "").split("-")[0]), _num((vh or "").split("-")[0])
        mx = max(abs(na or 0), abs(nh or 0), 1e-9)
        wa = 100 * (na or 0) / mx
        whh = 100 * (nh or 0) / mx
        better_a = (na is not None and nh is not None) and ((na < nh) if k in lower_better else (na > nh))
        better_h = (na is not None and nh is not None) and ((nh < na) if k in lower_better else (nh > na))
        rows.append(f'<div class="v l tm-{E(X.key(a["id"]) or "fcs")}{" win" if better_a else ""}"><b>{E(str(va or DASH))}</b><i style="width:{wa:.0f}%"></i></div>'
                    f'<div class="k">{lab}</div>'
                    f'<div class="v tm-{E(X.key(h["id"]) or "fcs")}{" win" if better_h else ""}"><b>{E(str(vh or DASH))}</b><i style="width:{whh:.0f}%"></i></div>')
    hdr = (f'<div class="bx-h"><span>{HC.chip(a["id"], a.get("abbr"))}{E(X.abbr(a["id"], a))}</span><span></span>'
           f'<span>{E(X.abbr(h["id"], h))}{HC.chip(h["id"], h.get("abbr"))}</span></div>')
    return "\n".join([HC.sec("box", "Team stats", "ESPN box score · bars scaled to the larger of the two; bold = the better side"),
                      f'    <div class="paper">{hdr}<div class="bx">{"".join(rows)}</div></div>', "  </section>"])


def winprob(X, e):
    gs = X.gsum.get(e["eid"]) or {}
    wp = gs.get("wp") or []
    if len(wp) < 10:
        return ""
    h, a = e["h"], e["a"]
    W, H, L, R, T, B = 900, 260, 46, 884, 14, 236
    n = len(wp)
    pts = " ".join(f"{L + (R - L) * i / (n - 1):.1f},{B - (B - T) * p:.1f}" for i, p in enumerate(wp))
    lo = min(range(n), key=lambda i: wp[i])
    hi = max(range(n), key=lambda i: wp[i])
    svg = (f'<svg class="wp-svg" viewBox="0 0 {W} {H}" role="img" aria-label="ESPN win probability for {E(X.abbr(h["id"], h))} over the game">'
           f'<line class="ax" x1="{L}" y1="{T}" x2="{L}" y2="{B}"/><line class="ax" x1="{L}" y1="{B}" x2="{R}" y2="{B}"/>'
           f'<line class="mid" x1="{L}" y1="{(T + B) / 2}" x2="{R}" y2="{(T + B) / 2}"/>'
           f'<text x="{L - 6}" y="{T + 4}" text-anchor="end">{E(X.abbr(h["id"], h))}</text>'
           f'<text x="{L - 6}" y="{B}" text-anchor="end">{E(X.abbr(a["id"], a))}</text>'
           f'<text x="{L - 6}" y="{(T + B) / 2 + 4}" text-anchor="end">50%</text>'
           f'<polyline class="ln" points="{pts}"/></svg>')
    note = (f'{E(X.abbr(h["id"], h))}’s chance per play: low {C.pct0(wp[lo])}, high {C.pct0(wp[hi])} {DOT} {n} plays. ESPN’s model, '
            f'not the house’s; shown as published.')
    return "\n".join([HC.sec("wp", "Win probability", "ESPN’s in-game model, home team’s chance by play"),
                      f'    <div class="paper">{svg}<p class="muted-p">{note}</p></div>', "  </section>"])


def forecasts(X, e):
    h, a = e["h"], e["a"]
    hk, ak = X.key(h["id"]) or "NCAAF", X.key(a["id"]) or "NCAAF"
    hm = e.get("hm_pre")
    cl = e.get("cl") or {}
    k = X.kg.get(e["eid"])
    hab, aab = X.abbr(h["id"], h), X.abbr(a["id"], a)
    w = X.winner(e)
    margin = e["h"]["score"] - e["a"]["score"]
    rows = []

    def row(lab, p, sub):
        rows.append(wr(lab, p, hk if (p or 0.5) >= 0.5 else ak, sub))
    row(f"{HM} pregame", hm["p"] if hm else None,
        (f'walk-forward line {E(C.line_txt(-hm["line"], hab, aab))} {DOT} total {C.fmt(hm["total"])}' if hm else "no pregame fit"))
    row("Closing market", cl.get("p_h"), (f'{E(X.mk_txt(e, cl))} {DOT} total {C.fmt(cl.get("total"))} {DOT} {E(cl.get("prov") or "")}, moneyline no-vig' if cl.get("spread") is not None else "no closing line"))
    row("Kalshi pre-kickoff", k["p_home"] if k else None, (f'{k["c_home"]}¢ / {k["c_away"]}¢ {DOT} {k["vol"]:,} contracts in the 24 h before' if k else "not listed"))
    res = (f'<p class="gm-wsum"><b>Result:</b> {E(X.abbr(w, h if w == h["id"] else a))} by {abs(margin)} '
           f'({E(X.score_txt(e))}).' + (f' The house line missed by {C.fmt(abs(hm["line"] - margin))} points, the closing line by '
                                        f'{C.fmt(abs(-cl["spread"] - margin))}.' if hm and cl.get("spread") is not None else "") + "</p>")
    head = (f'<div class="gm-we"><span>{HC.chip(a["id"], a.get("abbr"))}{E(aab)} favored ←</span><span>→ {E(hab)} favored{HC.chip(h["id"], h.get("abbr"))}</span></div>')
    return "\n".join([HC.sec("forecasts", "Forecasts against the result", "three pregame numbers, never blended"),
                      f'    <div class="paper gm-why">{head}{"".join(rows)}{res}</div>', "  </section>"])


def means(X, e):
    rows = []
    for s in ("a", "h"):
        side = e[s]
        tid = side["id"]
        if tid not in X.teams:
            continue
        S = X.sim[tid]
        rows.append(f'<tr><td><span class="tm">{HC.chip(tid)}{X.team_link(tid)}</span></td><td>{E(X.record(tid))}</td>'
                    f'<td class="r">{C.pct1(S["p_cfp"])}</td><td class="r">{C.pct1(S["p_conf"]) if X.teams[tid]["conf"] != "IND" else DASH}</td>'
                    f'<td class="r">{C.pct0(S["p_bowl"])}</td><td class="r">{C.fmt(S["w"])}</td></tr>')
    tb = (f'<table class="tbl"><thead><tr><th>Team</th><th>Record</th><th class="r">CFP</th><th class="r">Conf title</th><th class="r">Bowl</th>'
          f'<th class="r">Proj W</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')
    return "\n".join([HC.sec("means", "What it means", f'{HM} season simulation after this game'),
                      f'    <div class="paper">{tb}</div>', "  </section>"])
