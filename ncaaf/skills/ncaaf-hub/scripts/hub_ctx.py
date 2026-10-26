#!/usr/bin/env python3
"""hub_ctx — the build's context: one object over the pull (lookups by team, week, game) and the formatting every page
shares (kickoff times, lines, results, covers, records, ranks). Machine work only; nothing authored."""
import sys
from collections import defaultdict

sys.dont_write_bytecode = True
import hub_common as HC  # noqa: E402

C = HC.C
E = HC.E
DASH, DOT, EN, MINUS = HC.DASH, HC.DOT, HC.EN, HC.MINUS


class X:
    def __init__(self, P):
        self.P = P
        self.season = P["season"]
        self.week = P["week"]
        self.reg = P["reg"]
        self.teams = P["reg"]["teams"]
        self.confs = P["reg"]["confs"]
        HC.set_registry(self.teams)
        self.ev = P["events"]
        self.evid = {e["eid"]: e for e in self.ev}
        self.by_team = defaultdict(list)
        for e in self.ev:
            for s in ("h", "a"):
                self.by_team[e[s]["id"]].append(e)
        for t in self.by_team:
            self.by_team[t].sort(key=lambda e: e["date"] or "")
        self.rat = P["ratings"]
        self.sim = P["sim"]["teams"]
        self.smeta = P["sim"]["meta"]
        self.today = P["today"]
        self.rec = P["teamrec"]
        self.stats = P["stats"]
        self.rk = P["rankings"] or {}
        self.ap = {r["id"]: r["rank"] for r in (self.rk.get("ap") or {}).get("ranks", [])}
        self.usa = {r["id"]: r["rank"] for r in (self.rk.get("usa") or {}).get("ranks", [])}
        self.cfp = {r["id"]: r["rank"] for r in (self.rk.get("cfp") or {}).get("ranks", [])}
        kal = P.get("kalshi") or {}
        self.kal_ok = bool(kal.get("ok"))
        self.kal_why = kal.get("why") or ""
        self.kg = kal.get("games") or {}
        self.kf = kal.get("futures") or {"title": {}, "playoff": {}, "conf": {}}
        self.kmeta = kal.get("meta") or {}
        self.last = P.get("last") or {}
        self.gsum = P.get("games") or {}
        self.facts = P.get("facts") or {}
        self.model = P["model"]
        self.stat_defs = P.get("stat_defs") or []
        self.now = C.parse_iso(P["built_utc"])
        self.cal = P["cal"]
        self.reg_weeks = [c for c in self.cal if c["st"] == 2]
        self.n_reg = len(self.reg_weeks)
        self.game_pages = set()          # event ids with a page (set by the builder)
        self.conf_order = [c for c in ("SEC", "B1G", "B12", "ACC", "AAC", "P12", "MWC", "SBC", "MAC", "CUSA", "IND") if c in self.confs]

    # ---------------------------------------------------------------- teams
    def t(self, tid):
        return self.teams.get(tid)

    def key(self, tid):
        t = self.teams.get(tid)
        return t["key"] if t else None

    def loc(self, tid, side=None):
        t = self.teams.get(tid)
        if t:
            return t["loc"]
        return (side or {}).get("loc") or "FCS opponent"

    def abbr(self, tid, side=None):
        t = self.teams.get(tid)
        return t["abbr"] if t else ((side or {}).get("abbr") or "FCS")

    def conf_short(self, ck):
        c = self.confs.get(ck)
        return c["short"] if c else ck

    def record(self, tid):
        r = self.rec.get(tid)
        return HC.rec(r["w"], r["l"]) if r else DASH

    def conf_record(self, tid):
        r = self.rec.get(tid)
        return HC.rec(r["cw"], r["cl"]) if r else DASH

    def ap_rank(self, tid):
        return self.ap.get(tid)

    def rank_html(self, tid):
        r = self.ap.get(tid)
        return f'<span class="rkn" title="AP Top 25">{r}</span>' if r else ""

    def team_cell(self, tid, side=None, sub=None, link=True):
        """chip + (rank) name with an optional second line; FBS teams link to their page."""
        nm = E(self.loc(tid, side))
        rk = self.rank_html(tid) if tid in self.teams else ""
        inner = f'<b>{rk}{nm}</b>' + (f"<small>{sub}</small>" if sub else "")
        body = f'<span class="nm2">{inner}</span>'
        if link and tid in self.teams:
            body = f'<a class="tl2" href="#{E(self.key(tid))}">{body}</a>'
        return f'<span class="tm">{HC.chip(tid, (side or {}).get("abbr"))}{body}</span>'

    def team_link(self, tid, side=None, text=None):
        nm = E(text or self.loc(tid, side))
        if tid in self.teams:
            return f'<a class="wk-a" href="#{E(self.key(tid))}">{nm}</a>'
        return nm

    # ---------------------------------------------------------------- games
    def when(self, e):
        d = C.parse_iso(e["date"])
        if not d:
            return DASH, DASH, ""
        if not e.get("time_valid", True):
            # ESPN parks an unset kickoff at midnight Eastern of the listed date: name that date, never a fake late-night CT time
            de = d.astimezone(C.ET) if C.ET else d
            return "TBD", de.strftime("%a %b ") + str(de.day), ""
        day = C.ct_day(d)
        return C.ct_time(d) + " CT", day, C.utc_hm(d) + " UTC"

    def state(self, e):
        s = e["status"]
        if s["completed"]:
            return "final"
        if s["state"] == "in":
            return "live"
        nm = s.get("name") or ""
        if "POSTPONED" in nm or "CANCEL" in nm:
            return "off"
        d = C.parse_iso(e["date"])
        if d and d <= self.now:
            return "underway"
        return "pre"

    def winner(self, e):
        if not e["status"]["completed"] or e["h"]["score"] is None:
            return None
        return e["h"]["id"] if e["h"]["score"] > e["a"]["score"] else e["a"]["id"]

    def score_txt(self, e, first=None):
        """'OSU 31–17' style: winner first unless `first` (a team id) is given (then that team's score first)."""
        h, a = e["h"], e["a"]
        if h["score"] is None:
            return DASH
        if first:
            me, op = (h, a) if first == h["id"] else (a, h)
            return f"{me['score']}{EN}{op['score']}"
        w, l = (h, a) if h["score"] > a["score"] else (a, h)
        return f"{E(self.abbr(w['id'], w))} {w['score']}{EN}{l['score']}"

    def line_of(self, e):
        """The market line to print: the closing line on a final / a game under way, else the current DraftKings line."""
        if e["status"]["completed"] or e["status"]["state"] == "in":
            return e.get("cl") or None
        return e.get("odds") or None

    def mk_txt(self, e, o=None):
        o = o if o is not None else self.line_of(e)
        if not o or o.get("spread") is None:
            return None
        return C.line_txt(o["spread"], self.abbr(e["h"]["id"], e["h"]), self.abbr(e["a"]["id"], e["a"]))

    def cover(self, e):
        """(text, home covered?) against the closing line; total over/under."""
        o = e.get("cl")
        if not o or o.get("spread") is None or e["h"]["score"] is None:
            return None
        m = e["h"]["score"] - e["a"]["score"]
        x = m + o["spread"]
        hab, aab = self.abbr(e["h"]["id"], e["h"]), self.abbr(e["a"]["id"], e["a"])
        cv = "push" if abs(x) < 1e-9 else (f"{hab} covered" if x > 0 else f"{aab} covered")
        tt = ""
        if o.get("total"):
            pts = e["h"]["score"] + e["a"]["score"]
            tt = "push" if pts == o["total"] else ("over" if pts > o["total"] else "under")
        return cv, tt

    def hm_txt(self, e, short=False):
        """HOUSE MODEL pregame text: favorite and win chance, line, total."""
        hm = e.get("hm_pre") if e["status"]["completed"] else e.get("hm")
        if not hm:
            return DASH, ""
        h, a = e["h"], e["a"]
        p = hm["p"]
        fav, pf = (h, p) if p >= 0.5 else (a, 1 - p)
        ln = C.line_txt(-hm["line"], self.abbr(h["id"], h), self.abbr(a["id"], a))
        main = f"{E(self.abbr(fav['id'], fav))} {C.pct1(pf)}"
        sub = f"{E(ln)}" + ("" if short else f" {DOT} total {C.fmt(hm['total'])}")
        return main, sub

    def kal_txt(self, e):
        k = self.kg.get(e["eid"])
        if not k:
            return None
        h, a = e["h"], e["a"]
        p = k["p_home"]
        fav, pf = (h, p) if p >= 0.5 else (a, 1 - p)
        tag = "pre-kickoff" if k.get("pre") else "book"
        return (f"{E(self.abbr(fav['id'], fav))} {C.pct1(pf)}", f"{tag}{' · thin' if k.get('thin') else ''} · {k['c_home']}¢/{k['c_away']}¢")

    def game_link(self, e, text="Game page ›", cls="sb-gm"):
        if e["eid"] in self.game_pages:
            return f'<a class="{cls}" href="#G{e["eid"]}">{text}</a>'
        return ""

    def week_label(self, e):
        if e["st"] == 3:
            return "Postseason"
        return f"Week {e['week']}"

    def week_range(self, w):
        c = next((c for c in self.cal if c["st"] == 2 and c["week"] == w), None)
        return (c or {}).get("detail") or ""

    def is_title(self, e):
        fb = {t: v["conf"] for t, v in self.teams.items()}
        note = " ".join(e.get("notes") or [])
        return "championship" in note.lower() and fb.get(e["h"]["id"]) and fb.get(e["h"]["id"]) == fb.get(e["a"]["id"])

    def next_game(self, tid):
        for e in self.by_team.get(tid, []):
            if not e["status"]["completed"] and self.state(e) != "off":
                return e
        return None

    def last_game(self, tid):
        g = [e for e in self.by_team.get(tid, []) if e["status"]["completed"]]
        return g[-1] if g else None

    def stat(self, tid, k):
        s = self.stats.get(tid) or {}
        return (s.get("v") or {}).get(k), (s.get("rk") or {}).get(k), (s.get("pct") or {}).get(k)
