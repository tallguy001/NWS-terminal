#!/usr/bin/env python3
"""ncaaf_model.py — the NCAAF HOUSE MODEL: offense / defense points ratings for every FBS team, game lines and win chances.

    python3 ncaaf_model.py ratings [--season Y] [--top 25]         this season's ratings from the live finals (ncaaf-data-pull)
    python3 ncaaf_model.py predict AWAY HOME [--neutral]           one game: HOUSE MODEL line, total, win chance
    python3 ncaaf_model.py backtest [--seasons 2019-2025]          walk-forward against the closing market (calibration.json params)
    python3 ncaaf_model.py calibrate [--train 2016-2023] [--test 2024-2025] [--write]
                                                                   grid search on the training seasons, held-out report, writes
                                                                   references/calibration.json and references/priors_<Y+1>.json

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
               sigma=16.0, sigma_early=17.5, early_weeks=4, mu0=28.0, new_team=-3.0)
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


# ============================================================================ the fit
class Ratings:
    """A fitted state: off/def per team id, mu, the FCS group effects, hfa, sigma; predicts any pairing."""

    def __init__(self, off, dfn, mu, g_off, g_def, fbs, P, n_games=None, season=None, through=None, se=None):
        self.off, self.dfn, self.mu = off, dfn, mu
        self.g_off, self.g_def = g_off, g_def
        self.fbs, self.P = fbs, P
        self.n_games = n_games or {}
        self.season, self.through = season, through
        self.se = se or {}

    def o(self, t):
        return self.off.get(t, self.g_off)

    def d(self, t):
        return self.dfn.get(t, self.g_def)

    def net(self, t):
        return self.o(t) + self.d(t)

    def line(self, h, a, neutral=False):
        """Expected home margin."""
        return self.net(h) - self.net(a) + (0.0 if neutral else self.P["hfa"])

    def total(self, h, a):
        return 2 * self.mu + self.o(h) + self.o(a) - self.d(h) - self.d(a)

    def sigma(self, week=None, st=2):
        if st == 2 and week is not None and week <= self.P.get("early_weeks", 4):
            return self.P.get("sigma_early", self.P["sigma"])
        return self.P["sigma"]

    def p_home(self, h, a, neutral=False, week=None, st=2):
        return Phi(self.line(h, a, neutral) / self.sigma(week, st))

    def to_json(self):
        return {"season": self.season, "through": self.through, "mu": round(self.mu, 4), "g_off": round(self.g_off, 4),
                "g_def": round(self.g_def, 4), "hfa": self.P["hfa"],
                "teams": {t: [round(self.off[t], 4), round(self.dfn[t], 4), self.n_games.get(t, 0), round(self.se.get(t, 0.0), 4)]
                          for t in self.off}}

    @classmethod
    def from_json(cls, j, fbs, P):
        off = {t: v[0] for t, v in j["teams"].items()}
        dfn = {t: v[1] for t, v in j["teams"].items()}
        ng = {t: v[2] for t, v in j["teams"].items()}
        se = {t: (v[3] if len(v) > 3 else 0.0) for t, v in j["teams"].items()}
        return cls(off, dfn, j["mu"], j["g_off"], j["g_def"], fbs, P, ng, j.get("season"), j.get("through"), se)


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


def fit(games, fbs, prior, P, season=None, through=None, ref_week=None, want_se=False):
    """games: dicts with hid, aid, hs, as, neutral, week, st. fbs: {id: conf} for the season.
    prior: {"teams": {id: (po, pd)}, "g_off": x, "g_def": y, "mu": m, "fcs_dev": {id: (o, d)}}."""
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
    return Ratings(off, dfn, mu, g_off, g_def, fbs, P, ng, season, through, se)


def prior_from(prev, fbs_now, P):
    """The next season's prior from last season's final Ratings (or None = flat)."""
    if prev is None:
        return {"teams": {}, "mu": P.get("mu0", 28.0), "g_off": -9.0, "g_def": -9.0, "new_o": -3.0, "new_d": -3.0}
    rho = P["rho"]
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
            teams[t] = (rho * prev.off[t] + (1 - rho) * mo, rho * prev.dfn[t] + (1 - rho) * md)
        else:
            teams[t] = (mo + nt / 2, md + nt / 2)
    dev = {}
    for t in prev.off:
        if t not in prev.fbs and t not in fbs_now:
            dev[t] = (rho * (prev.off[t] - prev.g_off), rho * (prev.dfn[t] - prev.g_def))
    return {"teams": teams, "mu": prev.mu, "g_off": prev.g_off, "g_def": prev.g_def, "fcs_dev": dev}


# ============================================================================ walk-forward
def chain(seasons, P, evaluate=None, log=None):
    """Fit season by season (each season's prior = the previous final). evaluate: set of seasons to score walk-forward.
    -> (final Ratings of the last season, [prediction rows])."""
    prev = None
    preds = []
    for y in seasons:
        C_ = load_corpus(y)
        if C_ is None:
            continue
        fbs = C_["fbs"]
        G = C_["games"]
        pr = prior_from(prev, fbs, P)
        if evaluate and y in evaluate:
            weeks = sorted({g["week"] for g in G if g["st"] == 2})
            for w in weeks:
                train = [g for g in G if g["st"] == 2 and g["week"] < w]
                R = fit(train, fbs, pr, P, y, w - 1, ref_week=w)
                for g in G:
                    if g["st"] == 2 and g["week"] == w:
                        preds.append(_pred_row(R, g, y, fbs))
            train = [g for g in G if g["st"] == 2]
            R = fit(train, fbs, pr, P, y, "reg", ref_week=max(weeks) + 1)
            for g in G:
                if g["st"] == 3:
                    preds.append(_pred_row(R, g, y, fbs))
        prev = fit(G, fbs, pr, P, y, "final", ref_week=None)
        if log:
            log(f"  {y}: {len(G)} games")
    return prev, preds


def _pred_row(R, g, y, fbs):
    h, a = g["hid"], g["aid"]
    line = R.line(h, a, bool(g["neutral"]))
    return {"season": y, "st": g["st"], "week": g["week"], "eid": g["eid"], "fbs2": (h in fbs and a in fbs),
            "line": line, "total": R.total(h, a), "margin": g["hs"] - g["as"], "pts": g["hs"] + g["as"],
            "spread": g.get("spread"), "mtotal": g.get("total"), "ml_h": g.get("ml_h"), "ml_a": g.get("ml_a")}


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


def live(season, events=None, reg=None, P=None, want_se=True):
    """This season's Ratings from every final so far (regular season and postseason), prior from last season."""
    D = _data()
    P = P or params()
    events = events if events is not None else D.season_events(season)
    reg = reg or D.registry(season, events)
    fbs = {t: v["conf"] for t, v in reg["teams"].items()}
    prev = load_prior_ratings(season, P)
    pr = prior_from(prev, fbs, P)
    G = []
    wk = 0
    for e in events:
        if e["status"]["completed"] and e["h"]["score"] is not None and e["a"]["score"] is not None:
            G.append({"hid": e["h"]["id"], "aid": e["a"]["id"], "hs": e["h"]["score"], "as": e["a"]["score"],
                      "neutral": e["neutral"], "week": e["week"], "st": e["st"]})
            if e["st"] == 2:
                wk = max(wk, e["week"] or 0)
    R = fit(G, fbs, pr, P, season, wk, ref_week=wk + 1, want_se=want_se)
    R.prior = pr
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
    a = ap.parse_args()
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
        print(f"[ncaaf ratings] HOUSE MODEL {season} through week {R.through} · {len(G)} finals · hfa {R.P['hfa']} · "
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
