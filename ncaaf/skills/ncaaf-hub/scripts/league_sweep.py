#!/usr/bin/env python3
"""league_sweep.py — the NCAAF League Hub's render gate (Playwright over local HTTP), the NFL / EPL league_sweep's contract.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 league_sweep.py OUT [--dark] [--teams all|N] [--games N] [--widths 390,834,1180]

Lint (no browser): every fragment's tags balance; no placeholder or Python leak text (None, nan, undefined, {…}); every in-page
link (#KEY, #C-…, #W…, #G…) resolves to a view or a game page of this build; the league home carries every section; each
team page carries its sections; publish-files.json lists every fragment.
Render (Chromium): the league home, every conference and week, the teams (all by default) and a sample of game pages (finals and
previews) at each width: the view loads, no page or console error, no sideways scroll, every board fits its panel at 834 px and
up (fit-to-width), the bug's status is set and its section links resolve. Interactions at 1180 px: a rankings tab, sorting the
odds board both ways (rank cells renumber), a team link from the home (trail League › team), the picker to a conference, Back.
Exit 0 = PASS, 1 = FAIL (blocks publishing), 2 = no browser (say so; never claim a render check).
"""
import argparse
import functools
import http.server
import json
import os
import re
import socketserver
import sys
import threading
from html.parser import HTMLParser

sys.dont_write_bytecode = True
BAD_TEXT = re.compile(r"\bNone\b|\bnan\b|\bNaN\b|\bundefined\b|\{[a-z_]+\}|\binf\b")
TEAM_SECS = ["odds", "schedule", "ratings", "record", "teamstats"]
HOME_SECS = ["games", "rankings", "playoff", "odds", "confs", "power", "efficiency", "teamstats", "pulse", "calendar", "allteams"]


class Bal(HTMLParser):
    VOID = {"br", "meta", "link", "img", "hr", "input", "col", "source", "wbr", "path", "circle", "rect", "line", "polyline", "polygon",
            "ellipse", "stop", "use"}

    def __init__(self):
        super().__init__()
        self.stack, self.bad = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.bad.append(tag)


def text_of(h):
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    h = re.sub(r'(title|data-tip|aria-label)="[^"]*"', " ", h)
    return re.sub(r"<[^>]+>", " ", h)


def lint(out):
    fails, notes = [], []
    shell = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    D = json.loads(re.search(r'<script type="application/json" id="lg-data">(.*?)</script>', shell, re.S).group(1).replace("<\\/", "</"))
    meta, games = D["meta"], D.get("games") or {}
    pub = json.load(open(os.path.join(out, "publish-files.json"), encoding="utf-8"))
    frags = {}
    for k, m in meta.items():
        p = os.path.join(out, m["file"])
        if not os.path.exists(p):
            fails.append(f"view {k}: file {m['file']} missing")
            continue
        if m["file"] not in pub["files"]:
            fails.append(f"view {k}: {m['file']} not in publish-files.json")
        frags[k] = json.load(open(p, encoding="utf-8"))
    for f in sorted(os.listdir(os.path.join(out, "games"))) if os.path.isdir(os.path.join(out, "games")) else []:
        rel = f"games/{f}"
        if rel not in pub["files"]:
            fails.append(f"{rel} not in publish-files.json")
        for eid, g in json.load(open(os.path.join(out, rel), encoding="utf-8")).items():
            frags["G" + eid] = g
    for eid in games:
        if "G" + eid not in frags:
            fails.append(f"game {eid}: indexed but not in any bundle")
    keys = set(meta) | {"G" + e for e in games}
    dead = {}
    for k, f in frags.items():
        h = f["html"]
        b = Bal()
        b.feed(h)
        if b.stack or b.bad:
            fails.append(f"{k}: unbalanced tags (open {b.stack[-3:]}, stray {b.bad[:3]})")
        m = BAD_TEXT.search(text_of(h))
        if m:
            i = m.start()
            fails.append(f"{k}: leaked text {m.group(0)!r} near …{text_of(h)[max(0, i - 60):i + 30]!r}")
        for href in re.findall(r'href="#([^"]+)"', h):
            if href not in keys and href not in {s[0] for s in f.get("nav") or []} and not re.match(r"^(wk|wP)", href) \
                    and not re.search(r'id="' + re.escape(href) + '"', h):
                dead.setdefault(href, k)
        for sid, _ in f.get("nav") or []:
            if f'id="{sid}"' not in h:
                fails.append(f"{k}: nav section {sid} has no anchor")
    for href, k in list(dead.items())[:10]:
        fails.append(f"dead link #{href} (first seen on {k})")
    home = frags.get("NCAAF", {}).get("html", "")
    for s in HOME_SECS:
        if f'id="{s}"' not in home:
            fails.append(f"league home: section {s} missing")
    nteam = 0
    for k, m in meta.items():
        if m["file"].startswith("teams/"):
            nteam += 1
            h = frags.get(k, {}).get("html", "")
            for s in TEAM_SECS:
                if f'id="{s}"' not in h:
                    fails.append(f"team {k}: section {s} missing")
    notes.append(f"lint: {len(frags)} fragments ({nteam} teams, {len(games)} game pages), dead links {len(dead)}")
    return fails, notes, D


def serve(out):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=out)

    class Q(handler.func):
        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Q, directory=out))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/index.html"


CHECK_JS = r"""(args) => {
  const [key, w] = args;
  const out = {errs: []};
  const box = document.getElementById('club');
  out.loaded = box && box.getAttribute('data-ab') === key && box.innerHTML.length > 200;
  out.sw = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  out.status = (document.getElementById('lg-st') || {}).textContent || '';
  const over = [];
  if (w >= 834) document.querySelectorAll('#club table.rb.lg').forEach(t => {
    if (t.offsetParent === null) return; const wrap = t.parentNode; if (t.scrollWidth > wrap.clientWidth + 2) over.push((t.className || '') + ' ' + t.scrollWidth + '>' + wrap.clientWidth);
  });
  out.over = over;
  const navs = [...document.querySelectorAll('#lg-nav a')].map(a => a.getAttribute('href').slice(1));
  out.badnav = navs.filter(id => !document.getElementById(id));
  return out;
}"""


def render(url, D, widths, dark, teams_n, games_n):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, ["no Python Playwright: pip install --break-system-packages playwright==<the Node package's version>"]
    meta = D["meta"]
    team_keys = [k for k, m in meta.items() if m["file"].startswith("teams/")]
    if teams_n != "all":
        n = int(teams_n)
        team_keys = team_keys[:: max(1, len(team_keys) // max(1, n))][:n]
    other = [k for k, m in meta.items() if not m["file"].startswith("teams/")]
    gk = list(D.get("games") or {})
    fin = [g for g in gk if "–" in D["games"][g][0]][: games_n // 2 + 1]
    pre = [g for g in gk if "–" not in D["games"][g][0]][: games_n // 2 + 1]
    views = other + team_keys + ["G" + g for g in fin + pre]
    fails, n = [], 0
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for w in widths:
                ctx = br.new_context(viewport={"width": w, "height": 900}, color_scheme="dark" if dark else "light")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                page.goto(url + "#NCAAF", wait_until="networkidle")
                for k in views:
                    page.evaluate("k => window.ncaafHub.show(k, 'pick')", k)
                    try:
                        page.wait_for_function("k => { const b = document.getElementById('club'); return b && b.getAttribute('data-ab') === k && b.innerHTML.length > 200; }",
                                               arg=k, timeout=8000)
                    except Exception:  # noqa: BLE001
                        fails.append(f"{k} @{w}: did not load")
                        continue
                    page.wait_for_timeout(30)
                    r = page.evaluate(CHECK_JS, [k, w])
                    n += 1
                    if r["sw"] > 1:
                        fails.append(f"{k} @{w}: sideways scroll {r['sw']}px")
                    if r["over"]:
                        fails.append(f"{k} @{w}: board wider than its panel: {r['over'][:2]}")
                    if not r["status"].strip():
                        fails.append(f"{k} @{w}: empty status")
                    if r["badnav"]:
                        fails.append(f"{k} @{w}: section links without anchors {r['badnav'][:3]}")
                    if errs:
                        fails.append(f"{k} @{w}: script errors {errs[:2]}")
                        errs.clear()
                ctx.close()
            # interactions at 1180
            ctx = br.new_context(viewport={"width": 1180, "height": 900}, color_scheme="dark" if dark else "light")
            page = ctx.new_page()
            page.goto(url + "#NCAAF", wait_until="networkidle")
            page.wait_for_selector("#rankings")
            page.click('#rankings [data-tab="rk-hm"]')
            if page.is_hidden("#rk-hm"):
                fails.append("interaction: the rankings tab did not switch panes")
            btn = page.locator('#odds table.lp-odds button.srt', has_text="Title").first
            btn.click()
            first_desc = page.evaluate("() => [...document.querySelectorAll('#odds table.lp-odds tbody tr')].slice(0,3).map(r => r.querySelector('.rkc').textContent)")
            btn.click()
            vals = page.evaluate("() => [...document.querySelectorAll('#odds table.lp-odds tbody tr')].map(r => r.cells[[...r.parentNode.parentNode.tHead.rows[1].cells].findIndex(c => c.getAttribute('aria-sort'))].getAttribute('data-v'))")
            nums = [float(v) for v in vals if v not in (None, "")]
            if first_desc[:3] != ["1", "2", "3"] or nums != sorted(nums):
                fails.append(f"interaction: sorting the odds board failed ({first_desc[:3]}, ascending {nums[:3]})")
            page.locator('#power table a.tl2').first.click()
            page.wait_for_timeout(400)
            crumbs = page.evaluate("() => window.ncaafHub.trail()")
            if len(crumbs) != 2 or crumbs[0] != "League":
                fails.append(f"interaction: back trail after a team link = {crumbs}")
            page.click("#lg-back")
            page.wait_for_timeout(300)
            if page.get_attribute("#club", "data-ab") != "NCAAF" or not page.is_hidden("#lg-tr"):
                fails.append("interaction: Back did not return to the league home with the trail hidden")
            page.click("#lg-pick")
            page.click('#lg-sheet [data-ab="C-SEC"]')
            page.wait_for_timeout(400)
            if page.get_attribute("#club", "data-ab") != "C-SEC":
                fails.append("interaction: the picker did not open the SEC page")
            ctx.close()
            br.close()
    except Exception as e:  # noqa: BLE001
        if "Executable doesn't exist" in str(e) or "browserType.launch" in str(e):
            return None, [f"no browser: {e}"]
        fails.append(f"render crashed: {type(e).__name__}: {e}")
    return n, fails


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--teams", default="all")
    ap.add_argument("--games", type=int, default=12)
    ap.add_argument("--widths", default="390,834,1180")
    a = ap.parse_args()
    fails, notes, D = lint(a.out)
    for x in notes:
        print("[league_sweep]", x)
    srv, url = serve(a.out)
    n, rf = render(url, D, [int(x) for x in a.widths.split(",")], a.dark, a.teams, a.games)
    srv.shutdown()
    if n is None:
        for x in rf:
            print("[league_sweep] NOT RUN:", x)
        for x in fails:
            print("FAIL", x)
        sys.exit(1 if fails else 2)
    fails += rf
    for x in fails[:60]:
        print("FAIL", x)
    print(f"[league_sweep] {'PASS' if not fails else 'FAIL'} · {n} views rendered ({'dark' if a.dark else 'light'}) · "
          f"{len(fails)} failures")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
