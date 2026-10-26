#!/usr/bin/env python3
"""hub_build.py — deterministic renderer for the NCAAF League Hub (the NFL / NHL / EPL League Hubs' design, ported).

    python3 hub_build.py league --pull league.json --out-dir OUT

Writes OUT/index.html (the shell: header, picker, theme, router) and the view fragments it fetches:
  league/NCAAF.json          the league home (pages_landing)
  teams/<KEY>.json ×138      one page per FBS team (pages_team)
  confs/<CONF>.json ×11      one page per conference (pages_conf)
  weeks/W<n>.json ×15 (+WP)  the league schedule, a week per view (pages_week)
  games/w<n>.json            game pages for this week and last, bundled by week (pages_game)
  publish-files.json         the Artifact publish arguments (file_path, root, files)
and QA-only files (never published): league-hub-full.html (every fragment inline, for ncaaf-qa) and games-qa.html.

Machine work only: hub_pull.py supplies every number; nothing is authored. The <head> (fonts + CSS) is lifted from
assets/hub-template.html (the NFL League Hub's stylesheet); team colors come from ncaaf-data-pull/ncaaf_theme.py at build time.
No player pages (owner, 2026-10-26: "No player cards, just teams").
"""
import argparse
import json
import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_common as HC  # noqa: E402
import hub_ctx  # noqa: E402
import league_shell as LSH  # noqa: E402
import ncaaf_css as NC  # noqa: E402

E = HC.E
TH = HC.TH
DOT, DASH = HC.DOT, HC.DASH
TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "assets", "hub-template.html"))
LAND = HC.LAND
HOUSE_KEY = "WIS"        # the house team (owner, 2026-10-26: "House team is Wisconsin"); --house overrides
WARN = []


def warn(m):
    if m not in WARN:
        WARN.append(m)


def load_head():
    tpl = open(TEMPLATE, encoding="utf-8").read()
    head = tpl.split("<head>", 1)[1].split("</head>", 1)[0]
    head = re.sub(r"<meta[^>]*>\s*", "", head)
    head = re.sub(r"<title>.*?</title>\s*", "", head, flags=re.S)
    head = re.sub(r"<!--.*?-->\s*", "", head, flags=re.S)
    head = head.replace("</style>", NC.NCAAF_CSS + "</style>", 1)
    return head.strip() + '\n<style id="tm-chips">\n' + TH.chips_css() + "\n</style>"


def _structure_check(page, what="HTML structure"):
    from html.parser import HTMLParser
    VOID = {"br", "meta", "link", "img", "hr", "input", "col", "source", "wbr", "path", "circle", "rect", "line", "polyline",
            "polygon", "ellipse", "stop", "use"}

    class Chk(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.bad = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in VOID:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if tag in VOID:
                return
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()
            else:
                self.bad.append(tag)
    c = Chk()
    c.feed(page)
    if c.stack or c.bad:
        warn(f"{what}: unclosed={c.stack[-5:]} mismatched={c.bad[:5]}")
        return False
    return True


def build_league(P, out_dir, house=None):
    X = hub_ctx.X(P)
    hk = house if house is not None else HOUSE_KEY
    if hk and not HC.set_house(hk):
        warn(f"house team {hk} is not an FBS key in this season's registry — no house treatment")
    import pages_landing as PL
    import pages_team as PT
    import pages_conf as PC
    import pages_week as PW
    import pages_game as PG
    views = {}          # route key -> {"html", "nav"} fragment
    meta = {}           # route key -> {theme, nick, chip, status, file, crumb}
    files = {}          # route key -> relative file
    # ---- game pages first (so every other view links only to pages that exist)
    gscope = [e for e in X.ev if e["st"] == 2 and e["week"] in (X.week - 1, X.week)]
    X.game_pages = {e["eid"] for e in gscope}
    gb, gidx, gqa = {}, {}, []
    for e in gscope:
        try:
            h_, nav_, m_ = PG.render(X, e)
        except Exception as ex:  # noqa: BLE001
            import traceback
            warn(f"game page {e['eid']} failed: {type(ex).__name__}: {ex} @ {traceback.extract_tb(ex.__traceback__)[-1].lineno}")
            X.game_pages.discard(e["eid"])
            continue
        b = f"w{e['week']:02d}"
        gb.setdefault(b, {})[e["eid"]] = {"html": h_, "nav": nav_}
        theme_key = X.key(m_["theme"]) or LAND
        gidx[e["eid"]] = [m_["label"], theme_key, b, m_["status"]]
        gqa.append((e["eid"], h_))
    # ---- league home
    h, nav, status = PL.render(X)
    views[LAND] = {"html": h, "nav": nav}
    meta[LAND] = {"theme": HC.theme_css(LAND), "nick": "League", "chip": HC.chip(LAND), "status": status,
                  "file": f"league/{LAND}.json", "crumb": "League"}
    # ---- teams
    for tid, t in X.teams.items():
        try:
            h, nav, status = PT.render(X, tid)
        except Exception as ex:  # noqa: BLE001
            import traceback
            warn(f"team page {t['abbr']} failed: {type(ex).__name__}: {ex} @ {traceback.extract_tb(ex.__traceback__)[-1].lineno}")
            raise
        k = t["key"]
        views[k] = {"html": h, "nav": nav}
        meta[k] = {"theme": HC.theme_css(k), "nick": t["loc"], "chip": HC.chip(tid), "status": status,
                   "file": f"teams/{k}.json", "crumb": t["loc"]}
    # ---- conferences
    for ck, cf in X.confs.items():
        h, nav, status = PC.render(X, ck)
        k = f"C-{ck}"
        views[k] = {"html": h, "nav": nav}
        meta[k] = {"theme": HC.theme_css(LAND), "nick": cf["short"], "chip": HC.chip(LAND), "status": status,
                   "file": f"confs/{ck}.json", "crumb": cf["short"]}
    # ---- weeks
    for c in X.reg_weeks:
        w = c["week"]
        h, nav, status = PW.render(X, w)
        k = f"W{w}"
        views[k] = {"html": h, "nav": nav}
        meta[k] = {"theme": HC.theme_css(LAND), "nick": f"Week {w}", "chip": HC.chip(LAND), "status": status,
                   "file": f"weeks/W{w}.json", "crumb": f"Week {w}"}
    if any(e["st"] == 3 for e in X.ev):
        h, nav, status = PW.render(X, "P")
        views["WP"] = {"html": h, "nav": nav}
        meta["WP"] = {"theme": HC.theme_css(LAND), "nick": "Postseason", "chip": HC.chip(LAND), "status": status,
                      "file": "weeks/WP.json", "crumb": "Postseason"}
    # ---- picker sheet: League + conferences, then teams by conference
    wkb = "".join(f'<button type="button" class="lg-wkb{" now" if c["week"] == X.week else ""}" data-ab="W{c["week"]}" aria-current="false" '
                  f'title="Week {c["week"]}, {E(c.get("detail") or "")}">{c["week"]}</button>' for c in X.reg_weeks)
    if any(e["st"] == 3 for e in X.ev):
        wkb += '<button type="button" class="lg-wkb" data-ab="WP" aria-current="false" title="Postseason">P</button>'
    sheet = [f'<button type="button" class="lg-team lg-home tm-{LAND}" data-ab="{LAND}" aria-current="false">{HC.chip(LAND)}'
             f'<span class="lg-nk">League home</span><span class="lg-pw">{len(X.teams)} teams</span><span class="lg-rc">Week {X.week}</span></button>',
             (f'<button type="button" class="lg-team tm-{E(HC.HOUSE["key"])}" data-ab="{E(HC.HOUSE["key"])}" aria-current="false">{HC.chip(HC.HOUSE["id"])}'
              f'<span class="lg-nk">{E(X.loc(HC.HOUSE["id"]))} {DOT} house team</span><span class="lg-pw">{("#" + str(X.ap[HC.HOUSE["id"]])) if HC.HOUSE["id"] in X.ap else ""}</span>'
              f'<span class="lg-rc">{E(X.record(HC.HOUSE["id"]))}</span></button>' if HC.HOUSE["id"] else ""),
             '<div class="lg-confs" aria-label="Conferences">' + "".join(
                 f'<button type="button" data-ab="C-{ck}" aria-current="false">{E(X.confs[ck]["short"])}</button>' for ck in X.conf_order) + '</div>',
             f'<div class="lg-div" style="grid-column:1/-1"><h3>League schedule {DOT} weeks</h3><div class="lg-wkg">{wkb}</div></div>',
             f'<div class="lg-cap">Order: <b>conference standings</b> {DOT} right: AP rank, record</div>']
    for ck in X.conf_order:
        cf = X.confs[ck]
        mem = sorted(cf["members"], key=lambda t: (-(X.rec[t]["cw"] - X.rec[t]["cl"]), -X.rec[t]["cw"], -X.rat[t]["net"]))
        btns = []
        for tid in mem:
            t = X.teams[tid]
            btns.append(f'<button type="button" class="lg-team tm-{E(t["key"])}" data-ab="{E(t["key"])}" aria-current="false">{HC.chip(tid)}'
                        f'<span class="lg-nk">{E(t["loc"])}</span><span class="lg-pw">{("#" + str(X.ap[tid])) if tid in X.ap else ""}</span>'
                        f'<span class="lg-rc">{E(X.record(tid))}</span></button>')
        sheet.append(f'<div class="lg-div"><h3>{E(cf["short"])}</h3>{"".join(btns)}</div>')
    stamp = (f'  <details class="stamp"><summary><b>Built {E(P["built_ct"])}</b><span>{len(X.teams)} FBS teams {DOT} {X.season} season {DOT} Week {X.week}</span>'
             f'<span>{HC.HM} ratings through Week {X.model["through"]} {DOT} {X.smeta["sims"]:,} season simulations</span>'
             f'<span class="st-more">Sources</span></summary>\n    <div class="stamp-b">{provenance(X)}</div>\n  </details>\n')
    head = load_head()
    extra = {"built": P["built_ct"], "season": X.season, "games": gidx}

    def page(fr):
        payload = {"default": LAND, "landing": LAND, "meta": meta, **extra}
        if fr is not None:
            payload["frags"] = fr
        js = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
        return (f'<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                f'<title>NCAAF League Hub</title>\n{head}\n<style id="lg-theme">\n{meta[LAND]["theme"]}</style>\n'
                f'<header class="bug">\n  <div class="bug-in">\n'
                f'    <a class="lg-brand" href="#{LAND}" title="League home"><span>College football</span><b>League Hub</b></a>\n'
                f'    <button type="button" class="lg-pick" id="lg-pick" aria-expanded="false" aria-controls="lg-sheet" '
                f'aria-label="Choose a team or conference">{meta[LAND]["chip"]}<span class="bug-name">League</span>'
                f'<span class="car" aria-hidden="true"></span></button>\n'
                f'    <span class="lg-st" id="lg-st">{E(meta[LAND]["status"])}</span>\n'
                f'    <a class="lg-wk" href="#W{X.week}">Week {X.week} slate</a>\n'
                + (f'    <a class="lg-wk lg-hs" href="#{E(HC.HOUSE["key"])}" title="House team">{HC.chip(HC.HOUSE["id"])}{E(X.loc(HC.HOUSE["id"]))}</a>\n'
                   if HC.HOUSE["id"] else "") +
                f'    <nav class="bug-nav" id="lg-nav" aria-label="Sections"></nav>\n'
                f'  </div>\n' + LSH.TRAIL_HTML +
                f'  <div class="lg-sheet" id="lg-sheet" hidden><div class="lg-sheet-in ncaaf">{"".join(sheet)}</div></div>\n'
                f'</header>\n<main class="wrap" id="top">\n{stamp}  <div id="club" aria-live="polite"></div>\n'
                f'  <footer>NCAAF League Hub {DOT} the league home, all {len(X.teams)} FBS teams, every conference, every week of the '
                f'schedule and a page for each game of this week and last — rebuilt from ESPN’s college-football feeds (scores, kickoffs, TV, '
                f'venues, standings, the AP and Coaches polls and the CFP ranking, team statistics, DraftKings lines and closing lines), '
                f'Kalshi’s public market data and the house model on every refresh. Circles are percentile ranks among FBS teams on the '
                f'locked scale (red is better). HOUSE MODEL numbers and market numbers are labeled and never blended. Nothing on this page is '
                f'authored.</footer>\n</main>\n<script type="application/json" id="lg-data">{js}</script>\n{LSH.FIT_JS}{LSH.LEAGUE_JS}')
    os.makedirs(out_dir, exist_ok=True)
    rels = []
    for k, v in views.items():
        rel = meta[k]["file"]
        os.makedirs(os.path.join(out_dir, os.path.dirname(rel)), exist_ok=True)
        with open(os.path.join(out_dir, rel), "w", encoding="utf-8") as f:
            json.dump(v, f, separators=(",", ":"), ensure_ascii=False)
        rels.append(rel)
        _structure_check(v["html"], f"view {k}")
    os.makedirs(os.path.join(out_dir, "games"), exist_ok=True)
    for b, bun in gb.items():
        rel = f"games/{b}.json"
        with open(os.path.join(out_dir, rel), "w", encoding="utf-8") as f:
            json.dump(bun, f, separators=(",", ":"), ensure_ascii=False)
        rels.append(rel)
    for eid, h_ in gqa:
        _structure_check(h_, f"game {eid}")
    shell = page(None)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(shell)
    full = page({k: v for k, v in views.items()})
    with open(os.path.join(out_dir, "league-hub-full.html"), "w", encoding="utf-8") as f:
        f.write(full)
    if gqa:
        allg = "".join(f'<section class="gm-qa" id="qaG{eid}">{h_}</section>\n' for eid, h_ in gqa)
        with open(os.path.join(out_dir, "games-qa.html"), "w", encoding="utf-8") as f:
            f.write(f'<meta charset="utf-8">\n<title>NCAAF League Hub — game pages (QA)</title>\n{head}\n<style id="lg-theme">\n'
                    f'{meta[LAND]["theme"]}</style>\n<main class="wrap">\n{stamp}{allg}</main>\n')
    pub = {"file_path": os.path.abspath(os.path.join(out_dir, "index.html")), "root": os.path.abspath(out_dir),
           "files": {r: r for r in sorted(rels)}}
    with open(os.path.join(out_dir, "publish-files.json"), "w", encoding="utf-8") as f:
        json.dump(pub, f, indent=1)
    return shell, rels, X


def provenance(X):
    P = X.P
    m = X.model
    test = m.get("test_all") or {}
    cal = m.get("calibration") or {}
    bx = m.get("boxes") or {}
    v11 = m.get("v11") or {}
    v1t = (((v11.get("compare") or {}).get("test") or {}).get("v1") or {}).get("mae_house")
    lo = (v11.get("loso") or {}).get("summary") or {}
    km = X.kmeta
    if X.kal_ok:
        kal_txt = (f'Public Trade API, read {E(km.get("read_utc") or "")}: {km.get("priced", 0)} games priced ({km.get("pre", 0)} at the '
                   f'pre-kickoff hour, never in-play), futures for the title, the playoff and every conference champion')
    else:
        kal_txt = f"not read this build ({E(X.kal_why)})"
    return (f'<b>Data.</b> ESPN college-football feeds (site and core APIs): {P["counts"]["events"]} FBS events this season, '
            f'{P["counts"]["finals"]} finals, closing lines on {P["counts"]["closing"]} (DraftKings first, ESPN BET otherwise; core odds endpoint), '
            f'DraftKings lines for upcoming games (scoreboard), conference membership and standings (computed from the games; ESPN '
            f'{"agrees on every record" if not P.get("espn_mismatch") else "differs on " + str(len(P["espn_mismatch"])) + " records"}), the AP / Coaches polls'
            f'{" and the CFP ranking" if X.cfp else ""}, ESPN team statistics, game summaries. {E(P.get("fetch") or "")}.<br>'
            f'<b>{HC.HM}.</b> ncaaf-sim {E(m.get("version") or "v1")}: offense/defense ridge ratings from this season’s finals (prior: last '
            f'season regressed toward the current conference'
            + (f', moved toward the preseason AP poll of {E((m.get("poll") or "")[:10])}' if m.get("poll") and m.get("version") == "v1.1" else "")
            + ')'
            + (f', stacked with opponent-adjusted run, pass and turnover efficiency from {bx.get("with_boxes", 0)} of {bx.get("fbs_finals", 0)} '
               f'FBS v FBS finals’ team boxes{" (Weeks 1–4 weights)" if m.get("early") else ""}' if m.get("version") == "v1.1" and bx else "")
            + f', home edge {C_fmt(m["hfa"])} points, win chance from a normal margin (sigma {C_fmt(m["sigma"])}, '
            f'{C_fmt(m.get("sigma_early"))} in Weeks 1–4). Calibrated on {E("–".join(map(str, cal.get("train_seasons") or [])))}, held out '
            f'{E("–".join(map(str, cal.get("test_seasons") or [])))}: margin error {C_fmt(test.get("mae_house"), 2)}'
            + (f' (v1 {C_fmt(v1t, 2)})' if v1t is not None else "")
            + f' vs the closing line’s {C_fmt(test.get("mae_market"), 2)}; Brier {C_fmt(test.get("brier_house"), 4)} vs '
            f'{C_fmt(test.get("brier_market"), 4)}'
            + (f'; left out one season at a time (2016–2025) v1.1 beats v1 in {lo["seasons_better"]} of {lo["seasons"]}' if lo else "")
            + f' — the closing market is the better forecaster and the house numbers are advisory. Season simulation: {X.smeta["sims"]:,} seasons, seed '
            f'{X.smeta["seed"]}; conference title games by conference record with head-to-head, a committee proxy fitted to the committee’s '
            f'final rankings 2014–2025, the 2026 bid rules.<br>'
            f'<b>Kalshi.</b> {kal_txt}. '
            f'A second market beside DraftKings: never averaged with it, never blended with the house.<br>'
            f'<b>Not on these pages.</b> Player pages (teams only, by design), live in-game scores (not built yet), injuries.')


def C_fmt(x, nd=1):
    return HC.fmt(x, nd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("league")
    s.add_argument("--pull", required=True)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--house", default=HOUSE_KEY, help="house team key (default WIS); '' for none")
    a = ap.parse_args()
    P = json.load(open(a.pull, encoding="utf-8"))
    shell, rels, X = build_league(P, a.out_dir, a.house)
    tot = os.path.getsize(os.path.join(a.out_dir, "index.html")) + sum(os.path.getsize(os.path.join(a.out_dir, r)) for r in rels)
    print(f"[hub_build league] {len(rels)} data files + shell · {tot / 1e6:.1f} MB to publish · teams {len(X.teams)} · "
          f"game pages {len(X.game_pages)}", file=sys.stderr)
    if tot > 58e6:
        warn(f"publish size {tot / 1e6:.1f} MB is past 58 MB (the publish limit is 64 MB a call)")
    for w in WARN:
        print("WARN", w, file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
