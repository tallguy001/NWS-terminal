#!/usr/bin/env python3
"""ncaaf_model.py — the NCAAF HOUSE MODEL: offense / defense points ratings for every FBS team, game lines and win chances.

    python3 ncaaf_model.py ratings [--season Y] [--top 25]         this season's ratings from the live finals (ncaaf-data-pull)
    python3 ncaaf_model.py predict AWAY HOME [--neutral]           one game: HOUSE MODEL line, total, win chance
    python3 ncaaf_model.py backtest [--seasons 2019-2025]          walk-forward against the closing market (calibration.json params)
    python3 ncaaf_model.py calibrate [--train 2016-2023] [--test 2024-2025] [--write]
                                                                   v1 grid search on the training seasons (points layer only)
    python3 ncaaf_model.py calibrate-v11 [--train 2016-2023] [--test 2024-2025] [--loso] [--write]
                                                                   the v1.1 layers (preseason poll prior, box-score efficiency
                                                                   stack) on top of the v1 points parameters; held-out report,
                                                                   leave-one-season-out check, writes references/calibration.json
                                                                   and references/priors_<Y+1>.json

The model (deterministic; no market input anywhere — the market is only the yardstick):
  * Each team-game score = mu + off(team) - def(opponent) ± hfa/2 (home +, away −, neutral 0). Net rating = off + def =
    points better than an average FBS team on a neutral field; line = net(home) - net(away) + hfa (non-neutral).
  * Fit: weighted least squares with a Gaussian prior on every rating (ridge toward the prior; prior strength k = "games'
    worth"), so early-season ratings lean on the prior and the data take over as games accrue. FCS opponents share a group
    offense and defense effect (fitted) with small individual deviations, so a win over an FCS team counts for what FCS
    teams are, not for nothing.
  * Blowouts: the margin is compressed past `cap` points (the winner's score is reduced by (excess)·(1 − shrink)), so a
    63–0 win over an overmatched opponent says less than its raw margin. Totals use the same adjusted scores.
  * Prior for a new season: last season's final rating regressed toward the team's CURRENT conference mean of last season's
    ratings (rho = carry-over), so a team that changed conference starts from its new league's level; teams new to the
    data start 3 points below their conference mean.
  * Win chance = Phi(line / sigma) with sigma fitted walk-forward (larger in the first `early_weeks` weeks).
v1.1 (2026-10-26) adds two non-market inputs, each validated walk-forward (references/calibration.json "v11"):
  * Preseason poll prior: the prior net is replaced by E[season-final net | prior net, sqrt(preseason AP points share),
    received votes] (a regression on past seasons; references/corpus/polls_pre.json), split evenly over offense and defense.
    The poll is public opinion released before any game, not a betting market.
  * Box-score efficiency: opponent-adjusted offense / defense ratings of rushing yards per carry, passing yards per dropback
    (sacks counted) and giveaways, fitted the same ridge way from FBS v FBS team boxes (references/corpus/boxes_<Y>.json.gz;
    this season's from ESPN, cached). The line is a stack: c·(points line) + Σ w_m·(efficiency difference), with separate
    efficiency weights while predicting weeks 1–4. Given the points line, the giveaway weight is positive — a turnover-luck
    correction (turnovers barely persist, so a team that scored despite them is better than its points say). Because the stack is linear in each team, it folds into one rating per team:
    offense = c·scoring offense + Σ w_m·O_m, defense likewise, net = offense + defense, home field = c·hfa. Totals stay on the
    points layer. FCS teams (no boxes) keep their points ratings.
Calibration (calibration.json) records the chosen parameters, the training seasons and the held-out seasons' numbers against
the closing market (ESPN core odds: DraftKings / ESPN BET). Advisory only: the closing market is the better forecaster.
"""
import argparse
import glob
import gzip
import json
import math
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.normpath(os.path.join(HERE, "..", "references"))
CORPUS = os.path.join(REFS, "corpus")
CAL_PATH = os.path.join(REFS, "calibration.json")

try:
    import numpy as np
except ImportError:  # pragma: no cover
    sys.exit("[ncaaf-sim] numpy is required")

DEFAULT = dict(hfa=2.5, k_off=3.0, k_def=3.0, k_fcs=6.0, rho=0.60, cap=28.0, shrink=0.0, w_fcs=1.0, tau=0.0,
               sigma=16.0, sigma_early=17.5, early_weeks=4, mu0=28.0, new_team=-3.0, k_e=4.0, rho_e=0.75)
G_COLS = ["eid", "st", "week", "date", "hid", "aid", "hs", "as", "neutral", "conf", "spread", "total", "ml_h", "ml_a", "prov", "note"]


def Phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def load_cal():
    if os.path.exists(CAL_PATH):
        with open(CAL_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"params": dict(DEFAULT)}


def params():
    P = dict(DEFAULT)
    P.update((load_cal().get("params") or {}))
    return P


# ============================================================================ corpus
def load_corpus(season):
    p = os.path.join(CORPUS, f"games_{season}.json.gz")
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        d = json.load(f)
    d["games"] = [dict(zip(d.get("cols") or G_COLS, r)) for r in d["games"]]
    return d


def corpus_seasons():
    out = []
    for p in sorted(glob.glob(os.path.join(CORPUS, "games_*.json.gz"))):
        try:
            out.append(int(os.path.basename(p)[6:10]))
        except ValueError:
            pass
    return out


# ============================================================================ v1.1 inputs: preseason poll, box-score efficiency
CACHE = os.environ.get("NCAAF_CACHE", "/tmp/ncaaf_cache")
POLL_PATH = os.path.join(CORPUS, "polls_pre.json")
EFF = {   # per team-game box -> the efficiency each rating layer fits (FBS v FBS finals only)
    "rypc": lambda b: b["ry"] / b["ra"] if b.get("ra") and b.get("ry") is not None else None,
    "pypa": lambda b: b["py"] / (b["pa"] + (b.get("sk") or 0)) if b.get("pa") and b.get("py") is not None else None,
    "to": lambda b: b["to"] if b.get("to") is not None else None,
}
_POLLS = None


def load_boxes(season):
    """Closed season's team boxes: {eid: {team id: {plays, yds, ..}}} (None when the corpus has no box file)."""
    p = os.path.join(CORPUS, f"boxes_{season}.json.gz")
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        d = json.load(f)
    cols = d["cols"]
    return {eid: {t: dict(zip(cols, v)) for t, v in tm.items()} for eid, tm in d["rows"].items()}


def polls():
    """Preseason AP poll by season (packaged corpus + any season fetched since into the cache)."""
    global _POLLS
    if _POLLS is None:
        _POLLS = {}
        for p in (POLL_PATH, os.path.join(CACHE, "polls_pre_extra.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    _POLLS.update(json.load(f))
            except (OSError, ValueError):
                pass
    return _POLLS


def ensure_poll(season):
    """This season's preseason poll: packaged, cached, or fetched once (None before it is published)."""
    if str(season) in polls():
        return polls()[str(season)]
    sys.path.insert(0, HERE)
    import build_polls as BP
    p = BP.fetch(season)
    if p:
        _POLLS[str(season)] = p
        os.makedirs(CACHE, exist_ok=True)
        extra = os.path.join(CACHE, "polls_pre_extra.json")
        try:
            with open(extra, encoding="utf-8") as f:
                cur = json.load(f)
        except (OSError, ValueError):
            cur = {}
        cur[str(season)] = p
        with open(extra, "w", encoding="utf-8") as f:
            json.dump(cur, f)
    return p


def poll_share(season, t):
    p = polls().get(str(season))
    return None if not p else p["points"].get(t, 0.0) / p["max"]


def _eff_obs(games, boxes, fbs, m):
    f = EFF[m]
    out = []
    for g in games:
        bx = boxes.get(g.get("eid")) if boxes else None
        h, a = g["hid"], g["aid"]
        if not bx or h not in fbs or a not in fbs or h not in bx or a not in bx:
            continue
        hf = 0 if g.get("neutral") else 1
        for me, op, sg in ((h, a, hf), (a, h, -hf)):
            v = f(bx[me])
            if v is not None:
                out.append((me, op, v, sg))
    return out


def fit_eff(obs, fbs, prior, k):
    """One efficiency layer: value(me vs op) = mu + O(me) - D(op) + h·site/2, ridge toward the prior (k games' worth);
    O and D centred on the FBS average. -> (mu, O, D, h)."""
    ids = sorted(fbs)
    ix = {t: i for i, t in enumerate(ids)}
    n = len(ids)
    K = 2 * n + 2
    A = np.zeros((K, K))
    b = np.zeros(K)
    for me, op, y, hf in obs:
        xs = ((0, 1.0), (1, hf / 2.0), (2 + ix[me], 1.0), (2 + n + ix[op], -1.0))
        for i, xi in xs:
            b[i] += xi * y
            for j, xj in xs:
                A[i, j] += xi * xj
    lam = np.zeros(K)
    b0 = np.zeros(K)
    mu0 = prior.get("mu")
    lam[0], b0[0] = 1e-3, (mu0 if mu0 is not None else (sum(o[2] for o in obs) / len(obs) if obs else 0.0))
    lam[1], b0[1] = 5.0, prior.get("h") or 0.0
    pt = prior.get("teams") or {}
    for t in ids:
        po, pd = pt.get(t, (0.0, 0.0))
        lam[2 + ix[t]], b0[2 + ix[t]] = k, po
        lam[2 + n + ix[t]], b0[2 + n + ix[t]] = k, pd
    beta = np.linalg.solve(A + np.diag(lam), b + lam * b0)
    O = {t: float(beta[2 + ix[t]]) for t in ids}
    D = {t: float(beta[2 + n + ix[t]]) for t in ids}
    mo, md = sum(O.values()) / n, sum(D.values()) / n
    return (float(beta[0] + mo - md), {t: v - mo for t, v in O.items()}, {t: v - md for t, v in D.items()}, float(beta[1]))


def eff_prior(prev, fbs, rho):
    """Next season's efficiency prior: last season's final layer regressed toward the current conference mean."""
    if prev is None:
        return {"teams": {}, "mu": None}
    mu, O, D, h = prev
    confs = {}
    for t, c in fbs.items():
        if t in O:
            confs.setdefault(c, []).append(t)
    cm = {c: (sum(O[t] for t in ts) / len(ts), sum(D[t] for t in ts) / len(ts)) for c, ts in confs.items()}
    out = {}
    for t, c in fbs.items():
        mo, md = cm.get(c, (0.0, 0.0))
        out[t] = (rho * O[t] + (1 - rho) * mo, rho * D[t] + (1 - rho) * md) if t in O else (mo - 0.1, md - 0.1)
    return {"teams": out, "mu": mu, "h": h}


# ============================================================================ the fit
class Ratings:
    """A fitted state: off/def per team id, mu, the FCS group effects, hfa, sigma; predicts any pairing."""

    def __init__(self, off, dfn, mu, g_off, g_def, fbs, P, n_games=None, season=None, through=None, se=None):
        self.off, self.dfn, self.mu = off, dfn, mu          # the points layer (scoring offense / defense)
        self.g_off, self.g_def = g_off, g_def
        self.fbs, self.P = fbs, P
        self.n_games = n_games or {}
        self.season, self.through = season, through
        self.se = se or {}
        self.hfa = P["hfa"]                                  # effective home field (c·hfa once the stack is attached)
        self.E, self.early, self._c = None, False, None      # v1.1 efficiency layers {m: (mu, O, D, h)} and stack weights

    def attach_eff(self, E, early):
        """Attach the efficiency layers; with stack coefficients in P, o / d / net / line become the v1.1 ratings."""
        self.E, self.early = E, early
        st = self.P.get("stack") or {}
        c = st.get("coef")
        if c:
            fe = st["feats"]
            n = len(fe)
            self._c = (c[0], {m: c[1 + i] + (c[1 + n + i] if (early and len(c) > 1 + n) else 0.0) for i, m in enumerate(fe)})
            self.hfa = c[0] * self.P["hfa"]
        return self

    def po(self, t):
        return self.off.get(t, self.g_off)

    def pd(self, t):
        return self.dfn.get(t, self.g_def)

    def o(self, t):
        if self._c is None or t not in self.fbs:
            return self.po(t)
        cl, w = self._c
        return cl * self.po(t) + sum(wm * self.E[m][1].get(t, 0.0) for m, wm in w.items())

    def d(self, t):
        if self._c is None or t not in self.fbs:
            return self.pd(t)
        cl, w = self._c
        return cl * self.pd(t) + sum(wm * self.E[m][2].get(t, 0.0) for m, wm in w.items())

    def net(self, t):
        return self.o(t) + self.d(t)

    def line(self, h, a, neutral=False):
        """Expected home margin."""
        return self.net(h) - self.net(a) + (0.0 if neutral else self.hfa)

    def pline(self, h, a, neutral=False):
        """The points layer's line alone (v1)."""
        return self.po(h) + self.pd(h) - self.po(a) - self.pd(a) + (0.0 if neutral else self.P["hfa"])

    def eff_diff(self, m, h, a):
        _, O, D, _ = self.E[m]
        return (O.get(h, 0.0) + D.get(h, 0.0)) - (O.get(a, 0.0) + D.get(a, 0.0))

    def total(self, h, a):
        return 2 * self.mu + self.po(h) + self.po(a) - self.pd(h) - self.pd(a)

    def sigma(self, week=None, st=2, line=0.0):
        """Margin SD for the win chance: sigma (sigma_early in the first weeks), widened by sigma_slope per 10 points of line
        (big mismatches are less certain in points than a constant SD says)."""
        s = self.P["sigma"]
        if st == 2 and week is not None and week <= self.P.get("early_weeks", 4):
            s = self.P.get("sigma_early", s)
        return s * (1.0 + (self.P.get("sigma_slope") or 0.0) * abs(line) / 10.0)

    def p_home(self, h, a, neutral=False, week=None, st=2):
        ln = self.line(h, a, neutral)
        return Phi(ln / self.sigma(week, st, ln))

    def to_json(self):
        j = {"season": self.season, "through": self.through, "mu": round(self.mu, 4), "g_off": round(self.g_off, 4),
             "g_def": round(self.g_def, 4), "hfa": self.P["hfa"],
             "teams": {t: [round(self.off[t], 4), round(self.dfn[t], 4), self.n_games.get(t, 0), round(self.se.get(t, 0.0), 4)]
                       for t in self.off}}
        if self.E:
            j["eff"] = {m: {"mu": round(mu, 5), "h": round(h, 5), "teams": {t: [round(O[t], 5), round(D[t], 5)] for t in O}}
                        for m, (mu, O, D, h) in self.E.items()}
        return j

    @classmethod
    def from_json(cls, j, fbs, P):
        off = {t: v[0] for t, v in j["teams"].items()}
        dfn = {t: v[1] for t, v in j["teams"].items()}
        ng = {t: v[2] for t, v in j["teams"].items()}
        se = {t: (v[3] if len(v) > 3 else 0.0) for t, v in j["teams"].items()}
        R = cls(off, dfn, j["mu"], j["g_off"], j["g_def"], fbs, P, ng, j.get("season"), j.get("through"), se)
        if j.get("eff"):
            R.E = {m: (e["mu"], {t: v[0] for t, v in e["teams"].items()}, {t: v[1] for t, v in e["teams"].items()}, e["h"])
                   for m, e in j["eff"].items()}
        return R


def adj_scores(hs, as_, P):
    m = hs - as_
    cap = P.get("cap") or 0
    if cap and abs(m) > cap:
        ex = (abs(m) - cap) * (1.0 - P.get("shrink", 0.0))
        if m > 0:
            hs = hs - ex
        else:
            as_ = as_ - ex
    return hs, as_


def fit(games, fbs, prior, P, season=None, through=None, ref_week=None, want_se=False, boxes=None):
    """games: dicts with hid, aid, hs, as, neutral, week, st (and eid, for the boxes). fbs: {id: conf} for the season.
    prior: {"teams": {id: (po, pd)}, "g_off": x, "g_def": y, "mu": m, "fcs_dev": {id: (o, d)}, "eff": {m: layer prior}}.
    boxes: {eid: {team id: box}} -> with P["stack"], the v1.1 efficiency layers are fitted from the same games and attached
    (early weights when predicting weeks 1–`early_weeks`, i.e. ref_week within them)."""
    teams = set(fbs)
    for g in games:
        teams.add(g["hid"])
        teams.add(g["aid"])
    ids = sorted(teams)
    ix = {t: i for i, t in enumerate(ids)}
    n = len(ids)
    K = 2 * n + 3                         # mu, off[n], def[n], g_off, g_def
    GO, GD = 2 * n + 1, 2 * n + 2
    A = np.zeros((K, K))
    b = np.zeros(K)
    hfa = P["hfa"]
    tau = P.get("tau") or 0.0
    ng = {}
    rows = []
    for g in games:
        h, a = g["hid"], g["aid"]
        hs, as_ = adj_scores(float(g["hs"]), float(g["as"]), P)
        hf = 0.0 if g.get("neutral") else hfa / 2.0
        w = 1.0
        if (h not in fbs) or (a not in fbs):
            w *= P.get("w_fcs", 1.0)
        if tau and ref_week is not None and g.get("st") == 2 and g.get("week") is not None:
            w *= math.exp(-max(0, ref_week - g["week"]) / tau)
        ng[h] = ng.get(h, 0) + 1
        ng[a] = ng.get(a, 0) + 1
        for me, op, y in ((h, a, hs - hf), (a, h, as_ + hf)):
            x = {0: 1.0, 1 + ix[me]: 1.0, 1 + n + ix[op]: -1.0}
            if me not in fbs:
                x[GO] = x.get(GO, 0.0) + 1.0
            if op not in fbs:
                x[GD] = x.get(GD, 0.0) - 1.0
            rows.append((x, y, w))
    for x, y, w in rows:
        ks = list(x.items())
        for i, xi in ks:
            b[i] += w * xi * y
            for j, xj in ks:
                A[i, j] += w * xi * xj
    pt = prior.get("teams") or {}
    dev = prior.get("fcs_dev") or {}
    beta0 = np.zeros(K)
    lam = np.zeros(K)
    lam[0], beta0[0] = 1e-3, prior.get("mu", P.get("mu0", 28.0))
    lam[GO], beta0[GO] = 0.05, prior.get("g_off", -9.0)
    lam[GD], beta0[GD] = 0.05, prior.get("g_def", -9.0)
    for t in ids:
        i = ix[t]
        if t in fbs:
            po, pd = pt.get(t, (prior.get("new_o", -3.0), prior.get("new_d", -3.0)))
            lam[1 + i], beta0[1 + i] = P["k_off"], po
            lam[1 + n + i], beta0[1 + n + i] = P["k_def"], pd
        else:
            do, dd = dev.get(t, (0.0, 0.0))
            lam[1 + i], beta0[1 + i] = P["k_fcs"], do
            lam[1 + n + i], beta0[1 + n + i] = P["k_fcs"], dd
    A2 = A + np.diag(lam)
    beta = np.linalg.solve(A2, b + lam * beta0)
    mu = beta[0]
    off = {t: beta[1 + ix[t]] for t in ids}
    dfn = {t: beta[1 + n + ix[t]] for t in ids}
    g_off, g_def = beta[GO], beta[GD]
    for t in ids:                          # FCS teams carry the group effect inside their value
        if t not in fbs:
            off[t] += g_off
            dfn[t] += g_def
    # center on the FBS average (an average FBS team = 0 / 0)
    fb = [t for t in ids if t in fbs]
    mo = sum(off[t] for t in fb) / len(fb)
    md = sum(dfn[t] for t in fb) / len(fb)
    for t in ids:
        off[t] -= mo
        dfn[t] -= md
    mu = mu + mo - md
    g_off -= mo
    g_def -= md
    se = {}
    if want_se:
        try:
            cov = np.linalg.inv(A2)
            # residual variance per team-score
            res = []
            for x, y, w in rows:
                pred = sum(beta[i] * xi for i, xi in x.items())
                res.append(y - pred)
            s2 = float(np.mean(np.square(res))) if res else 100.0
            for t in ids:
                i = ix[t]
                v = cov[1 + i, 1 + i] + cov[1 + n + i, 1 + n + i] + 2 * cov[1 + i, 1 + n + i]
                se[t] = math.sqrt(max(0.0, v * s2))
        except np.linalg.LinAlgError:
            se = {}
    R = Ratings(off, dfn, mu, g_off, g_def, fbs, P, ng, season, through, se)
    st = P.get("stack")
    if st and boxes is not None:
        ep = prior.get("eff") or {}
        E = {m: fit_eff(_eff_obs(games, boxes, fbs, m), fbs, ep.get(m) or {}, P.get("k_e", 4.0)) for m in st["feats"]}
        R.attach_eff(E, ref_week is not None and ref_week <= P.get("early_weeks", 4))
    return R


def prior_from(prev, fbs_now, P, prev2=None, season=None):
    """The next season's prior from last season's final Ratings (or None = flat). With `rho2` > 0 and the season before
    (`prev2`), program strength two seasons back enters too: base = rho·last + rho2·two back, the rest to the conference mean.
    v1.1: with P["poll"] and `season`'s preseason AP poll, each team's prior net moves to the poll regression's estimate
    (lam = share of the move; even split over offense and defense); with efficiency layers on `prev`, their priors too."""
    if prev is None:
        return {"teams": {}, "mu": P.get("mu0", 28.0), "g_off": -9.0, "g_def": -9.0, "new_o": -3.0, "new_d": -3.0}
    rho, rho2 = P["rho"], (P.get("rho2") or 0.0)
    confs = {}
    for t, c in fbs_now.items():
        if t in prev.off:
            confs.setdefault(c, []).append(t)
    cm = {c: (sum(prev.off[t] for t in ts) / len(ts), sum(prev.dfn[t] for t in ts) / len(ts)) for c, ts in confs.items()}
    teams = {}
    nt = P.get("new_team", -3.0)
    for t, c in fbs_now.items():
        mo, md = cm.get(c, (0.0, 0.0))
        if t in prev.off:
            if rho2 and prev2 is not None and t in prev2.off:
                teams[t] = (rho * prev.off[t] + rho2 * prev2.off[t] + (1 - rho - rho2) * mo,
                            rho * prev.dfn[t] + rho2 * prev2.dfn[t] + (1 - rho - rho2) * md)
            else:
                teams[t] = (rho * prev.off[t] + (1 - rho) * mo, rho * prev.dfn[t] + (1 - rho) * md)
        else:
            teams[t] = (mo + nt / 2, md + nt / 2)
    pp = P.get("poll") or {}
    if pp.get("coef") and season is not None and polls().get(str(season)):
        c, lam = pp["coef"], pp.get("lam", 1.0)
        for t, (po, pd) in list(teams.items()):
            sh_ = poll_share(season, t)
            net = po + pd
            tgt = c[0] + c[1] * net + c[2] * math.sqrt(sh_) + c[3] * (1.0 if sh_ > 0 else 0.0)
            mv = lam * (tgt - net) / 2.0
            teams[t] = (po + mv, pd + mv)
    dev = {}
    for t in prev.off:
        if t not in prev.fbs and t not in fbs_now:
            dev[t] = (rho * (prev.off[t] - prev.g_off), rho * (prev.dfn[t] - prev.g_def))
    eff = {m: eff_prior(v, fbs_now, P.get("rho_e", 0.75)) for m, v in (prev.E or {}).items()}
    return {"teams": teams, "mu": prev.mu, "g_off": prev.g_off, "g_def": prev.g_def, "fcs_dev": dev, "eff": eff}


# ============================================================================ walk-forward
def chain(seasons, P, evaluate=None, log=None):
    """Fit season by season (each season's prior = the previous final). evaluate: set of seasons to score walk-forward.
    -> (final Ratings of the last season, [prediction rows])."""
    prev = prev2 = None
    preds = []
    for y in seasons:
        C_ = load_corpus(y)
        if C_ is None:
            continue
        fbs = C_["fbs"]
        G = C_["games"]
        B = (load_boxes(y) or {}) if P.get("stack") else None
        pr = prior_from(prev, fbs, P, prev2, season=y)
        if evaluate and y in evaluate:
            weeks = sorted({g["week"] for g in G if g["st"] == 2})
            for w in weeks:
                train = [g for g in G if g["st"] == 2 and g["week"] < w]
                R = fit(train, fbs, pr, P, y, w - 1, ref_week=w, boxes=B)
                for g in G:
                    if g["st"] == 2 and g["week"] == w:
                        preds.append(_pred_row(R, g, y, fbs))
            train = [g for g in G if g["st"] == 2]
            R = fit(train, fbs, pr, P, y, "reg", ref_week=max(weeks) + 1, boxes=B)
            for g in G:
                if g["st"] == 3:
                    preds.append(_pred_row(R, g, y, fbs))
        prev2, prev = prev, fit(G, fbs, pr, P, y, "final", ref_week=None, boxes=B)
        if log:
            log(f"  {y}: {len(G)} games")
    return prev, preds


def _pred_row(R, g, y, fbs):
    h, a = g["hid"], g["aid"]
    line = R.line(h, a, bool(g["neutral"]))
    row = {"season": y, "st": g["st"], "week": g["week"], "eid": g["eid"], "fbs2": (h in fbs and a in fbs),
           "line": line, "total": R.total(h, a), "margin": g["hs"] - g["as"], "pts": g["hs"] + g["as"],
           "spread": g.get("spread"), "mtotal": g.get("total"), "ml_h": g.get("ml_h"), "ml_a": g.get("ml_a")}
    if R.E is not None:      # the stack's inputs (calibrate-v11 fits the weights from these)
        row["line_pts"] = R.pline(h, a, bool(g["neutral"]))
        row["early"] = R.early
        row["eff"] = {m: R.eff_diff(m, h, a) for m in R.E} if row["fbs2"] else None
    return row


def _novig(mh, ma):
    def p(ml):
        if ml in (None, 0):
            return None
        ml = float(ml)
        return 100.0 / (ml + 100.0) if ml > 0 else -ml / (-ml + 100.0)
    ph, pa = p(mh), p(ma)
    if ph is None or pa is None:
        return None
    return ph / (ph + pa)


def score(preds, P, sig=None, early=None):
    """Metrics on FBS v FBS games with a closing line. Win chances with the given sigmas (else P's)."""
    sig = sig or P["sigma"]
    early = early or P.get("sigma_early", sig)
    rows = [r for r in preds if r["fbs2"] and r["spread"] is not None and r["margin"] != 0]
    if not rows:
        return {}
    ew = P.get("early_weeks", 4)
    out = {"n": len(rows)}
    mae_h = sum(abs(r["line"] - r["margin"]) for r in rows) / len(rows)
    mae_m = sum(abs(-r["spread"] - r["margin"]) for r in rows) / len(rows)
    bh = bm = llh = 0.0
    nm = 0
    agree = 0
    ats_n = ats_w = 0
    dif = []
    for r in rows:
        s = early if (r["st"] == 2 and r["week"] <= ew) else sig
        ph = min(max(Phi(r["line"] / s), 1e-4), 1 - 1e-4)
        y = 1.0 if r["margin"] > 0 else 0.0
        bh += (ph - y) ** 2
        llh += -(y * math.log(ph) + (1 - y) * math.log(1 - ph))
        pm = _novig(r["ml_h"], r["ml_a"])
        if pm is None:
            pm = Phi(-r["spread"] / sig)
        pm = min(max(pm, 1e-4), 1 - 1e-4)
        bm += (pm - y) ** 2
        dif.append((ph - y) ** 2 - (pm - y) ** 2)
        nm += 1
        agree += 1 if ((ph > 0.5) == (pm > 0.5)) else 0
        edge = r["line"] + r["spread"]                     # house home margin vs market's
        if abs(edge) >= 3 and r["margin"] + r["spread"] != 0:
            ats_n += 1
            ats_w += 1 if ((edge > 0) == (r["margin"] + r["spread"] > 0)) else 0
    out.update(mae_house=round(mae_h, 3), mae_market=round(mae_m, 3), brier_house=round(bh / len(rows), 5),
               brier_market=round(bm / nm, 5), logloss_house=round(llh / len(rows), 5), same_favorite=round(agree / nm, 4),
               ats_3plus=[ats_w, ats_n])
    tr = [r for r in rows if r["mtotal"]]
    if tr:
        out["mae_total_house"] = round(sum(abs(r["total"] - r["pts"]) for r in tr) / len(tr), 3)
        out["mae_total_market"] = round(sum(abs(r["mtotal"] - r["pts"]) for r in tr) / len(tr), 3)
    # paired bootstrap of the Brier difference (house − market): 95% interval
    import random
    rnd = random.Random(20261026)
    m = len(dif)
    boots = sorted(sum(dif[rnd.randrange(m)] for _ in range(m)) / m for _ in range(400))
    out["brier_diff"] = round(sum(dif) / m, 5)
    out["brier_diff_ci95"] = [round(boots[10], 5), round(boots[389], 5)]
    return out


def fit_sigma(preds, P):
    rows = [r for r in preds if r["fbs2"] and r["margin"] != 0]
    ew = P.get("early_weeks", 4)
    best = {}
    for name, sel in (("early", lambda r: r["st"] == 2 and r["week"] <= ew), ("late", lambda r: not (r["st"] == 2 and r["week"] <= ew))):
        rr = [r for r in rows if sel(r)]
        bl = None
        for s in [x / 2 for x in range(24, 48)]:
            ll = 0.0
            for r in rr:
                ph = min(max(Phi(r["line"] / s), 1e-4), 1 - 1e-4)
                y = 1.0 if r["margin"] > 0 else 0.0
                ll += -(y * math.log(ph) + (1 - y) * math.log(1 - ph))
            if bl is None or ll < bl[0]:
                bl = (ll, s)
        best[name] = bl[1] if bl else P["sigma"]
    return best["late"], best["early"]


def objective(preds):
    rows = [r for r in preds if r["fbs2"]]
    return sum(abs(r["line"] - r["margin"]) for r in rows) / max(1, len(rows))


def calibrate(train, test, write=False, log=print):
    seasons = corpus_seasons()
    first = seasons[0]
    P = dict(DEFAULT)
    grid = [("hfa", [2.0, 2.5, 3.0]), ("cap", [21.0, 28.0, 35.0, 0.0]), ("shrink", [0.0, 0.33]), ("rho", [0.5, 0.6, 0.7]),
            ("k_off", [2.0, 3.0, 4.5]), ("k_def", [2.0, 3.0, 4.5]), ("k_fcs", [3.0, 6.0, 12.0]), ("w_fcs", [0.5, 1.0]),
            ("tau", [0.0, 10.0])]
    tr = set(range(train[0], train[1] + 1))
    span = list(range(first, train[1] + 1))
    cache = {}

    def run(Pp):
        k = tuple(sorted(Pp.items()))
        if k not in cache:
            _, pr = chain(span, Pp, evaluate=tr)
            cache[k] = objective(pr)
        return cache[k]
    best = run(P)
    log(f"[calibrate] start MAE {best:.3f}")
    for _ in range(2):
        for name, vals in grid:
            for v in vals:
                Q = dict(P)
                Q[name] = v
                s = run(Q)
                if s < best - 1e-4:
                    best, P = s, Q
            log(f"  {name} = {P[name]} -> train MAE {best:.3f}")
    _, pr_tr = chain(span, P, evaluate=tr)
    sig, sig_e = fit_sigma(pr_tr, P)
    P["sigma"], P["sigma_early"] = sig, sig_e
    log(f"  sigma late {sig}, early {sig_e}")
    allspan = list(range(first, test[1] + 1))
    te = set(range(test[0], test[1] + 1))
    final, pr_all = chain(allspan, P, evaluate=tr | te)
    rep = {"train": {}, "test": {}}
    for y in sorted(tr | te):
        m = score([r for r in pr_all if r["season"] == y], P)
        rep["test" if y in te else "train"][str(y)] = m
    rep["train_all"] = score([r for r in pr_all if r["season"] in tr], P)
    rep["test_all"] = score([r for r in pr_all if r["season"] in te], P)
    doc = {"model": "ncaaf-sim HOUSE MODEL v1 (offense/defense ridge ratings)", "built": _now(),
           "params": P, "train_seasons": [train[0], train[1]], "test_seasons": [test[0], test[1]],
           "corpus": f"ESPN finals {first}–{test[1]}, closing lines from ESPN core odds (DraftKings / ESPN BET / consensus)",
           "report": rep,
           "reading": ("Held-out seasons scored walk-forward: each week predicted from games before it. The closing market is "
                       "the better forecaster (lower MAE and Brier); the HOUSE MODEL is advisory and never blended with it.")}
    if write:
        with open(CAL_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
        write_priors(final, test[1] + 1, P)
        log(f"  wrote {CAL_PATH}")
    return doc


# ============================================================================ v1.1 calibration
V11 = {"k": 4.0, "k_e": 4.0, "rho_e": 0.75, "feats": ["rypc", "pypa", "to"], "lam": 1.0, "form": "sqrt",
       "selected_on": ("validation seasons 2022–2023 with every coefficient fit on 2016–2021 (prior strength 3–5, poll form "
                       "sqrt / linear / log and share 0.5–1, efficiency sets of yards per play, first-down rate, rushing yards "
                       "per carry, passing yards per dropback, third downs, penalties and giveaways, efficiency prior "
                       "strength 2–16 and carry-over 0.4–0.75); the v1 points parameters were already at a flat optimum")}


def _stack_x(r, fe):
    e = 1.0 if r["early"] else 0.0
    return [r["line_pts"]] + [r["eff"][m] for m in fe] + [e * r["eff"][m] for m in fe]


def stack_fit(rows, fe):
    """margin ~ c·points line + Σ w_m·efficiency difference (+ early-week adjustments), no intercept, FBS v FBS games."""
    rr = [r for r in rows if r["fbs2"] and r.get("eff")]
    X = np.array([_stack_x(r, fe) for r in rr])
    y = np.array([r["margin"] for r in rr], dtype=float)
    return [round(float(v), 5) for v in np.linalg.lstsq(X, y, rcond=None)[0]]


def _restack(rows, fe, coef):
    for r in rows:
        if r["fbs2"] and r.get("eff"):
            r["line"] = float(np.dot(coef, _stack_x(r, fe)))
    return rows


def poll_fit(P, seasons):
    """Season-final points net ~ [1, prior net, sqrt(preseason AP points share), received votes] over `seasons`
    (points-layer chain, no poll, no boxes). -> (coef, rmse, rmse of the prior net alone, n)."""
    Pn = {k: v for k, v in P.items() if k not in ("poll", "stack")}
    prev = None
    X, Y = [], []
    for y in corpus_seasons():
        if y > max(seasons):
            break
        C_ = load_corpus(y)
        fbs = C_["fbs"]
        pr = prior_from(prev, fbs, Pn)
        fin = fit(C_["games"], fbs, pr, Pn, y, "final")
        if y in seasons and prev is not None and polls().get(str(y)):
            for t in fbs:
                if t in pr["teams"] and t in fin.off:
                    po, pd = pr["teams"][t]
                    sh = poll_share(y, t)
                    X.append([1.0, po + pd, math.sqrt(sh), 1.0 if sh > 0 else 0.0])
                    Y.append(fin.net(t))
        prev = fin
    X, Y = np.array(X), np.array(Y)
    c = np.linalg.lstsq(X, Y, rcond=None)[0]
    c0 = np.linalg.lstsq(X[:, :2], Y, rcond=None)[0]
    return ([round(float(v), 5) for v in c], round(float(np.sqrt(np.mean((Y - X @ c) ** 2))), 3),
            round(float(np.sqrt(np.mean((Y - X[:, :2] @ c0) ** 2))), 3), len(Y))


def _mae(rows, sel=lambda r: True):
    rr = [r for r in rows if r["fbs2"] and sel(r)]
    return sum(abs(r["line"] - r["margin"]) for r in rr) / max(1, len(rr))


def calibrate_v11(train, test, write=False, loso=False, log=print):
    """The v1.1 layers on top of the v1 points parameters: poll regression and stack weights fit on the training seasons,
    scored walk-forward on the held-out seasons against v1 and the closing line; optional leave-one-season-out check; then
    refit on every season for production (calibration.json params) and the next season's priors."""
    cal = load_cal()
    old = cal.get("v11") or {}
    P1 = dict(DEFAULT)
    P1.update(old.get("v1_params") or {k: v for k, v in (cal.get("params") or {}).items() if k not in ("poll", "stack")})
    fe = V11["feats"]
    V = dict(P1, k_off=V11["k"], k_def=V11["k"], k_e=V11["k_e"], rho_e=V11["rho_e"])
    seasons = corpus_seasons()
    first = seasons[0]
    tr = set(range(train[0], train[1] + 1))
    te = set(range(test[0], test[1] + 1))
    span = [y for y in seasons if y <= test[1]]
    ev = sorted(tr | te)

    def run(poll_seasons, stack_on, rows_P=None):
        pc = poll_fit(V, poll_seasons)
        Pt = dict(V, poll={"coef": pc[0], "lam": V11["lam"], "form": V11["form"]}, stack={"feats": fe, "coef": None})
        _, rows = chain(span, Pt, evaluate=set(ev))
        sc = stack_fit([r for r in rows if r["season"] in stack_on], fe)
        return pc, sc, _restack(rows, fe, sc)

    log(f"[calibrate-v11] v1 points parameters: {json.dumps(P1)}")
    _, rows_v1 = chain(span, P1, evaluate=set(ev))
    pc_tr, sc_tr, rows = run(list(range(first + 1, train[1] + 1)), tr)
    sig, sig_e = fit_sigma([r for r in rows if r["season"] in tr], P1)
    Ptr = dict(V, sigma=sig, sigma_early=sig_e)
    log(f"  train fit: poll {pc_tr[0]} (rmse {pc_tr[1]} vs prior alone {pc_tr[2]}, n {pc_tr[3]}) · stack {sc_tr} · sigma {sig}/{sig_e}")
    rep = {"train": {}, "test": {}}
    cmp_ = {}
    for y in ev:
        rep["test" if y in te else "train"][str(y)] = score([r for r in rows if r["season"] == y], Ptr)
    rep["train_all"] = score([r for r in rows if r["season"] in tr], Ptr)
    rep["test_all"] = score([r for r in rows if r["season"] in te], Ptr)
    for tag, ss in (("train", tr), ("test", te)):
        a = score([r for r in rows_v1 if r["season"] in ss], P1)
        b = rep[f"{tag}_all"]
        cmp_[tag] = {"v1": {k: a[k] for k in ("n", "mae_house", "brier_house", "logloss_house", "mae_market", "brier_market")},
                     "v1_1": {k: b[k] for k in ("n", "mae_house", "brier_house", "logloss_house")}}
    v1l = {r["eid"]: r["line"] for r in rows_v1}
    d = np.array([abs(r["line"] - r["margin"]) - abs(v1l[r["eid"]] - r["margin"]) for r in rows if r["season"] in te and r["fbs2"]])
    rng = np.random.default_rng(20261026)
    bs = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(4000)])
    cmp_["test_mae_delta"] = round(float(d.mean()), 4)
    cmp_["test_mae_delta_ci95"] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
    for wk, sel in (("wk1_4", lambda r: r["st"] == 2 and r["week"] <= 4), ("wk5_plus", lambda r: r["st"] == 2 and r["week"] > 4),
                    ("post", lambda r: r["st"] == 3)):
        q1 = [r for r in rows_v1 if r["season"] in te and sel(r)]
        q2 = [r for r in rows if r["season"] in te and sel(r)]
        cmp_[f"test_mae_{wk}"] = [round(_mae(q1), 3), round(_mae(q2), 3)]
    log(f"  held-out {test[0]}–{test[1]}: v1 {cmp_['test']['v1']['mae_house']} -> v1.1 {cmp_['test']['v1_1']['mae_house']} "
        f"(closing line {cmp_['test']['v1']['mae_market']}) · delta {cmp_['test_mae_delta']} CI {cmp_['test_mae_delta_ci95']}")
    lo = {}
    if loso:
        for y in ev:
            pc_y, sc_y, rows_y = run([s for s in range(first + 1, test[1] + 1) if s != y], set(ev) - {y})
            q = [r for r in rows_y if r["season"] == y and r["fbs2"]]
            dm = sum(abs(r["line"] - r["margin"]) - abs(v1l[r["eid"]] - r["margin"]) for r in q) / len(q)
            sg = P1["sigma"]
            qb = [r for r in q if r["margin"] != 0]
            db = sum((Phi(r["line"] / sg) - (r["margin"] > 0)) ** 2 - (Phi(v1l[r["eid"]] / sg) - (r["margin"] > 0)) ** 2 for r in qb) / len(qb)
            qe = [r for r in q if r["st"] == 2 and r["week"] <= 4]
            de = sum(abs(r["line"] - r["margin"]) - abs(v1l[r["eid"]] - r["margin"]) for r in qe) / max(1, len(qe))
            lo[str(y)] = {"mae_delta": round(dm, 4), "brier_delta": round(db, 5), "mae_delta_wk1_4": round(de, 4), "n": len(q)}
            log(f"  LOSO {y}: MAE {dm:+.3f} · Brier {db:+.5f} · weeks 1–4 {de:+.3f}")
        md = [v["mae_delta"] for v in lo.values()]
        lo["summary"] = {"mean_mae_delta": round(sum(md) / len(md), 4), "seasons_better": sum(1 for x in md if x < 0),
                         "seasons": len(md), "mean_brier_delta": round(sum(v["brier_delta"] for k, v in lo.items() if k != "summary") / len(md), 5),
                         "seasons_brier_better": sum(1 for k, v in lo.items() if k != "summary" and v["brier_delta"] < 0),
                         "mean_mae_delta_wk1_4": round(sum(v["mae_delta_wk1_4"] for k, v in lo.items() if k != "summary") / len(md), 4)}
        log(f"  LOSO summary {lo['summary']}")
    elif old.get("loso"):
        lo = old["loso"]
    # production: every season
    pc_all, sc_all, rows_all = run(list(range(first + 1, test[1] + 1)), set(ev))
    sig_a, sig_ae = fit_sigma(rows_all, P1)
    Pp = dict(V, sigma=sig_a, sigma_early=sig_ae, poll={"coef": pc_all[0], "lam": V11["lam"], "form": V11["form"]},
              stack={"feats": fe, "coef": sc_all})
    log(f"  production fit ({first + 1}–{test[1]}): poll {pc_all[0]} · stack {sc_all} · sigma {sig_a}/{sig_ae}")
    final, _ = chain(span, Pp)
    doc = {"model": "ncaaf-sim HOUSE MODEL v1.1 (points ratings + preseason poll prior + box-score efficiency stack)",
           "built": _now(), "params": Pp, "train_seasons": [train[0], train[1]], "test_seasons": [test[0], test[1]],
           "corpus": (f"ESPN finals {first}–{test[1]}, closing lines from ESPN core odds (DraftKings / ESPN BET / consensus); "
                      f"team boxes (FBS v FBS) {first}–{test[1]}; preseason AP poll {first}–{test[1] + 1}"),
           "report": rep,
           "v11": {"selection": V11["selected_on"], "v1_params": P1,
                   "train_fit": {"poll": pc_tr[0], "poll_rmse": pc_tr[1], "prior_only_rmse": pc_tr[2], "stack": sc_tr,
                                 "sigma": [sig, sig_e]},
                   "production_fit": {"poll": pc_all[0], "stack": sc_all, "sigma": [sig_a, sig_ae], "seasons": [first + 1, test[1]]},
                   "stack_order": ["points line"] + fe + [f"early·{m}" for m in fe],
                   "compare": cmp_, "loso": lo},
           "reading": ("Held-out seasons scored walk-forward with the v1.1 layers fit on the training seasons only: each week "
                       "predicted from games before it. v1.1 beats v1 modestly and consistently (leave-one-season-out: better "
                       "in most seasons, most in weeks 1–4); the closing market is still the better forecaster. The HOUSE "
                       "MODEL is advisory and never blended with it.")}
    if cal.get("committee"):
        doc["committee"] = cal["committee"]
    if write:
        with open(CAL_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
        write_priors(final, test[1] + 1, Pp)
        log(f"  wrote {CAL_PATH} (refit the committee proxy next: ncaaf_sim.py committee --write)")
    return doc


def write_priors(final, season, P):
    """The final Ratings of season-1 (the next season's prior source) -> references/priors_<season>.json."""
    p = os.path.join(REFS, f"priors_{season}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"for_season": season, "built": _now(), "fbs": final.fbs, "ratings": final.to_json()}, f, separators=(",", ":"))
    print(f"  wrote {p}")


def load_prior_ratings(season, P):
    """Ratings at the end of season-1 (packaged priors_<season>.json, else rebuilt from the corpus)."""
    p = os.path.join(REFS, f"priors_{season}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return Ratings.from_json(d["ratings"], d["fbs"], P)
    ss = [y for y in corpus_seasons() if y < season]
    if not ss:
        return None
    final, _ = chain(ss, P)
    return final


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ============================================================================ live season (through ncaaf-data-pull)
def _data():
    cand = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ncaaf-data-pull", "scripts")
    dirs = [cand] + sorted(glob.glob("/mnt/skills/*/ncaaf-data-pull/scripts")) + \
        sorted(glob.glob(os.path.expanduser("~/.claude/skills/synced/*/ncaaf-data-pull/scripts")))
    for d in dirs:
        if os.path.isdir(d):
            if d not in sys.path:
                sys.path.insert(0, d)
            import ncaaf_data as D
            return D
    sys.exit("[ncaaf-sim] sibling skill ncaaf-data-pull not installed (required)")


def live_boxes(season, events, fbs, workers=16):
    """Team boxes of this season's FBS v FBS finals: the packaged corpus file when the season is closed, else ESPN's core
    API (build_boxes.fetch_box, ≈100 KB a team-game), cached forever in NCAAF_CACHE (finals do not change; a failed
    fetch is retried on the next run). -> ({eid: {team id: box}}, fetched now, missing)."""
    sys.path.insert(0, HERE)
    import build_boxes as BB
    from concurrent.futures import ThreadPoolExecutor
    base = load_boxes(season) or {}
    cp = os.path.join(CACHE, f"boxes_live_{season}.json")
    try:
        with open(cp, encoding="utf-8") as f:
            have = json.load(f)
    except (OSError, ValueError):
        have = {}
    need = []
    for e in events:
        h, a = e["h"]["id"], e["a"]["id"]
        if not e["status"]["completed"] or h not in fbs or a not in fbs:
            continue
        for t in (h, a):
            if t not in (base.get(e["eid"]) or {}) and t not in (have.get(e["eid"]) or {}):
                need.append((e["eid"], t))
    got = 0
    if need:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(lambda j: BB.fetch_box(*j), need))
        for (eid, t), r in zip(need, res):
            if r:
                have.setdefault(eid, {})[t] = r
                got += 1
        os.makedirs(CACHE, exist_ok=True)
        with open(cp, "w", encoding="utf-8") as f:
            json.dump(have, f, separators=(",", ":"))
    out = {eid: {t: dict(zip(BB.COLS, v)) for t, v in tm.items()} for eid, tm in have.items()}
    for eid, tm in base.items():
        out.setdefault(eid, {}).update(tm)
    return out, got, len(need) - got


def live(season, events=None, reg=None, P=None, want_se=True, log=None):
    """This season's Ratings from every final so far (regular season and postseason), prior from last season (v1.1: moved
    by this season's preseason AP poll; the efficiency layers fitted from this season's team boxes). R.prior = the prior
    dict, R.prior_rating = {team: (offense, defense)} the HOUSE MODEL's preseason rating on the same scale as R.o / R.d,
    R.boxes = the boxes used, R.box_note = coverage."""
    D = _data()
    P = P or params()
    events = events if events is not None else D.season_events(season)
    reg = reg or D.registry(season, events)
    fbs = {t: v["conf"] for t, v in reg["teams"].items()}
    prev = load_prior_ratings(season, P)
    if P.get("poll"):
        try:
            ensure_poll(season)
        except Exception:  # noqa: BLE001 — no poll yet (or offline): the prior stays last season's
            pass
    pr = prior_from(prev, fbs, P, season=season)
    G = []
    wk = 0
    for e in events:
        if e["status"]["completed"] and e["h"]["score"] is not None and e["a"]["score"] is not None:
            G.append({"eid": e["eid"], "hid": e["h"]["id"], "aid": e["a"]["id"], "hs": e["h"]["score"], "as": e["a"]["score"],
                      "neutral": e["neutral"], "week": e["week"], "st": e["st"], "date": e.get("date")})
            if e["st"] == 2:
                wk = max(wk, e["week"] or 0)
    B, note = None, None
    if P.get("stack"):
        try:
            B, got, miss = live_boxes(season, events, fbs)
            nb = sum(1 for g in G if g["hid"] in fbs and g["aid"] in fbs)
            have = sum(1 for g in G if g["hid"] in fbs and g["aid"] in fbs and len(B.get(g["eid"]) or {}) >= 2)
            note = {"fbs_finals": nb, "with_boxes": have, "fetched_now": got, "missing": miss}
        except Exception as ex:  # noqa: BLE001 — offline: efficiency layers fall back to their priors
            B, note = {}, {"error": str(ex)[:200]}
        if log:
            log(f"  team boxes: {note}")
    R = fit(G, fbs, pr, P, season, wk, ref_week=wk + 1, want_se=want_se, boxes=B)
    R0 = fit([], fbs, pr, P, season, 0, ref_week=1, boxes={} if B is not None else None)
    R.prior, R.boxes, R.box_note = pr, B, note
    R.prior_rating = {t: (R0.o(t), R0.d(t)) for t in fbs}
    return R, G


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("ratings"); s.add_argument("--season", type=int); s.add_argument("--top", type=int, default=25)
    s = sp.add_parser("predict"); s.add_argument("away"); s.add_argument("home"); s.add_argument("--neutral", action="store_true")
    s.add_argument("--season", type=int)
    s = sp.add_parser("backtest"); s.add_argument("--seasons", default="2019-2025")
    s = sp.add_parser("calibrate"); s.add_argument("--train", default="2016-2023"); s.add_argument("--test", default="2024-2025")
    s.add_argument("--write", action="store_true")
    s = sp.add_parser("calibrate-v11"); s.add_argument("--train", default="2016-2023"); s.add_argument("--test", default="2024-2025")
    s.add_argument("--loso", action="store_true"); s.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.cmd == "calibrate-v11":
        tr = tuple(int(x) for x in a.train.split("-"))
        te = tuple(int(x) for x in a.test.split("-"))
        doc = calibrate_v11(tr, te, a.write, a.loso)
        print(json.dumps(doc["v11"]["compare"], indent=1))
        return
    if a.cmd == "calibrate":
        tr = tuple(int(x) for x in a.train.split("-"))
        te = tuple(int(x) for x in a.test.split("-"))
        doc = calibrate(tr, te, a.write)
        print(json.dumps({k: doc["report"][k] for k in ("train_all", "test_all")}, indent=1))
        print(json.dumps(doc["params"]))
        return
    if a.cmd == "backtest":
        lo, hi = (int(x) for x in a.seasons.split("-"))
        P = params()
        ss = [y for y in corpus_seasons() if y <= hi]
        _, pr = chain(ss, P, evaluate=set(range(lo, hi + 1)))
        for y in range(lo, hi + 1):
            print(y, json.dumps(score([r for r in pr if r["season"] == y], P)))
        print("all", json.dumps(score(pr, P)))
        return
    D = _data()
    import ncaaf_common as C
    season = getattr(a, "season", None) or C.season_of()
    R, G = live(season)
    reg = D.registry(season)
    T = reg["teams"]
    if a.cmd == "ratings":
        fb = sorted(T, key=lambda t: -R.net(t))
        print(f"[ncaaf ratings] HOUSE MODEL {season} through week {R.through} · {len(G)} finals · hfa {R.hfa:.2f} · "
              f"mu {R.mu:.1f} · FCS group {R.g_off + R.g_def:+.1f}")
        for i, t in enumerate(fb[:a.top], 1):
            print(f"  {i:>3}. {T[t]['abbr']:<6} net {R.net(t):+6.1f}  off {R.o(t):+5.1f}  def {R.d(t):+5.1f}  "
                  f"({R.n_games.get(t, 0)} g, ±{R.se.get(t, 0):.1f})")
        return
    if a.cmd == "predict":
        def find(k):
            k = k.upper()
            return next((t for t, v in T.items() if v["key"] == k or v["abbr"] == k), None)
        h, aw = find(a.home), find(a.away)
        if not h or not aw:
            sys.exit("unknown team")
        ln = R.line(h, aw, a.neutral)
        print(f"[ncaaf predict] HOUSE MODEL {T[aw]['abbr']} {'vs' if a.neutral else '@'} {T[h]['abbr']}: "
              f"{C.line_txt(-ln, T[h]['abbr'], T[aw]['abbr'])}, total {R.total(h, aw):.1f}, "
              f"P({T[h]['abbr']}) {C.pct1(R.p_home(h, aw, a.neutral))}")


if __name__ == "__main__":
    main()
