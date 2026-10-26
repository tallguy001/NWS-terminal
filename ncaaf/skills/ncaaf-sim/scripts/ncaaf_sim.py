#!/usr/bin/env python3
"""ncaaf_sim.py — the NCAAF HOUSE MODEL's season simulation: conference title games, the 12-team CFP, bowl eligibility.

    python3 ncaaf_sim.py season [--sims 10000] [--seed YYYYMMDD] [--json OUT]   this season from today (ncaaf-data-pull)
    python3 ncaaf_sim.py week [--week N]                                        a week's games: HOUSE MODEL vs DraftKings
    python3 ncaaf_sim.py committee [--fetch] [--write]                          fit + grade the committee proxy (2014–2025)

One simulated season (vectorised over N seasons, numpy):
  1. Each team's true strength is drawn around its HOUSE MODEL net rating (v1.1: points + efficiency stack) with the fit's own
     standard error; every remaining game's margin = strength(home) − strength(away) + the model's effective home field (none
     at a neutral site) + game noise, with the noise sized so a
     single game keeps the calibrated sigma (sqrt(sigma² − se_h² − se_a²), at least 10 points).
  2. Conference title games: the two best conference records meet (Sun Belt: the East and West division winners); a two-way
     tie at the cut goes to head-to-head, anything else to the simulated strength (each league's published tiebreakers are
     longer — an approximation, labelled). A title game ESPN already lists is played as listed. Played at a neutral site.
  3. The committee proxy ranks every FBS team: résumé (wins minus the wins an elite team — the k-th best rating — would expect
     against the same schedule) + b · strength/10 + c · conference champion; b, c, k fitted to the committee's final rankings
     2014–2025 (`committee`, graded by top-12 overlap).
  4. The field (2026-27 rules, references/season_2026_facts.json): champions of the ACC, Big Ten, Big 12 and SEC, the best
     champion of the American, C-USA, MAC, Mountain West, Pac-12 and Sun Belt, Notre Dame if top 12, then at-large by rank;
     straight seeding, an automatic qualifier outside the top 12 takes the lowest seed; byes to seeds 1–4; first round on
     the higher seed's campus, quarterfinals on, neutral.
  5. Counted: wins (regular season), bowl eligibility (6 wins, at most one FCS win), conference title game and title, CFP,
     bye, seed, each round, champion; and for each team's next game, the CFP / title-game / bowl odds with a win and a loss.
The per-game numbers on the hub come from the single-game model (no strength draw), so a season's odds run slightly flatter
than the game lines — the strength draw is the uncertainty of the rating itself, the same finding the NFL hub records.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ncaaf_model as M  # noqa: E402

np = M.np
REFS = M.REFS
CFP_PATH = os.path.join(REFS, "cfp_final.json")
P4 = ["SEC", "B1G", "B12", "ACC"]
G6 = ["AAC", "CUSA", "MAC", "MWC", "P12", "SBC"]
COMMITTEE_DEFAULT = {"b": 0.35, "c": 0.5, "k_elite": 12}


def _data():
    return M._data()


def committee_params():
    c = (M.load_cal().get("committee") or {}).get("params")
    return dict(COMMITTEE_DEFAULT, **(c or {}))


def _phi_vec(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def is_title_game(e_or_note, conf_h=None, conf_a=None):
    note = e_or_note if isinstance(e_or_note, str) or e_or_note is None else " ".join(e_or_note.get("notes") or [])
    return bool(note) and "championship" in note.lower() and conf_h is not None and conf_h == conf_a


# ============================================================================ committee proxy (history)
def fetch_cfp_history(lo=2014, hi=2025):
    _data()
    import ncaaf_common as C
    out = {}
    for y in range(lo, hi + 1):
        for w in (17, 16, 15):
            try:
                d = C.get_json(f"{C.CORE}/seasons/{y}/types/2/weeks/{w}/rankings/21", ttl=None)
            except RuntimeError:
                continue
            rk = d.get("ranks") or []
            if len(rk) >= 25:
                ids = [r["team"]["$ref"].split("/teams/")[-1].split("?")[0] for r in sorted(rk, key=lambda r: r["current"])]
                out[str(y)] = {"week": w, "date": d.get("date"), "headline": d.get("headline"), "ids": ids[:25]}
                break
    with open(CFP_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return out


def resume(G, fbs, R, k_elite, cutoff=None):
    """Per FBS team: wins, losses, fcs wins, E (elite team's expected wins vs the same schedule), conference champion flag."""
    nets = sorted((R.net(t) for t in fbs), reverse=True)
    Re = nets[min(len(nets), k_elite) - 1]
    sig = R.P["sigma"]
    out = {t: {"w": 0, "l": 0, "E": 0.0, "champ": 0, "fcsw": 0} for t in fbs}
    for g in G:
        if cutoff and g["date"] >= cutoff:
            continue
        if g["st"] != 2:
            continue
        h, a = g["hid"], g["aid"]
        for me, op, home in ((h, a, True), (a, h, False)):
            if me not in out:
                continue
            adv = 0.0 if g["neutral"] else (R.hfa if home else -R.hfa)
            out[me]["E"] += M.Phi((Re - R.net(op) + adv) / sig)
            won = (g["hs"] > g["as"]) == (me == h)
            out[me]["w" if won else "l"] += 1
            if won and op not in fbs:
                out[me]["fcsw"] += 1
        note = g.get("note") or ""
        if "championship" in note.lower() and h in fbs and a in fbs and fbs[h] == fbs[a]:
            out[h if g["hs"] > g["as"] else a]["champ"] = 1
    return out


def committee_fit(write=False, log=print):
    if not os.path.exists(CFP_PATH):
        fetch_cfp_history()
    with open(CFP_PATH, encoding="utf-8") as f:
        hist = json.load(f)
    P = M.params()
    seasons = sorted(int(y) for y in hist if M.load_corpus(int(y)))
    prev = None
    first = M.corpus_seasons()[0]
    data = {}
    for y in range(first, max(seasons) + 1):
        Cp = M.load_corpus(y)
        fbs = Cp["fbs"]
        B = (M.load_boxes(y) or {}) if P.get("stack") else None
        pr = M.prior_from(prev, fbs, P, season=y)
        if str(y) in hist:
            cut = (hist[str(y)].get("date") or "")[:16]
            if not cut:          # no date on the ranking (2014): the day after the last conference title game
                tg = [g["date"] for g in Cp["games"] if g["st"] == 2 and "championship" in (g.get("note") or "").lower()]
                last = max(tg) if tg else max(g["date"] for g in Cp["games"] if g["st"] == 2)
                cut = (dt.datetime.fromisoformat(last[:10]) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
            G = [g for g in Cp["games"] if g["st"] == 2 and g["date"] < cut]
            R = M.fit(G, fbs, pr, P, y, "ranking", boxes=B)
            data[y] = (G, fbs, R, cut)
        prev = M.fit(Cp["games"], fbs, pr, P, y, "final", boxes=B)
    best = None
    for k in (4, 6, 9, 12, 25):
        rs = {y: resume(*data[y][:3], k, data[y][3]) for y in seasons}
        for b in (0.0, 0.2, 0.35, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
            for c in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5):
                ov, sp = [], []
                for y in seasons:
                    G, fbs, R, _ = data[y]
                    sc = {t: (v["w"] - v["E"]) + b * R.net(t) / 10 + c * v["champ"] for t, v in rs[y].items()}
                    order = sorted(sc, key=lambda t: -sc[t])
                    truth = hist[str(y)]["ids"]
                    ov.append(len(set(order[:12]) & set(truth[:12])))
                    pos = {t: i for i, t in enumerate(order)}
                    d2 = sum((pos.get(t, 60) - i) ** 2 for i, t in enumerate(truth))
                    n = len(truth)
                    sp.append(1 - 6 * d2 / (n * (n * n - 1)))
                m = sum(ov) / len(ov) + sum(sp) / len(sp)
                if best is None or m > best[0]:
                    best = (m, {"b": b, "c": c, "k_elite": k}, ov, sp)
    m, prm, ov, sp = best
    rep = {"params": prm, "seasons": seasons, "top12_overlap": dict(zip(map(str, seasons), ov)),
           "top12_overlap_mean": round(sum(ov) / len(ov), 2), "spearman_top25_mean": round(sum(sp) / len(sp), 3),
           "reading": ("Fitted to the committee's final rankings (ESPN core API, ranking 21): of the committee's top 12, the "
                       f"proxy names {sum(ov) / len(ov):.1f} on average. The committee is people; the proxy is a formula.")}
    log(f"[committee] best {prm} · top-12 overlap mean {rep['top12_overlap_mean']} · Spearman {rep['spearman_top25_mean']} · "
        f"by season {rep['top12_overlap']}")
    if write:
        cal = M.load_cal()
        cal["committee"] = rep
        with open(M.CAL_PATH, "w", encoding="utf-8") as f:
            json.dump(cal, f, indent=1)
        log(f"  wrote committee block to {M.CAL_PATH}")
    return rep


# ============================================================================ the season
def season_sim(season, R, events, reg, n=10000, seed=None, log=None):
    log = log or (lambda s: None)
    t0 = time.time()
    P = R.P
    CP = committee_params()
    teams = reg["teams"]
    fbs = {t: v["conf"] for t, v in teams.items()}
    F = sorted(fbs)
    fi = {t: i for i, t in enumerate(F)}
    nf = len(F)
    rng = np.random.default_rng(seed if seed is not None else int(dt.date.today().strftime("%Y%m%d")))
    # ---- games: completed (fixed) and remaining (simulated), regular season only (+ listed title games)
    done, rem = [], []
    for e in events:
        if e["st"] != 2:
            continue
        nm = e["status"].get("name") or ""
        if "CANCEL" in nm or "POSTPONED" in nm:
            continue
        h, a = e["h"]["id"], e["a"]["id"]
        if h not in fbs and a not in fbs:
            continue
        tg = is_title_game(e, fbs.get(h), fbs.get(a))
        g = {"eid": e["eid"], "h": h, "a": a, "neutral": e["neutral"] or tg, "conf": bool(e["conf"]) and fbs.get(h) == fbs.get(a)
             and fbs.get(h) not in (None, "IND") and not tg, "title": fbs.get(h) if tg else None, "date": e["date"],
             "week": e["week"]}
        if e["status"]["completed"] and e["h"]["score"] is not None:
            g["hw"] = e["h"]["score"] > e["a"]["score"]
            done.append(g)
        else:
            rem.append(g)
    # ---- strengths per sim
    allids = sorted({g["h"] for g in done + rem} | {g["a"] for g in done + rem} | set(F))
    ai = {t: i for i, t in enumerate(allids)}
    net = np.array([R.net(t) for t in allids])
    se = np.array([(R.se.get(t) or (4.0 if t in fbs else 6.0)) for t in allids])
    S = net[None, :] + rng.standard_normal((n, len(allids))) * se[None, :]
    sig = P["sigma"]

    def play(hidx, aidx, neutral):
        """margins for a list of games (vectors of indices) -> (n, g) bool home wins."""
        hidx, aidx = np.asarray(hidx), np.asarray(aidx)
        neu = np.asarray(neutral, dtype=float)
        m = S[:, hidx] - S[:, aidx] + R.hfa * (1.0 - neu)[None, :]
        sg = np.sqrt(np.maximum(sig ** 2 - se[hidx] ** 2 - se[aidx] ** 2, 100.0))
        m = m + rng.standard_normal(m.shape) * sg[None, :]
        return m > 0
    reg_rem = [g for g in rem if not g["title"]]
    tit_rem = [g for g in rem if g["title"]]
    HW = play([ai[g["h"]] for g in reg_rem], [ai[g["a"]] for g in reg_rem], [g["neutral"] for g in reg_rem]) \
        if reg_rem else np.zeros((n, 0), bool)
    # ---- records
    W = np.zeros((n, nf)); L = np.zeros((n, nf)); CW = np.zeros((n, nf)); CL = np.zeros((n, nf)); FW = np.zeros((n, nf))
    cur = {t: dict(w=0, l=0, cw=0, cl=0, fcsw=0) for t in F}
    for g in done:
        if g["title"]:
            continue
        for me, op, won in ((g["h"], g["a"], g["hw"]), (g["a"], g["h"], not g["hw"])):
            if me not in fi:
                continue
            j = fi[me]
            if won:
                W[:, j] += 1; cur[me]["w"] += 1
                if op not in fbs:
                    FW[:, j] += 1; cur[me]["fcsw"] += 1
            else:
                L[:, j] += 1; cur[me]["l"] += 1
            if g["conf"]:
                if won:
                    CW[:, j] += 1; cur[me]["cw"] += 1
                else:
                    CL[:, j] += 1; cur[me]["cl"] += 1
    for k, g in enumerate(reg_rem):
        hw = HW[:, k]
        for me, op, won in ((g["h"], g["a"], hw), (g["a"], g["h"], ~hw)):
            if me not in fi:
                continue
            j = fi[me]
            W[:, j] += won; L[:, j] += ~won
            if op not in fbs:
                FW[:, j] += won
            if g["conf"]:
                CW[:, j] += won; CL[:, j] += ~won
    # head-to-head lookup among conference games: (a, b) -> per-sim bool "a beat b"
    h2h = {}
    for g in done:
        if g["conf"]:
            h2h[(g["h"], g["a"])] = np.full(n, g["hw"]); h2h[(g["a"], g["h"])] = np.full(n, not g["hw"])
    for k, g in enumerate(reg_rem):
        if g["conf"]:
            h2h[(g["h"], g["a"])] = HW[:, k]; h2h[(g["a"], g["h"])] = ~HW[:, k]
    # ---- conference title games
    champ = np.full((n, nf), False)
    ccg = np.full((n, nf), False)
    confs = reg["confs"]
    pct = np.where(CW + CL > 0, CW / np.maximum(CW + CL, 1), 0.0)
    Sf = S[:, [ai[t] for t in F]]
    listed = {g["title"]: g for g in tit_rem}
    listed_done = {g["title"]: g for g in done if g["title"]}
    TGP = {}                                                 # conf -> (idx_a, idx_b) arrays per sim (for stakes, report)

    def top_two(members, rows=None):
        idx = np.array([fi[t] for t in members])
        key1 = pct[:, idx]
        key2 = Sf[:, idx]
        order = np.lexsort((-key2, -key1), axis=-1)          # best first
        first = idx[order[:, 0]]
        second = idx[order[:, 1]] if len(idx) > 1 else first
        if len(idx) > 2:
            third = idx[order[:, 2]]
            tie = np.isclose(pct[np.arange(n), second], pct[np.arange(n), third]) & \
                ~np.isclose(pct[np.arange(n), first], pct[np.arange(n), second])
            for s in np.nonzero(tie)[0]:
                b, c = F[second[s]], F[third[s]]
                if (c, b) in h2h and h2h[(c, b)][s]:
                    second[s], third[s] = third[s], second[s]
            # a two-way tie for first between #1 and #2 needs no swap (both play)
        return first, second
    for ck, cf in confs.items():
        if ck == "IND":
            continue
        if ck in listed_done:
            g = listed_done[ck]
            jw, jl = (fi[g["h"]], fi[g["a"]]) if g["hw"] else (fi[g["a"]], fi[g["h"]])
            champ[:, jw] = True; ccg[:, jw] = True; ccg[:, jl] = True
            continue
        if ck in listed:
            g = listed[ck]
            a_, b_ = np.full(n, fi[g["h"]]), np.full(n, fi[g["a"]])
        elif cf.get("divs") and len(cf["divs"]) == 2:
            dv = list(cf["divs"].values())
            a_ = top_two(dv[0])[0]
            b_ = top_two(dv[1])[0]
        else:
            a_, b_ = top_two(cf["members"])
        ccg[np.arange(n), a_] = True
        ccg[np.arange(n), b_] = True
        Fa = np.array([ai[t] for t in F])
        sa, sb = S[np.arange(n), Fa[a_]], S[np.arange(n), Fa[b_]]
        sea, seb = se[Fa[a_]], se[Fa[b_]]
        m = sa - sb + rng.standard_normal(n) * np.sqrt(np.maximum(sig ** 2 - sea ** 2 - seb ** 2, 100.0))
        win = np.where(m > 0, a_, b_)
        champ[np.arange(n), win] = True
        TGP[ck] = (a_, b_)
    # ---- committee proxy
    nets_sorted = np.sort(net[[ai[t] for t in F]])[::-1]
    Re = nets_sorted[min(nf, int(CP["k_elite"])) - 1]
    E = np.zeros(nf)
    for g in done + reg_rem:
        for me, op, home in ((g["h"], g["a"], True), (g["a"], g["h"], False)):
            if me in fi:
                adv = 0.0 if g["neutral"] else (R.hfa if home else -R.hfa)
                E[fi[me]] += M.Phi((Re - net[ai[op]] + adv) / sig)
    # title game adds a game against the opponent (wins counted in W below)
    TW = np.zeros((n, nf))
    for ck, (a_, b_) in TGP.items():
        pass
    winners = champ & ccg
    losers = ccg & ~champ
    W2 = W + winners                                          # title-game result counts in the résumé
    L2 = L + losers
    Etg = np.zeros((n, nf))
    for ck, (a_, b_) in TGP.items():
        Fa = np.array([ai[t] for t in F])
        pa = 0.5 * (1 + np.vectorize(math.erf)((Re - net[Fa[b_]]) / sig / math.sqrt(2)))
        pb = 0.5 * (1 + np.vectorize(math.erf)((Re - net[Fa[a_]]) / sig / math.sqrt(2)))
        Etg[np.arange(n), a_] += pa
        Etg[np.arange(n), b_] += pb
    score = (W2 - (E[None, :] + Etg)) + CP["b"] * Sf / 10.0 + CP["c"] * champ
    # ---- the field
    order = np.argsort(-score, axis=1)
    rank = np.empty_like(order)
    rank[np.arange(n)[:, None], order] = np.arange(nf)[None, :]
    nd = fi.get(next((t for t in F if teams[t]["key"] == "ND"), None)) if any(teams[t]["key"] == "ND" for t in F) else None
    conf_of = np.array([P4.index(fbs[t]) if fbs[t] in P4 else (10 + G6.index(fbs[t]) if fbs[t] in G6 else 99) for t in F])
    inCFP = np.zeros((n, nf), bool)
    seedM = np.zeros((n, nf), np.int8)
    rounds = {k: np.zeros((n, nf), bool) for k in ("qf", "sf", "final", "champ")}
    Fa = np.array([ai[t] for t in F])
    for s in range(n):
        ch = np.nonzero(champ[s])[0]
        aq = [j for j in ch if conf_of[j] < 10]
        g6 = [j for j in ch if 10 <= conf_of[j] < 99]
        if g6:
            aq.append(min(g6, key=lambda j: rank[s, j]))
        top = list(order[s, :12])
        fld = list(top)
        for j in aq:
            if j not in fld:
                fld.append(j)
        protected = set(aq) | ({nd} if nd is not None and nd in top else set())
        while len(fld) > 12:
            drop = max((j for j in fld if j not in protected), key=lambda j: rank[s, j])
            fld.remove(drop)
        intop = sorted([j for j in fld if rank[s, j] < 12], key=lambda j: rank[s, j])
        outs = sorted([j for j in fld if rank[s, j] >= 12], key=lambda j: rank[s, j])
        seeds = intop + outs
        for k, j in enumerate(seeds):
            inCFP[s, j] = True
            seedM[s, j] = k + 1
        st = S[s, Fa]

        def g1(x, y, home):
            mm = st[x] - st[y] + (R.hfa if home else 0.0) + rng.standard_normal() * math.sqrt(max(sig ** 2 - se[Fa[x]] ** 2 - se[Fa[y]] ** 2, 100.0))
            return x if mm > 0 else y
        sd = {k + 1: j for k, j in enumerate(seeds)}
        r1 = {5: g1(sd[5], sd[12], True), 6: g1(sd[6], sd[11], True), 7: g1(sd[7], sd[10], True), 8: g1(sd[8], sd[9], True)}
        qf = [(sd[1], r1[8]), (sd[2], r1[7]), (sd[3], r1[6]), (sd[4], r1[5])]
        for x, y in qf:
            rounds["qf"][s, x] = True; rounds["qf"][s, y] = True
        q = [g1(x, y, False) for x, y in qf]
        for j in q:
            rounds["sf"][s, j] = True
        f1, f2 = g1(q[0], q[3], False), g1(q[1], q[2], False)
        rounds["final"][s, f1] = True; rounds["final"][s, f2] = True
        rounds["champ"][s, g1(f1, f2, False)] = True
    # ---- per-team summaries
    out = {}
    bowl = (W >= 6) & ((W - np.maximum(FW - 1, 0)) >= 6)
    for t in F:
        j = fi[t]
        w = W[:, j]
        q = np.percentile(w, [10, 50, 90])
        sd_ = seedM[:, j]
        out[t] = {"w": round(float(w.mean()), 3), "w10": int(q[0]), "w50": int(q[1]), "w90": int(q[2]),
                  "l": round(float(L[:, j].mean()), 3), "cw": round(float(CW[:, j].mean()), 3), "cl": round(float(CL[:, j].mean()), 3),
                  "p_bowl": float(bowl[:, j].mean()), "p_w8": float((w >= 8).mean()), "p_w10": float((w >= 10).mean()),
                  "p_unbeaten": float((L[:, j] == 0).mean()),
                  "p_ccg": float(ccg[:, j].mean()), "p_conf": float(champ[:, j].mean()), "p_cfp": float(inCFP[:, j].mean()),
                  "p_bye": float(((sd_ >= 1) & (sd_ <= 4)).mean()), "p_seed": [float((sd_ == k).mean()) for k in range(1, 13)],
                  "p_qf": float(rounds["qf"][:, j].mean()), "p_sf": float(rounds["sf"][:, j].mean()),
                  "p_final": float(rounds["final"][:, j].mean()), "p_champ": float(rounds["champ"][:, j].mean()),
                  "rank_med": int(np.median(rank[:, j]) + 1), "cur": cur[t], "E": round(float(E[j]), 3),
                  "w_dist": [float((w == k).mean()) for k in range(0, 16)]}
    # stakes: each team's next remaining game
    nxt = {}
    for k, g in enumerate(sorted(enumerate(reg_rem), key=lambda kg: kg[1]["date"] or "")):
        idx, gg = g
        for me in (gg["h"], gg["a"]):
            if me in fi and me not in nxt:
                nxt[me] = (idx, gg)
    for t, (idx, gg) in nxt.items():
        j = fi[t]
        won = HW[:, idx] if gg["h"] == t else ~HW[:, idx]
        nw, nl = int(won.sum()), int((~won).sum())

        def cond(arr):
            return (float(arr[won].mean()) if nw else None, float(arr[~won].mean()) if nl else None)
        out[t]["stakes"] = {"eid": gg["eid"], "n_w": nw, "n_l": nl, "cfp": cond(inCFP[:, j]), "ccg": cond(ccg[:, j]),
                            "bowl": cond(bowl[:, j]), "conf": cond(champ[:, j])}
    conf_sum = {ck: {"p_ccg": round(sum(out[t]["p_ccg"] for t in cf["members"]), 4),
                     "p_conf": round(sum(out[t]["p_conf"] for t in cf["members"]), 4)} for ck, cf in confs.items()}
    meta = {"sims": n, "seed": int(seed) if seed is not None else int(dt.date.today().strftime("%Y%m%d")),
            "seconds": round(time.time() - t0, 1), "done": len(done), "remaining": len(reg_rem), "title_listed": sorted(listed),
            "title_done": sorted(listed_done), "elite_rating": round(float(Re), 2), "committee": CP,
            "sum_cfp": round(sum(v["p_cfp"] for v in out.values()), 3), "sum_champ": round(sum(v["p_champ"] for v in out.values()), 4),
            "sum_conf": conf_sum}
    log(f"[ncaaf_sim] {n} seasons in {meta['seconds']} s · {len(done)} finals + {len(reg_rem)} to play · CFP sum {meta['sum_cfp']} · "
        f"title sum {meta['sum_champ']}")
    return {"teams": out, "meta": meta}


def today_picture(R, events, reg):
    """'If the season ended today' by the committee proxy: current records, current conference leaders as champions."""
    CP = committee_params()
    teams = reg["teams"]
    fbs = {t: v["conf"] for t, v in teams.items()}
    G = []
    for e in events:
        if e["st"] == 2 and e["status"]["completed"] and e["h"]["score"] is not None:
            G.append({"hid": e["h"]["id"], "aid": e["a"]["id"], "hs": e["h"]["score"], "as": e["a"]["score"],
                      "neutral": e["neutral"], "st": 2, "date": e["date"], "note": " ".join(e.get("notes") or [])})
    rs = resume(G, fbs, R, int(CP["k_elite"]))
    # conference leaders
    cw = {t: [0, 0] for t in fbs}
    for e in events:
        if e["st"] == 2 and e["status"]["completed"] and e["conf"] and e["h"]["score"] is not None:
            h, a = e["h"]["id"], e["a"]["id"]
            if fbs.get(h) and fbs.get(h) == fbs.get(a):
                hw = e["h"]["score"] > e["a"]["score"]
                cw[h][0 if hw else 1] += 1
                cw[a][1 if hw else 0] += 1
    leaders = {}
    for ck, cf in reg["confs"].items():
        if ck == "IND":
            continue
        best = max(cf["members"], key=lambda t: ((cw[t][0] / max(1, sum(cw[t]))) if sum(cw[t]) else 0, R.net(t)))
        leaders[ck] = best
    sc = {t: (v["w"] - v["E"]) + CP["b"] * R.net(t) / 10 + CP["c"] * (1 if leaders.get(fbs[t]) == t else 0) for t, v in rs.items()}
    order = sorted(sc, key=lambda t: -sc[t])
    rank = {t: i for i, t in enumerate(order)}
    aq = [leaders[c] for c in P4 if c in leaders]
    g6 = [leaders[c] for c in G6 if c in leaders]
    if g6:
        aq.append(min(g6, key=lambda t: rank[t]))
    nd = next((t for t in fbs if teams[t]["key"] == "ND"), None)
    fld = list(order[:12])
    for t in aq:
        if t not in fld:
            fld.append(t)
    protected = set(aq) | ({nd} if nd in order[:12] else set())
    while len(fld) > 12:
        fld.remove(max((t for t in fld if t not in protected), key=lambda t: rank[t]))
    seeds = sorted([t for t in fld if rank[t] < 12], key=lambda t: rank[t]) + sorted([t for t in fld if rank[t] >= 12], key=lambda t: rank[t])
    return {"seeds": seeds, "rank": order[:25], "score": {t: round(sc[t], 3) for t in order[:40]}, "leaders": leaders,
            "aq": aq, "resume": {t: {"w": v["w"], "l": v["l"], "E": round(v["E"], 3)} for t, v in rs.items()}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("season"); s.add_argument("--sims", type=int, default=10000); s.add_argument("--seed", type=int)
    s.add_argument("--json"); s.add_argument("--season", type=int)
    s = sp.add_parser("week"); s.add_argument("--week", type=int); s.add_argument("--season", type=int)
    s = sp.add_parser("committee"); s.add_argument("--fetch", action="store_true"); s.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.cmd == "committee":
        if a.fetch or not os.path.exists(CFP_PATH):
            h = fetch_cfp_history()
            print(f"[committee] final rankings for {len(h)} seasons -> {CFP_PATH}")
        committee_fit(a.write)
        return
    D = _data()
    import ncaaf_common as C
    season = a.season or C.season_of()
    evs = D.season_events(season)
    reg = D.registry(season, evs)
    R, G = M.live(season, evs, reg)
    T = reg["teams"]
    if a.cmd == "week":
        cw = D.current_week(season)
        wk = a.week or cw["week"]
        for e in [x for x in evs if x["st"] == 2 and x["week"] == wk]:
            h, aw = e["h"], e["a"]
            ln = R.line(h["id"], aw["id"], e["neutral"])
            o = e.get("odds") or {}
            mk = C.line_txt(o.get("spread"), h["abbr"], aw["abbr"]) if o.get("spread") is not None else "—"
            print(f"  {aw['abbr']:>6} {'vs' if e['neutral'] else '@'} {h['abbr']:<6} HOUSE {C.line_txt(-ln, h['abbr'], aw['abbr']):<12} "
                  f"P({h['abbr']}) {C.pct1(R.p_home(h['id'], aw['id'], e['neutral'], wk)):>6} · DraftKings {mk}")
        return
    res = season_sim(season, R, evs, reg, n=a.sims, seed=a.seed, log=print)
    pic = today_picture(R, evs, reg)
    res["today"] = pic
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f)
    top = sorted(res["teams"].items(), key=lambda kv: -kv[1]["p_cfp"])[:25]
    print(f"{'team':<6} {'rec':>5} {'projW':>6} {'bowl':>6} {'CCG':>6} {'conf':>6} {'CFP':>6} {'bye':>6} {'title':>6}")
    for t, v in top:
        c = v["cur"]
        print(f"{T[t]['abbr']:<6} {c['w']:>2}-{c['l']:<2} {v['w']:>6.2f} {C.pct0(v['p_bowl']):>6} {C.pct0(v['p_ccg']):>6} "
              f"{C.pct0(v['p_conf']):>6} {C.pct0(v['p_cfp']):>6} {C.pct0(v['p_bye']):>6} {C.pct1(v['p_champ']):>6}")
    print("today (proxy):", " ".join(f"{i + 1}.{T[t]['abbr']}" for i, t in enumerate(pic["seeds"])))
    print(json.dumps(res["meta"]["sum_conf"]))


if __name__ == "__main__":
    main()
