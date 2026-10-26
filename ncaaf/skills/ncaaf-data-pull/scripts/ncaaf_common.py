#!/usr/bin/env python3
"""ncaaf_common — shared plumbing for the NCAAF suite (stdlib only): cached HTTP, Central time, formatting, sibling skills.

The college-football port of nfl-hub/hub_common.py and nhl-data-pull/nhl_common.py: same constants (true minus, en dash,
em dash, middle dot), same half-up rounding, same sibling-skill resolution (same parent first, then the install globs
/mnt/skills/*/<skill>/scripts and ~/.claude/skills/synced/*/<skill>/scripts).

Cache: $NCAAF_CACHE (default /tmp/ncaaf_cache). Every GET is keyed by its URL; `ttl` seconds decides reuse (None = keep
forever: finals and closed seasons never change). A failed GET falls back to a stale copy when one exists and says so
(`stale_hits`), never silently.

Python 3.11 safe: no backslashes inside f-string braces.
"""
import datetime as dt
import glob
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True   # importing sibling skills must not write __pycache__ into them (read-only contract)
HERE = os.path.dirname(os.path.abspath(__file__))
MINUS = "−"
EN = "–"
DASH = "—"
DOT = "·"
NBSP = " "

CACHE = os.environ.get("NCAAF_CACHE", "/tmp/ncaaf_cache")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
SITE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
SITE2 = "https://site.api.espn.com/apis/v2/sports/football/college-football"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
FBS_GROUP = 80

STATS = {"gets": 0, "hits": 0, "stale_hits": 0, "fails": 0, "bytes": 0}
_LAST = {}


# ============================================================================ HTTP + cache
def _cpath(url):
    h = hashlib.sha1(url.encode()).hexdigest()
    return os.path.join(CACHE, h[:2], h + ".json")


def get_json(url, ttl=600, pace=0.0, host_key=None, retries=3, timeout=30):
    """GET url as JSON with a file cache. ttl=None keeps forever; ttl=0 always refetches (the cache still backs a failure).
    pace: minimum seconds between two GETs to the same host_key (Kalshi asks for spacing)."""
    p = _cpath(url)
    if os.path.exists(p) and ttl != 0:
        age = time.time() - os.path.getmtime(p)
        if ttl is None or age < ttl:
            try:
                with open(p, encoding="utf-8") as f:
                    STATS["hits"] += 1
                    return json.load(f)
            except (OSError, ValueError):
                pass
    err = None
    for k in range(retries):
        if pace and host_key:
            wait = _LAST.get(host_key, 0) + pace - time.time()
            if wait > 0:
                time.sleep(wait)
            _LAST[host_key] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            STATS["gets"] += 1
            STATS["bytes"] += len(raw)
            data = json.loads(raw.decode("utf-8"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
            os.replace(tmp, p)
            return data
        except urllib.error.HTTPError as e:
            err = e
            if e.code in (400, 401, 403, 404):
                break
            time.sleep(min(8, 1.5 * (2 ** k)))
        except (urllib.error.URLError, TimeoutError, ValueError, ConnectionError, OSError) as e:
            err = e
            time.sleep(min(8, 1.5 * (2 ** k)))
    STATS["fails"] += 1
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                STATS["stale_hits"] += 1
                print(f"[ncaaf] stale cache used for {url} ({type(err).__name__}: {err})", file=sys.stderr)
                return json.load(f)
        except (OSError, ValueError):
            pass
    raise RuntimeError(f"GET failed: {url} ({type(err).__name__}: {err})")


def pmap(fn, items, workers=8):
    """Thread-pool map that keeps order; exceptions come back as the exception object (caller decides)."""
    from concurrent.futures import ThreadPoolExecutor
    items = list(items)
    if not items:
        return []

    def safe(x):
        try:
            return fn(x)
        except Exception as e:  # noqa: BLE001
            return e
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as ex:
        return list(ex.map(safe, items))


def stats_line():
    return (f"{STATS['gets']} GETs ({STATS['bytes'] / 1e6:.1f} MB), {STATS['hits']} cache hits, "
            f"{STATS['stale_hits']} stale, {STATS['fails']} failed")


# ============================================================================ time
try:
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
    ET = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001
    CT = ET = None


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def parse_iso(s):
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    if len(s) == 22 and s[-6] in "+-" and s[10] == "T":     # 2026-10-27T23:00+00:00 (no seconds)
        s = s[:16] + ":00" + s[16:]
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def to_ct(d):
    if d is None:
        return None
    return d.astimezone(CT) if CT else d - dt.timedelta(hours=5)


def ct_time(d):
    """'7:30 PM' (Central)."""
    c = to_ct(d)
    return c.strftime("%I:%M %p").lstrip("0") if c else DASH


def ct_day(d, year=False):
    """'Sat Oct 31' (Central)."""
    c = to_ct(d)
    if not c:
        return DASH
    s = c.strftime("%a %b ") + str(c.day)
    return s + (f", {c.year}" if year else "")


def utc_hm(d):
    return d.astimezone(dt.timezone.utc).strftime("%H:%M") if d else DASH


def stamp_ct(d=None):
    """'Mon Oct 26, 2026 10:14 AM CT'."""
    c = to_ct(d or utcnow())
    return c.strftime("%a %b ") + str(c.day) + c.strftime(", %Y ") + c.strftime("%I:%M %p").lstrip("0") + " CT"


def season_of(d=None):
    """College football season label = the year it kicks off (Aug–Jan; a January date belongs to the prior year)."""
    c = to_ct(d or utcnow())
    return c.year if c.month >= 7 else c.year - 1


# ============================================================================ formatting (half up, true minus)
def half_up(x, nd, scale=1):
    from decimal import Decimal, ROUND_HALF_UP
    d = (Decimal(repr(float(x))) * scale).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    return abs(d) if d == 0 else d


def fmt(x, nd=1):
    if x is None:
        return DASH
    return format(half_up(x, nd), "f").replace("-", MINUS)


def signed(x, nd=1):
    if x is None:
        return DASH
    v = half_up(x, nd)
    if v == 0:
        return format(abs(v), "f")
    return ("+" if v > 0 else MINUS) + format(abs(v), "f")


def pct1(p):
    if p is None:
        return DASH
    v = float(p) * 100
    if 0 < v < 0.05:
        return "<0.1%"
    if 99.95 < v < 100:
        return ">99.9%"
    return format(half_up(v, 1), "f") + "%"


def pct0(p):
    if p is None:
        return DASH
    v = float(p) * 100
    if 0 < v < 0.5:
        return "<1%"
    if 99.5 < v < 100:
        return ">99%"
    return format(half_up(v, 0), "f") + "%"


def ordn(n):
    if n is None:
        return DASH
    n = int(n)
    sfx = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{sfx}"


def rec(w, l):
    if w is None or l is None:
        return DASH
    return f"{w}{EN}{l}"


def line_txt(spread_home, home, away, nd=1):
    """Home-perspective spread (negative = home favored) -> 'OSU −7.5' / 'Pick'."""
    if spread_home is None:
        return DASH
    v = float(spread_home)
    if abs(v) < 0.05:
        return "Pick"
    fav = home if v < 0 else away
    return f"{fav} {MINUS}{format(half_up(abs(v), nd), 'f')}"


def ml_txt(ml):
    if ml is None:
        return DASH
    v = int(round(float(ml)))
    return ("+" if v > 0 else MINUS) + str(abs(v))


def ml_prob(ml):
    """American moneyline -> implied probability (with vig)."""
    if ml is None:
        return None
    v = float(ml)
    if v == 0:
        return None
    return 100.0 / (v + 100.0) if v > 0 else -v / (-v + 100.0)


def novig(ml_home, ml_away):
    ph, pa = ml_prob(ml_home), ml_prob(ml_away)
    if ph is None or pa is None or ph + pa <= 0:
        return None
    return ph / (ph + pa)


# ============================================================================ sibling skills
def skill_dir(skill):
    """Sibling skill's scripts dir: same parent first, then the install globs."""
    cand = os.path.join(os.path.dirname(os.path.dirname(HERE)), skill, "scripts")
    if os.path.isdir(cand):
        return cand
    for g in (f"/mnt/skills/*/{skill}/scripts", os.path.expanduser(f"~/.claude/skills/synced/*/{skill}/scripts")):
        hits = sorted(glob.glob(g))
        if hits:
            return hits[0]
    return None


def need(skill, who="ncaaf"):
    d = skill_dir(skill)
    if not d:
        sys.exit(f"[{who}] sibling skill {skill} not installed (required)")
    if d not in sys.path:
        sys.path.insert(0, d)
    return d


def refs_dir(skill):
    d = skill_dir(skill)
    return os.path.join(os.path.dirname(d), "references") if d else None
