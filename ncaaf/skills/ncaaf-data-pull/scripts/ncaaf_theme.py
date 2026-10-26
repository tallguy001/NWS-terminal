#!/usr/bin/env python3
"""ncaaf_theme — team colors and the page themes built from them (stdlib only).

The college port of nfl-hub/nfl_theme.py (itself nba_theme): same API, same token names, same contrast rules, so the NCAAF
League Hub carries proper team colors exactly the way the NFL, NBA, NHL and EPL hubs do (owner directive 2026-10-14:
"Artifacts should use proper team colors").

PALETTE: each FBS team's primary and alternate color as ESPN's feeds publish them (team `color` / `alternateColor`,
captured in ncaaf-data-pull/references/teams_<Y>.json by `ncaaf_data.py registry --write`; the build can pass the live
registry through `load()`). 138 teams cannot be hand-curated the way 32 NFL clubs were, so the STYLE is derived by rule:
  chrome = the primary, unless the primary is a light gold/tan (luminance > 0.33) and the alternate is dark — then the dark
           color is the chrome and the gold the accent (Purdue, Colorado, Wake Forest, Missouri, Vanderbilt read black-and-gold);
  accent = the other color (white when the alternate is white or too close to the chrome);
  third  = white or black, whichever reads on the chrome.
FIX overrides the rule where ESPN's pair misses a signature color (Georgia Tech navy and gold). Everything a reader reads is
derived for contrast (WCAG AA >= 4.5:1), never hand-set. The league theme NCAAF (navy and old gold) is a house design choice.

    import ncaaf_theme as TH
    TH.load(registry["teams"])   # optional: today's registry (else the packaged snapshot)
    TH.theme_css("WIS")          # :root day + both night blocks
    TH.chip("OSU")               # {"bg","fg","edge","ring"}
    TH.chips_css()               # .tm-KEY classes for every team (+ NCAAF)
    TH.mark("MICH")              # chart mark colors that clear 3:1 on light and dark surfaces
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.normpath(os.path.join(HERE, "..", "references"))
WHITE, BLACK = "#FFFFFF", "#000000"
LEAGUE = "NCAAF"
LEAGUE_STYLE = ("#0F2341", "#C99700", "#FFFFFF")      # house: broadcast navy + old gold
FIX = {"GT": ("#003057", "#B3A369", "#FFFFFF")}       # Georgia Tech navy + Tech Gold (ESPN lists gold + white)
SOURCE = ("Team colors as ESPN's college-football feeds publish them (team color and alternate color), captured in the "
          "registry snapshot; chrome / accent chosen by rule for contrast; Georgia Tech's navy added by hand.")

PALETTE = {}     # KEY -> (primary, alternate)
NAMES = {}       # KEY -> abbreviation shown on the chip
STYLE = {}       # KEY -> (chrome, accent, third)


# ------------------------------------------------------------------ color math (nfl_theme, verbatim)
def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hexc(c):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v))) for v in c)


def lum(h):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a, b, t):
    ra, rb = rgb(a), rgb(b)
    return hexc(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def toward(c, target, ok, steps=40):
    for i in range(steps + 1):
        x = mix(c, target, i / steps)
        if ok(x):
            return x
    return target


def toward_t(c, target, ok, steps=40):
    for i in range(steps + 1):
        x = mix(c, target, i / steps)
        if ok(x):
            return x, i / steps
    return target, 1.0


def rgba(h, a):
    r, g, b = rgb(h)
    return f"rgba({r},{g},{b},{a})"


def sat(h):
    r, g, b = (v / 255 for v in rgb(h))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0 if mx == 0 else (mx - mn) / mx


def _norm(h, dflt):
    h = (h or "").strip().lstrip("#")
    if len(h) != 6:
        return dflt
    try:
        int(h, 16)
    except ValueError:
        return dflt
    return "#" + h.upper()


# ------------------------------------------------------------------ palette -> style
def _style(key, prim, alt):
    if key in FIX:
        return FIX[key]
    p, a = _norm(prim, "#555555"), _norm(alt, WHITE)
    if lum(p) > 0.33 and lum(a) < 0.09:            # light gold primary, dark alternate: dark chrome, gold accent
        p, a = a, p
    accent = a if contrast(a, p) >= 1.3 else (WHITE if contrast(WHITE, p) >= contrast(BLACK, p) else BLACK)
    third = WHITE if contrast(WHITE, p) >= contrast(BLACK, p) else BLACK
    if third == accent:
        third = BLACK if accent == WHITE else WHITE
    return (p, accent, third)


def load(teams=None):
    """teams: {id: {key, abbr, color, alt}} (the registry); None = the newest packaged snapshot."""
    if teams is None:
        snaps = sorted(glob.glob(os.path.join(REFS, "teams_*.json")))
        teams = {}
        if snaps:
            with open(snaps[-1], encoding="utf-8") as f:
                teams = json.load(f).get("teams") or {}
    PALETTE.clear()
    NAMES.clear()
    STYLE.clear()
    for t in teams.values():
        k = t.get("key")
        if not k:
            continue
        PALETTE[k] = (_norm(t.get("color"), "#555555"), _norm(t.get("alt"), WHITE))
        NAMES[k] = t.get("abbr") or k
        STYLE[k] = _style(k, t.get("color"), t.get("alt"))
    STYLE[LEAGUE] = LEAGUE_STYLE
    NAMES[LEAGUE] = LEAGUE
    PALETTE[LEAGUE] = LEAGUE_STYLE[:2]
    return len(STYLE) - 1


# ------------------------------------------------------------------ tokens (identical rules to nfl_theme)
def tokens(tri):
    tri = tri if tri in STYLE else LEAGUE
    chrome, accent, third = STYLE[tri]
    dark_chrome = lum(chrome) < 0.012
    if lum(chrome) < 0.03:
        ch2, ch3 = mix(chrome, WHITE, 0.08), mix(chrome, WHITE, 0.16)
    else:
        ch2, ch3 = mix(chrome, BLACK, 0.14), mix(chrome, BLACK, 0.28)
    c_ink = WHITE if contrast(WHITE, chrome) >= 4.5 else ("#111111" if contrast("#111111", chrome) >= 4.6 else BLACK)
    c_ink2 = toward(mix(c_ink, chrome, 0.30), c_ink, lambda x: contrast(x, chrome) >= 4.6 and contrast(x, ch2) >= 4.5)
    c_ink3 = toward(mix(c_ink, chrome, 0.45), c_ink, lambda x: contrast(x, chrome) >= 3.2)
    on_gold = max((c_ink, chrome, "#111111", WHITE), key=lambda x: contrast(x, accent))
    bg = mix("#EDEDED", chrome, 0.05); sf = WHITE; sf2 = mix("#F6F6F6", chrome, 0.03)
    ln = mix("#DCDCDC", chrome, 0.06); ln2 = mix("#B3B3B3", chrome, 0.08); bg2 = mix("#E2E2E2", chrome, 0.06)
    ink = mix("#141414", chrome, 0.12); ink2 = mix("#3D3D3D", chrome, 0.10)
    ink3 = toward(mix("#6A6A6A", chrome, 0.08), "#000000", lambda x: contrast(x, bg) >= 4.6)
    nbg = mix("#09090A", chrome, 0.10); nsf = mix("#131315", chrome, 0.10); nsf2 = mix("#19191C", chrome, 0.12)
    nln = mix("#29292D", chrome, 0.16); nln2 = mix("#45454A", chrome, 0.20); nbg2 = mix("#0E0E10", chrome, 0.08)
    nink, nink2 = "#F2F2F2", "#C8C8C8"
    nink3 = toward("#8F8F8F", WHITE, lambda x: contrast(x, nsf2) >= 4.6)
    if dark_chrome:
        nch, nch2, nch3 = mix(chrome, WHITE, 0.10), mix(chrome, WHITE, 0.16), mix(chrome, WHITE, 0.24)
    else:
        nch, nch2, nch3 = chrome, ch2, ch3

    def light_ok(x):
        return contrast(x, WHITE) >= 4.5 and contrast(x, bg) >= 4.5 and contrast(x, sf2) >= 4.5
    base_l = chrome if sat(chrome) > 0.15 else (accent if accent not in (WHITE,) else (third if third not in (WHITE, BLACK) else "#6F7271"))
    acc_l = base_l if light_ok(base_l) else toward(base_l, BLACK, light_ok)

    def dark_ok(x):
        return contrast(x, nbg) >= 4.5 and contrast(x, nsf) >= 4.5 and contrast(x, nsf2) >= 4.5
    cands = [c for c in (accent, chrome if sat(chrome) > 0.15 else None, third) if c and c != BLACK] or [WHITE]
    tried = [toward_t(c, WHITE, dark_ok) for c in cands]
    acc_d = next((x for x, t in tried if t <= 0.40), min(tried, key=lambda z: z[1])[0])

    def chrome_ok(x):
        return contrast(x, chrome) >= 4.5 and contrast(x, ch2) >= 4.5
    base_c = accent if accent != BLACK else c_ink
    acc_c, t_c = toward_t(base_c, c_ink, chrome_ok)
    if t_c > 0.25:
        acc_c = c_ink
    sky_d = third if (third != BLACK and contrast(third, nbg) >= 3.0) else toward(third if third != BLACK else accent, WHITE, lambda x: contrast(x, nbg) >= 3.0)
    sky_l = third if contrast(third, WHITE) >= 3.0 and third != WHITE else (chrome if contrast(chrome, WHITE) >= 3 else BLACK)
    gold_l = accent if (contrast(accent, WHITE) >= 1.4 and contrast(accent, bg) >= 1.25) else chrome
    gold_n = accent if contrast(accent, nsf) >= 1.6 else (nch if contrast(nch, nsf) >= 1.6 else third)
    day = {
        "gold": accent, "gold-l": gold_l, "gold-deep": mix(accent, BLACK, 0.25), "sky": sky_l, "on-gold": on_gold,
        "acc-l": acc_l, "acc-d": acc_d, "acc-c": acc_c,
        "navy": chrome, "navy2": ch2, "navy3": ch3,
        "c-ink": c_ink, "c-ink2": c_ink2, "c-ink3": c_ink3, "c-ln": rgba(c_ink, 0.16),
        "bg": bg, "sf": sf, "sf2": sf2, "ln": ln, "ln2": ln2, "ink": ink, "ink2": ink2, "ink3": ink3,
        "acc": "var(--acc-l)", "tab": chrome, "bg2": bg2,
        "row-us": rgba(acc_l, 0.10), "shadow": "0 14px 30px -22px " + rgba(mix(chrome, BLACK, 0.5), 0.45),
        "chrome-edge": accent if contrast(accent, chrome) >= 1.3 else third,
    }
    night = {
        "gold-l": gold_n,
        "navy": nch, "navy2": nch2, "navy3": nch3, "sky": sky_d,
        "bg": nbg, "sf": nsf, "sf2": nsf2, "ln": nln, "ln2": nln2, "ink": nink, "ink2": nink2, "ink3": nink3,
        "acc": "var(--acc-d)", "tab": nch2 if dark_chrome else nch, "bg2": nbg2,
        "row-us": rgba(acc_d, 0.08), "shadow": "0 20px 40px -26px rgba(0,0,0,.9)",
    }
    return {"tri": tri, "chrome": chrome, "accent": accent, "third": third, "day": day, "night": night}


def _block(d):
    return "".join(f"--{k}:{v};" for k, v in d.items())


def theme_css(tri):
    """CSS overriding the template's tokens; inject AFTER the template's token blocks (same selectors, later wins)."""
    T = tokens(tri)
    nb = _block(T["night"])
    return (f":root{{{_block(T['day'])}}}\n"
            f"@media (prefers-color-scheme:dark){{:root:not([data-theme=\"light\"]){{{nb}}}}}\n"
            f":root[data-theme=\"dark\"]{{{nb}}}\n")


_CHIP = {}


def chip(tri):
    tri = tri if tri in STYLE else LEAGUE
    if tri in _CHIP:
        return _CHIP[tri]
    chrome, accent, third = STYLE[tri]
    fg = tokens(tri)["day"]["acc-c"]
    if contrast(fg, chrome) < 4.5:
        fg = tokens(tri)["day"]["c-ink"]
    edge = accent if contrast(accent, chrome) >= 1.3 else third
    ring = "rgba(255,255,255,.28)" if lum(chrome) < 0.012 else "transparent"
    _CHIP[tri] = {"bg": chrome, "fg": fg, "edge": edge, "ring": ring}
    return _CHIP[tri]


def chips_css(prefix="tm-"):
    out = []
    for t in STYLE:
        c = chip(t)
        out.append(f".{prefix}{t}{{--tm-bg:{c['bg']};--tm-fg:{c['fg']};--tm-edge:{c['edge']};--tm-ring:{c['ring']}}}")
    return "\n".join(out)


def mark(tri):
    """(primary, alternate) chart marks moved in lightness (hue kept) until each clears 3:1 on white and on the night surface."""
    tri = tri if tri in STYLE else LEAGUE
    out = []
    for c in STYLE[tri][:2]:
        def ok(x):
            return contrast(x, WHITE) >= 3.0 and contrast(x, "#161618") >= 3.0
        if ok(c):
            out.append(c)
        elif lum(c) > 0.2:
            out.append(toward(c, BLACK, ok))
        else:
            out.append(toward(c, WHITE, ok))
    return tuple(out)


def _selfcheck():
    bad = []
    for t in STYLE:
        T = tokens(t)
        d, n = T["day"], T["night"]
        checks = [("c-ink on chrome", contrast(d["c-ink"], d["navy"]), 4.5),
                  ("c-ink2 on chrome", contrast(d["c-ink2"], d["navy"]), 4.5),
                  ("acc-l on white", contrast(d["acc-l"], WHITE), 4.5),
                  ("acc-c on chrome", contrast(d["acc-c"], d["navy"]), 4.5),
                  ("acc-l on bg", contrast(d["acc-l"], d["bg"]), 4.5),
                  ("acc-d on night sf", contrast(d["acc-d"], n["sf"]), 4.5),
                  ("ink3 on bg", contrast(d["ink3"], d["bg"]), 4.5),
                  ("night ink3 on sf2", contrast(n["ink3"], n["sf2"]), 4.5)]
        ch = chip(t)
        checks.append(("chip text", contrast(ch["fg"], ch["bg"]), 4.5))
        for m in mark(t):
            checks.append(("mark on white", contrast(m, WHITE), 3.0))
        for name, v, lim in checks:
            if v < lim - 1e-6:
                bad.append(f"{t}: {name} {v:.2f} < {lim}")
    return bad


load()

if __name__ == "__main__":
    import sys
    bad = _selfcheck()
    for b in bad:
        print("FAIL", b)
    print(f"[ncaaf_theme] {len(STYLE)} themes ({len(STYLE) - 1} teams + league) · "
          f"{'PASS' if not bad else str(len(bad)) + ' contrast failures'}")
    sys.exit(1 if bad else 0)
