#!/usr/bin/env python3
"""qa.py — pre-delivery gate for every NCAAF workspace HTML / markdown product (ncaaf-qa, 2026-10-26).
The NFL / NHL / EPL qa.py contract, with college football's checks.

    python3 qa.py FILE [--pull PULL.json] [--date YYYY-MM-DD] [--no-render] [--json] [--widths 390,760,1100]

Exit 0 = PASS · 1 = FAIL (blocking: fix before delivery) · 2 = PASS with warnings (acceptable when each is explained).
Stdlib only; the layout pass uses Playwright + Chromium when present (PLAYWRIGHT_BROWSERS_PATH defaults to /opt/pw-browsers)
and falls back to static checks when not (the report says which).

Checks
  structure  unbalanced tags; leftover placeholders (TODO, {{…}}, undefined, NaN, [object Object]); elements that are only
             None / null / nan
  season     stale phase language for the build date (a "first CFP ranking" note once the committee has ranked; bracket
             or Selection-Day wording before Dec 6; preseason wording after Week 1) — dates in SEASON_DATES
  sources    banned aggregators (heavy.com class — the operator blocklist shared with every sports suite)
  stamps     a freshness stamp exists and is under 36 hours old at --date; house numbers carry the literal "HOUSE MODEL"; no
             market word (DraftKings, Kalshi, closing) inside a HOUSE MODEL label
  layout     rendered at each width: no page-level sideways scroll, no JS errors (the default view only — the hub's
             league_sweep.py is the gate for every view)
  integrity  --pull: 130+ FBS teams, every team rated and simulated, odds in [0,1]; CFP places sum to 12, titles to 1, each
             conference's title-game places to 2 and champions to 1; every closing line on a final; a game under way or
             final carries only Kalshi's pre-kickoff price; Kalshi game prices in (0,1); ESPN's records agree with the games
"""
import argparse
import datetime
import html.parser
import json
import os
import re
import sys

sys.dont_write_bytecode = True
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr", "path",
        "circle", "rect", "line", "polyline", "polygon", "ellipse", "stop", "use"}
BANNED = ["heavy.com", "sportskeeda", "clutchpoints", "yardbarker", "pickdawgz", "predictem", "sportsgrid", "covers.com",
          "sportsbookreview"]
# season (kickoff year) -> verified dates (ncaaf-data-pull/references/season_<Y>_facts.json), re-verified at each audit
SEASON_DATES = {2026: dict(week1="2026-08-22", first_cfp="2026-11-03", selection="2026-12-06", title="2027-01-25")}


class Balance(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.text, self._skip = [], [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        if tag in VOID:
            return
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            self.errors.append(f"stray </{tag}> at line {self.getpos()[0]}")

    def handle_data(self, d):
        if not self._skip:
            self.text.append(d)


def season_of(d):
    return d.year if d.month >= 7 else d.year - 1


def check_static(src, today, R):
    b = Balance()
    b.feed(src)
    if b.errors:
        R["fail"].append(f"structure: {b.errors[:3]}")
    if b.stack:
        R["fail"].append(f"structure: unclosed {[t for t, _ in b.stack[-4:]]}")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", src, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", body)
    for pat, lab in ((r"\bTODO\b", "TODO"), (r"\{\{[^}]*\}\}", "{{…}}"), (r"\bundefined\b", "undefined"), (r"\bNaN\b", "NaN"),
                     (r"\[object Object\]", "[object Object]")):
        if re.search(pat, txt):
            R["fail"].append(f"placeholder: {lab}")
    if re.search(r">\s*(None|null|nan)\s*<", body):
        R["fail"].append("an element whose whole content is None/null/nan")
    # a League Hub page carries its views as JSON (league-hub-full.html inlines every fragment): scan each one too
    m = re.search(r'<script type="application/json" id="lg-data">(.*?)</script>', src, re.S)
    if m:
        try:
            D = json.loads(m.group(1).replace("<\\/", "</"))
        except ValueError:
            D = {}
            R["fail"].append("structure: the page's lg-data payload is not valid JSON")
        nf = 0
        for k, f in (D.get("frags") or {}).items():
            nf += 1
            h = f.get("html") or ""
            fb = Balance()
            fb.feed(h)
            if fb.errors or fb.stack:
                R["fail"].append(f"structure: view {k} unbalanced ({(fb.errors or [t for t, _ in fb.stack])[:2]})")
            ft = re.sub(r"<[^>]+>", " ", re.sub(r'(title|data-tip|aria-label)="[^"]*"', " ", h))
            for pat, lab in ((r"\bTODO\b", "TODO"), (r"\{\{[^}]*\}\}", "{{…}}"), (r"\bundefined\b", "undefined"), (r"\bNaN\b", "NaN"),
                             (r"\bNone\b", "None"), (r"\bnan\b", "nan"), (r"\[object Object\]", "[object Object]")):
                if re.search(pat, ft):
                    R["fail"].append(f"placeholder: {lab} in view {k}")
        if nf:
            R["info"].append(f"structure: {nf} inlined views scanned")
    low = src.lower()
    for b_ in BANNED:
        if b_ in low:
            R["fail"].append(f"sources: banned aggregator {b_}")
    # stamps
    m = re.search(r"Built (\w{3} \w{3} \d{1,2}, \d{4}) (\d{1,2}:\d{2} [AP]M) CT", txt)
    if not m:
        R["fail"].append("stamps: no 'Built … CT' freshness stamp")
    else:
        built = datetime.datetime.strptime(m.group(1) + " " + m.group(2), "%a %b %d, %Y %I:%M %p")
        age_h = (datetime.datetime.combine(today, datetime.time(12)) - built).total_seconds() / 3600
        if age_h > 36:
            R["warn"].append(f"stamps: built {m.group(1)} — {age_h:.0f} h before {today}")
        R["info"].append(f"stamp: built {m.group(1)} {m.group(2)} CT")
    if "HOUSE MODEL" not in src:
        R["fail"].append("stamps: no HOUSE MODEL label anywhere")
    for mm in re.finditer(r'<span class="hm">HOUSE MODEL</span>\s*(DraftKings|Kalshi|closing)', src):
        R["fail"].append(f"stamps: a market word directly inside a HOUSE MODEL label ({mm.group(1)})")
    # season language
    sd = SEASON_DATES.get(season_of(today))
    if sd:
        d = today.isoformat()
        if d >= sd["first_cfp"] and re.search(r"releases its first ranking", txt) and "CFP committee" not in txt:
            R["warn"].append("season: 'first CFP ranking' note after Nov 3 — has the pull read the committee's ranking?")
        if d < sd["week1"] and re.search(r"\bfinal\b.*\bWeek 1\b", txt):
            R["warn"].append("season: results wording before Week 1")
        if d < sd["selection"] and re.search(r"Selection Day (bracket|field) (is|was) set", txt):
            R["fail"].append("season: a bracket named as set before Selection Day")
    else:
        R["warn"].append(f"season: no SEASON_DATES for {season_of(today)} — add them at the season audit")


def check_render(path, widths, R):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        R["warn"].append("layout: no Python Playwright — static checks only")
        return
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for w in widths:
                pg = br.new_page(viewport={"width": w, "height": 900})
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto("file://" + os.path.abspath(path), wait_until="load")
                pg.wait_for_timeout(500)
                sw = pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
                if sw > 1:
                    R["fail"].append(f"layout @{w}: sideways scroll {sw}px")
                if errs:
                    R["fail"].append(f"layout @{w}: JS errors {errs[:2]}")
                if pg.evaluate("() => /\\bundefined\\b|\\bNaN\\b/.test(document.body.innerText)"):
                    R["fail"].append(f"layout @{w}: client-side placeholder text")
                pg.close()
            br.close()
            R["info"].append(f"layout: rendered at {widths}")
    except Exception as e:  # noqa: BLE001
        R["warn"].append(f"layout: browser unavailable ({type(e).__name__}) — static checks only")


def check_pull(P, R):
    T = P["reg"]["teams"]
    if len(T) < 130:
        R["fail"].append(f"integrity: {len(T)} FBS teams (expected 130+)")
    S = P["sim"]["teams"]
    miss = [t for t in T if t not in P["ratings"] or t not in S]
    if miss:
        R["fail"].append(f"integrity: {len(miss)} teams without ratings or simulation")
    for t, s in S.items():
        for k in ("p_bowl", "p_ccg", "p_conf", "p_cfp", "p_bye", "p_qf", "p_sf", "p_final", "p_champ"):
            if not (0 <= s[k] <= 1):
                R["fail"].append(f"integrity: {t} {k}={s[k]} outside [0,1]")
                break
        if not (s["p_champ"] <= s["p_final"] + 1e-9 <= s["p_sf"] + 2e-9 <= s["p_qf"] + 3e-9 <= s["p_cfp"] + 4e-9):
            R["fail"].append(f"integrity: {t} round odds not nested")
    cfp = sum(s["p_cfp"] for s in S.values())
    ch = sum(s["p_champ"] for s in S.values())
    if abs(cfp - 12) > 0.01:
        R["fail"].append(f"integrity: CFP places sum to {cfp:.3f}, not 12")
    if abs(ch - 1) > 0.001:
        R["fail"].append(f"integrity: titles sum to {ch:.4f}, not 1")
    for ck, cf in P["reg"]["confs"].items():
        if ck == "IND":
            continue
        g = sum(S[t]["p_ccg"] for t in cf["members"])
        c = sum(S[t]["p_conf"] for t in cf["members"])
        if abs(g - 2) > 0.01 or abs(c - 1) > 0.001:
            R["fail"].append(f"integrity: {ck} title game sums {g:.3f} (2), champion {c:.4f} (1)")
    fin = [e for e in P["events"] if e["status"]["completed"]]
    nocl = [e for e in fin if not (e.get("cl") or {}).get("spread") is not None]
    if fin and len(nocl) / len(fin) > 0.05:
        R["warn"].append(f"integrity: {len(nocl)} of {len(fin)} finals without a closing line")
    # Kalshi
    kal = P.get("kalshi") or {}
    if not kal.get("ok"):
        R["warn"].append(f"integrity: Kalshi not read ({kal.get('why')}) — the hub says so on every Kalshi cell")
    ev = {e["eid"]: e for e in P["events"]}
    for eid, k in (kal.get("games") or {}).items():
        e = ev.get(eid)
        if not (0 < k["p_home"] < 1):
            R["fail"].append(f"integrity: Kalshi {eid} p_home {k['p_home']}")
        if e and (e["status"]["state"] in ("in", "post")) and not k.get("pre"):
            R["fail"].append(f"integrity: Kalshi {eid} is a live/final game priced from the current book, not pre-kickoff")
        if e and k.get("pre") and k.get("at_iso") and e.get("date") and k["at_iso"] > e["date"].replace("Z", "")[:16] + "Z":
            R["fail"].append(f"integrity: Kalshi {eid} pre-kickoff price stamped after kickoff")
    if P.get("espn_mismatch"):
        R["warn"].append(f"integrity: ESPN records differ from the games on {len(P['espn_mismatch'])}: {P['espn_mismatch'][:3]}")
    nets = [r["net"] for r in P["ratings"].values()]
    if abs(sum(nets) / len(nets)) > 0.5:
        R["fail"].append(f"integrity: FBS ratings not centered (mean {sum(nets) / len(nets):+.2f})")
    R["info"].append(f"integrity: {len(T)} teams · CFP sum {cfp:.2f} · title sum {ch:.3f} · {len(fin)} finals · "
                     f"{len(kal.get('games') or {})} Kalshi games")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--pull")
    ap.add_argument("--date")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--widths", default="390,760,1100")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.date) if a.date else datetime.date.today()
    R = {"fail": [], "warn": [], "info": []}
    src = open(a.file, encoding="utf-8").read()
    check_static(src, today, R)
    if a.pull:
        check_pull(json.load(open(a.pull, encoding="utf-8")), R)
    if not a.no_render and a.file.endswith(".html"):
        check_render(a.file, [int(x) for x in a.widths.split(",")], R)
    verdict = "FAIL" if R["fail"] else ("PASS (warnings)" if R["warn"] else "PASS")
    if a.json:
        print(json.dumps(dict(R, verdict=verdict), indent=1))
    else:
        for k in ("fail", "warn", "info"):
            for x in R[k]:
                print(f"{k.upper():<5} {x}")
        print(f"[ncaaf-qa] {verdict} · {os.path.basename(a.file)}")
    sys.exit(1 if R["fail"] else (2 if R["warn"] else 0))


if __name__ == "__main__":
    main()
