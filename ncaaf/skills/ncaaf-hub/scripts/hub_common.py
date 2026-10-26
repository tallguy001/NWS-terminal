#!/usr/bin/env python3
"""hub_common — shared plumbing for ncaaf-hub: sibling-skill resolution, formatting re-exports, the percentile scale, board
helpers (rb_table with the fit-to-width contract, sections, panels), chips and theme CSS. Python 3.11 safe."""
import glob
import html
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def skill_dir(skill):
    cand = os.path.join(os.path.dirname(os.path.dirname(HERE)), skill, "scripts")
    if os.path.isdir(cand):
        return cand
    for g in (f"/mnt/skills/*/{skill}/scripts", os.path.expanduser(f"~/.claude/skills/synced/*/{skill}/scripts")):
        hits = sorted(glob.glob(g))
        if hits:
            return hits[0]
    return None


def need(skill):
    d = skill_dir(skill)
    if not d:
        sys.exit(f"[ncaaf-hub] sibling skill {skill} not installed (required)")
    if d not in sys.path:
        sys.path.insert(0, d)
    return d


need("ncaaf-data-pull")
import ncaaf_common as C  # noqa: E402
import ncaaf_theme as TH  # noqa: E402

E = html.escape
MINUS, EN, DASH, DOT = C.MINUS, C.EN, C.DASH, C.DOT
fmt, signed, pct1, pct0, ordn, rec, half_up = C.fmt, C.signed, C.pct1, C.pct0, C.ordn, C.rec, C.half_up
LAND = "NCAAF"
HM = '<span class="hm">HOUSE MODEL</span>'
KX = '<span class="mk">Kalshi</span>'


def pct_int(p):
    return int(half_up(p, 0))


# ============================================================================ the locked percentile scale (the hubs' Savant scale)
SAV_DOM = (5, 45, 55, 95)
SAV_RNG = ((0x36, 0x61, 0xAD), (0xB4, 0xCF, 0xD1), (0xB4, 0xCF, 0xD1), (0xD8, 0x21, 0x29))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def sav_color(p):
    p = max(SAV_DOM[0], min(SAV_DOM[-1], float(p)))
    for i in range(3):
        a, b = SAV_DOM[i], SAV_DOM[i + 1]
        if p <= b:
            t = (p - a) / (b - a) if b > a else 0
            return _hex(tuple(SAV_RNG[i][k] + (SAV_RNG[i + 1][k] - SAV_RNG[i][k]) * t for k in range(3)))
    return _hex(SAV_RNG[-1])


def ink(p):
    return "#111111" if 28 <= float(p) <= 72 else "#ffffff"


def pct_word(p):
    return DASH if p is None else f"{ordn(pct_int(p))} percentile"


def pc(p, title=None, neutral=False, big=False):
    cls = "pcb" if big else "pc"
    if p is None:
        return f'<span class="{cls} na" aria-label="no percentile">{DASH if big else "·"}</span>'
    tt = title or pct_word(p)
    if neutral:
        return f'<span class="{cls} neu" title="{E(tt)}" aria-label="{E(tt)}">{pct_int(p)}</span>'
    return (f'<span class="{cls}" style="background:{sav_color(p)};color:{ink(p)}" title="{E(tt)}" '
            f'aria-label="{E(tt)}">{pct_int(p)}</span>')


def pbar(label, val, p, sub, neutral=False):
    if p is None:
        tr = '<div class="pb-t none"></div>'
    else:
        w = max(2.0, min(100.0, float(p)))
        paint = "" if neutral else f";background:{sav_color(p)}"
        bub = "" if neutral else f";background:{sav_color(p)};color:{ink(p)}"
        tr = (f'<div class="pb-t" role="img" aria-label="{E(label)}: {E(pct_word(p))}"><i style="width:{w:.1f}%{paint}"></i>'
              f'<b style="left:{w:.1f}%{bub}">{pct_int(p)}</b></div>')
    return (f'<div class="pb{" neu" if neutral else ""}"><div class="pb-k">{label}</div>{tr}'
            f'<div class="pb-v"><b>{val}</b><small>{sub}</small></div></div>')


# ============================================================================ chips, links, themes
TEAMS = {}       # id -> registry row (set by the builder)
KEY2ID = {}
HOUSE = {"key": None, "id": None}      # the house team (owner, 2026-10-26: Wisconsin); set by the builder


def set_house(key):
    HOUSE["key"] = key if key in KEY2ID else None
    HOUSE["id"] = KEY2ID.get(key)
    return HOUSE["id"]


def is_house_row(item):
    """A board row that belongs to the house team: its id, a ranking entry for it, or a game it plays."""
    hid = HOUSE["id"]
    if not hid:
        return False
    if isinstance(item, str):
        return item == hid
    if isinstance(item, dict):
        return item.get("id") == hid or (item.get("h") or {}).get("id") == hid or (item.get("a") or {}).get("id") == hid
    return False


def set_registry(teams):
    TEAMS.clear()
    TEAMS.update(teams)
    KEY2ID.clear()
    KEY2ID.update({t["key"]: tid for tid, t in teams.items()})
    TH.load(teams)


def chip(tid_or_key, abbr=None):
    t = TEAMS.get(tid_or_key) or TEAMS.get(KEY2ID.get(tid_or_key, ""))
    if t is None:
        if tid_or_key == LAND:
            return f'<span class="chip tm-{LAND}"><i>{LAND}</i></span>'
        ab = (abbr or str(tid_or_key or "—"))[:5]
        return f'<span class="chip fcs" title="FCS"><i>{E(ab)}</i></span>'
    return f'<span class="chip tm-{E(t["key"])}"><i>{E(t["abbr"])}</i></span>'


def is_fbs(tid):
    return tid in TEAMS


def tlink(tid, inner=None, cls="tl"):
    t = TEAMS.get(tid)
    if not t:
        return inner if inner is not None else ""
    return f'<a class="{cls}" href="#{E(t["key"])}">{inner if inner is not None else E(t["loc"])}</a>'


def name(tid, fallback=None):
    t = TEAMS.get(tid)
    return t["loc"] if t else (fallback or "FCS opponent")


def theme_css(key):
    return TH.theme_css(key if key in TH.STYLE else LAND)


def rank_tag(r):
    return f'<span class="rkn">{r}</span>' if r else ""


# ============================================================================ boards
def sec(sid, title, note=""):
    note_s = f'<span class="sec-note">{note}</span>' if note else ""
    return (f'  <section class="sec" id="{sid}">\n    <div class="sec-h">\n'
            f'      <h2 class="sec-t">{title}</h2>\n      {note_s}\n    </div>\n')


def rb_table(cols, rows, max_level, cls="", sort_default=None, house=True):
    """One board with the fit-to-width contract (data-d drop levels) and click-to-sort headers (button.srt + data-v cells).
    cols: dicts g (group), gs (group short), h (header html), f (cell fn), c (class), d (drop level), t (title),
    sk (sort key fn -> number or None), asc (sort ascending first), a (extra attrs fn), cf (cell class fn)."""
    gi, prev, k = [], object(), -1
    for c in cols:
        if c["g"] != prev:
            k += 1
            prev = c["g"]
        gi.append(k)
    top, i = [], 0
    while i < len(cols):
        j = i
        while j + 1 < len(cols) and cols[j + 1]["g"] == cols[i]["g"]:
            j += 1
        full_, short_ = cols[i]["g"], cols[i].get("gs", "")
        lab = short_ if (j - i < 2 and short_) else full_
        top.append(f'<th class="gh{" gx" if i else ""}" colspan="{j - i + 1}" data-gi="{gi[i]}" '
                   f'data-full="{E(full_)}" data-short="{E(short_)}">{lab}</th>')
        i = j + 1
    hdr = []
    for n, c in enumerate(cols):
        cl = (c.get("c") or "") + (" gx" if n and c["g"] != cols[n - 1]["g"] else "")
        d = f' data-d="{c["d"]}"' if c.get("d") else ""
        ttl = f' title="{E(c["t"])}"' if c.get("t") else ""
        h_ = c["h"]
        if c.get("sk"):
            dirn = "asc" if c.get("asc") else "desc"
            srt = ' aria-sort="' + ("ascending" if dirn == "asc" else "descending") + '"' if sort_default == n else ""
            h_ = f'<button type="button" class="srt" data-sk="{n}" data-dir="{dirn}">{h_}</button>'
            d += srt
        hdr.append(f'<th class="{cl.strip()}" data-gi="{gi[n]}"{d}{ttl}>{h_}</th>')
    body = []
    for row in rows:
        kind, item = row[0], row[1]
        rcls = row[2] if len(row) > 2 else ""
        if house and kind == "row" and "us" not in rcls.split() and is_house_row(item):
            rcls = (rcls + " us hs-row").strip()
        if kind == "grp":
            body.append(f'<tr class="grp band {rcls}"><td colspan="{len(cols)}">{item}</td></tr>')
            continue
        tds = []
        for n, c in enumerate(cols):
            cl = (c.get("c") or "") + (" gx" if n and c["g"] != cols[n - 1]["g"] else "") + ((" " + c["cf"](item)) if c.get("cf") else "")
            d = f' data-d="{c["d"]}"' if c.get("d") else ""
            if c.get("sk"):
                v = c["sk"](item)
                d += f' data-v="{"" if v is None else round(float(v), 5)}"'
            if c.get("a"):
                d += c["a"](item)
            tds.append(f'<td class="{cl.strip()}"{d}>{c["f"](item)}</td>')
        body.append(f'<tr class="{rcls}">' + "".join(tds) + "</tr>")
    srt = any(c.get("sk") for c in cols)
    return (f'<div class="tblwrap"><table class="rb lg {cls}" data-max="{max_level}"{" data-sortable=" + chr(34) + "1" + chr(34) if srt else ""}>'
            f'<thead><tr class="ghr">{"".join(top)}</tr><tr>{"".join(hdr)}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def brd(title, sub, table, foot, extra=""):
    return (f'    <div class="brd">\n      <div class="brd-h"><h4>{title}<small>{sub}</small></h4></div>\n'
            f'      <div class="brd-b">{table}</div>\n      <div class="brd-f">{foot}</div>\n{extra}    </div>\n')


def tabs(grp, items, note=""):
    """items: [(tab id, label, html)] -> the landing's segmented tabs (lp-tabbar) and panes."""
    btns = "".join(f'<button type="button" role="tab" data-grp="{grp}" data-tab="{tid}" aria-controls="{tid}" '
                   f'aria-selected="{"true" if i == 0 else "false"}" tabindex="{0 if i == 0 else -1}"'
                   f'{" class=" + chr(34) + "on" + chr(34) if i == 0 else ""}>{lab}</button>' for i, (tid, lab, _) in enumerate(items))
    panes = "".join(f'<div class="lp-pane" role="tabpanel" id="{tid}" data-pane-grp="{grp}"{"" if i == 0 else " hidden"}>{h}</div>'
                    for i, (tid, _, h) in enumerate(items))
    return (f'<div class="lp-tabbar"><div class="seg lp-tabs" role="tablist" aria-label="{E(grp)}">{btns}</div>'
            f'<span class="muted">{note}</span></div>{panes}')


def read_block(sents, title="Computed read"):
    sents = [s for s in (sents or []) if s]
    if not sents:
        return ""
    return (f'<div class="ph-rd" title="Rule-based, from the numbers in this section"><span class="ph-rd-k">{title}</span>'
            f'<p>{" ".join(sents)}</p></div>')


def ladder(rows):
    """rows: [(label, sub, p, cls, extra_html)] -> the odds ladder (lr rows)."""
    out = []
    for lab, sub, p, cls, extra in rows:
        w = 0.0 if p is None else max(0.0, min(100.0, 100 * p))
        out.append(f'<div class="lr {cls}"><div class="k">{lab}' + (f"<small>{sub}</small>" if sub else "") + '</div>'
                   f'<div class="tr"><i style="width:{w:.1f}%"></i></div><div class="v">{pct1(p)}{extra or ""}</div></div>')
    return '<div class="ladder2">' + "".join(out) + "</div>"
