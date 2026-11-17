/* NWS Terminal edge worker (v3.62.0)
   - serves the app shell from static assets with security + cache headers
   - /p/<kind>/...   same-origin read-only proxy for NOAA hosts without CORS
   - /p/gs/...       GribStream POST proxy (keeps the token off third parties)
   - /api/normals    1991-2020 normals + records, computed once per point and cached
   - /api/cams       Windy Webcams API v3 near a point (key stays a worker secret)
   - /api/config     what the server can do for the client
   - /api/health     liveness for uptime checks */

const VERSION = '3.62.0';

const ORIGINS = {
  spc: 'https://www.spc.noaa.gov',
  cpc: 'https://www.cpc.ncep.noaa.gov',
  wpc: 'https://www.wpc.ncep.noaa.gov',
  awc: 'https://aviationweather.gov',
  // Regional map layers: NWS point forecasts (no CORS), the rainfall analysis image
  // (same-origin so the map can be saved as a picture), Kalshi public market data.
  ndfd: 'https://digital.weather.gov',
  nwsmap: 'https://mapservices.weather.noaa.gov',
  kalshi: 'https://api.elections.kalshi.com',
  nowcoast: 'https://nowcoast.noaa.gov',
  opengeo: 'https://opengeo.ncep.noaa.gov',
  // Nominatim 403s without a User-Agent, and browsers refuse to set one.
  geo: 'https://nominatim.openstreetmap.org',
  // CoCoRaHS volunteer rain and snow reports (v3.62.0): its public daily export, one state and one day at a time.
  cocorahs: 'https://data.cocorahs.org',
};
const GS_ORIGIN = 'https://gribstream.com';
const UA = 'NWSTerminal/3.0 (NWS Terminal edge)';
const UPSTREAM_TIMEOUT_MS = 20000;

/* Content Security Policy for the document. Inline event handlers are still
   used throughout the markup, so script-src keeps 'unsafe-inline'; scripts can
   only be loaded from this origin and cdnjs (Leaflet, Chart.js). */
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: blob: https:",
  "connect-src 'self' https: wss:",
  // Windy's map embed (embed.windy.com) and webcam player (webcams.windy.com).
  "frame-src https://*.windy.com",
  "worker-src 'self'",
  "manifest-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
  // No frame-ancestors and no X-Frame-Options: v2.1.1 removed framing limits
  // because they blank the page inside embedded browsers.
].join('; ');

function cacheFor(pathname) {
  if (/\.(png|gif|jpg|jpeg|webp)$/i.test(pathname)) return 600;
  if (pathname.includes('/md/') || pathname.includes('/watch/')) return 120;
  if (pathname.startsWith('/search')) return 86400;
  if (pathname.startsWith('/trade-api/')) return 30;      // market prices
  if (pathname.endsWith('/legend')) return 86400;
  if (pathname.endsWith('/ImageServer') || pathname.startsWith('/geoserver/')) return 120;   // newest-frame times must stay fresh
  return 300;
}

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'X-Content-Type-Options': 'nosniff', ...extra },
  });
}

async function proxy(kind, rest, request) {
  const base = ORIGINS[kind];
  if (!base) return new Response('Unknown proxy target', { status: 404 });
  if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('Method not allowed', { status: 405 });
  // The newer upstreams are opened only as far as the app uses them.
  if (kind === 'kalshi' && !/^trade-api\/v2\/markets$/.test(rest)) return new Response('Unsupported path', { status: 404 });
  if (kind === 'ndfd' && rest !== 'xml/sample_products/browser_interface/ndfdXMLclient.php') return new Response('Unsupported path', { status: 404 });
  if (kind === 'nwsmap' && !/^raster\/rest\/services\/obs\/rfc_qpe\/MapServer\/(export|legend)$/.test(rest) &&
      !/^vector\/rest\/services\/(outlooks|precip)\/[A-Za-z0-9_]+\/MapServer\/\d+\/query$/.test(rest) &&
      !/^vector\/rest\/services\/(outlooks\/wpc_wssi|outlooks\/wpc_wssi_p|precip\/wpc_prob_winter_precip)\/MapServer\/(export|legend|identify)$/.test(rest) &&
      !/^eventdriven\/rest\/services\/water\/riv_gauges\/MapServer\/(0|15)\/query$/.test(rest) &&
      !/^eventdriven\/rest\/services\/WWA\/watch_warn_adv\/MapServer\/0\/query$/.test(rest) &&
      !/^raster\/rest\/services\/air_quality\/ndgd_smoke_sfc_1hr_avg_time\/ImageServer\/(exportImage|legend)$/.test(rest) &&
      !/^experimental\/rest\/services\/NWS_HeatRisk\/ImageServer\/(exportImage|legend)$/.test(rest) &&
      !/^raster\/rest\/services\/snow\/NOHRSC_Snow_Analysis\/MapServer\/(export|legend)$/.test(rest) &&
      !/^vector\/rest\/services\/obs\/usnic_greatlakes_ice_chart\/MapServer\/(export|legend)$/.test(rest) &&
      !/^eventdriven\/rest\/services\/radar\/radar_base_reflectivity_time\/ImageServer(\/exportImage)?$/.test(rest)) return new Response('Unsupported path', { status: 404 });
  if (kind === 'nowcoast' && rest !== 'geoserver/satellite/wms' && rest !== 'geoserver/observations/lightning_detection/ows') return new Response('Unsupported path', { status: 404 });
  if (kind === 'opengeo' && !/^geoserver\/[a-z]{4}\/ows$/.test(rest)) return new Response('Unsupported path', { status: 404 });
  if (kind === 'cocorahs' && rest !== 'export/exportreports.aspx') return new Response('Unsupported path', { status: 404 });
  const upstream = new URL(base + '/' + rest);
  // The path is appended to a fixed origin; refuse anything that resolved elsewhere.
  if (upstream.origin !== base) return new Response('Bad proxy path', { status: 400 });
  upstream.search = new URL(request.url).search;
  const ttl = cacheFor(upstream.pathname);
  const ask = { method: request.method, headers: { 'User-Agent': UA, Accept: request.headers.get('Accept') || '*/*' } };
  let res = await fetch(upstream.toString(), { ...ask, cf: { cacheTtl: ttl, cacheEverything: true }, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
  /* Cloudflare may hand back a copy that has outlived its time: marked STALE when the source did not answer the refresh, UPDATING
     while a refresh is under way. For weather that is an old map shown as the current one (v3.42.1: station reports hours old on
     a slow morning). Such a copy is asked for again past the cache, and the old one is used only if that fails. */
  const edge = (res.headers.get('CF-Cache-Status') || '').toUpperCase(), age = +res.headers.get('Age') || 0;
  let served = edge ? edge + (age ? ' ' + age + 's' : '') : '';
  if (res.ok && (edge === 'STALE' || edge === 'UPDATING' || age > ttl + 60)) {
    try {
      const again = await fetch(upstream.toString(), { ...ask, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
      if (again.ok) { res = again; served += ' -> asked again'; }
    } catch (e) { served += ' -> second ask failed'; }
  }
  const headers = new Headers();
  for (const h of ['Content-Type', 'Last-Modified', 'ETag']) {
    const v = res.headers.get(h);
    if (v) headers.set(h, v);
  }
  headers.set('Access-Control-Allow-Origin', '*');
  // Errors are never cached: a 404 during an SPC issuance window must not stick for 10 minutes.
  headers.set('Cache-Control', res.ok ? `public, max-age=${ttl}, stale-if-error=3600` : 'no-store');
  headers.set('X-Proxied-From', upstream.origin);
  if (served) headers.set('X-Edge-Copy', served);
  headers.set('X-Content-Type-Options', 'nosniff');
  return new Response(res.body, { status: res.status, headers });
}

function isSameOrigin(request) {
  const site = request.headers.get('Sec-Fetch-Site');
  if (site) return site === 'same-origin';
  const origin = request.headers.get('Origin');
  return !!origin && origin === new URL(request.url).origin;
}

/* ---- keys held as Cloudflare secrets (v3.14.0) ----
   GS_TOKEN, ANTHROPIC_API_KEY, WETHR_API_KEY, WINDY_WEBCAMS_KEY and LIGHTNING_KEY never reach the browser. Each route below
   answers only this site's own pages, and, when APP_PASSCODE is set, only a browser that has entered it. */
async function sha256hex(s) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
async function unlocked(request, env) {
  if (!env.APP_PASSCODE) return true;
  const m = /(?:^|;\s*)nwst_k=([a-f0-9]{64})(?:;|$)/.exec(request.headers.get('Cookie') || '');
  return !!m && m[1] === await sha256hex('nwst:' + env.APP_PASSCODE);
}
async function keyGuard(request, env) {
  if (!isSameOrigin(request)) return json({ error: 'This route only answers the app itself.' }, 401, { 'Cache-Control': 'no-store' });
  if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401, { 'Cache-Control': 'no-store' });
  return null;
}
async function unlock(request, env) {
  if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });
  if (!isSameOrigin(request)) return json({ error: 'This route only answers the app itself.' }, 401);
  if (!env.APP_PASSCODE) return json({ ok: true }, 200, { 'Cache-Control': 'no-store' });
  let code = ''; try { code = String((await request.json()).code || ''); } catch (e) { code = ''; }
  if (code.length > 200 || (await sha256hex('nwst:' + code)) !== (await sha256hex('nwst:' + env.APP_PASSCODE))) {
    await new Promise((r) => setTimeout(r, 400));   // slows guessing a little; Cloudflare rate limiting is the real control
    return json({ error: 'That code is not right.' }, 401, { 'Cache-Control': 'no-store' });
  }
  return json({ ok: true }, 200, { 'Cache-Control': 'no-store',
    'Set-Cookie': 'nwst_k=' + (await sha256hex('nwst:' + env.APP_PASSCODE)) + '; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Strict' });
}
async function chat(request, env) {
  if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });
  if (!env.ANTHROPIC_API_KEY) return json({ error: { message: 'No Anthropic key on the server. Add the ANTHROPIC_API_KEY secret in Cloudflare.' } }, 401, { 'Cache-Control': 'no-store' });
  const g = await keyGuard(request, env); if (g) return g;
  const text = await request.text();
  if (text.length > 5 * 1024 * 1024) return json({ error: { message: 'Request too large.' } }, 413);
  let b; try { b = JSON.parse(text); } catch (e) { return json({ error: { message: 'Bad request.' } }, 400); }
  if (!b || typeof b.model !== 'string' || !/^claude-[a-z0-9.-]{3,60}$/.test(b.model) || !Array.isArray(b.messages)) return json({ error: { message: 'Bad request.' } }, 400);
  // Only what the assistant uses is passed on, so the stored key cannot be driven as a general-purpose gateway.
  const out = { model: b.model, max_tokens: Math.min(8000, Math.max(1, Math.round(Number(b.max_tokens)) || 4096)), messages: b.messages };
  if (typeof b.system === 'string') out.system = b.system.slice(0, 20000);
  if (b.stream === true) out.stream = true;
  if (b.output_config && typeof b.output_config === 'object') out.output_config = { effort: String(b.output_config.effort || 'medium') };
  if (Array.isArray(b.tools)) {
    const t = b.tools.filter((x) => x && x.name === 'web_search' && /^web_search_\d{8}$/.test(String(x.type)))[0];
    if (t) out.tools = [Object.assign({}, t, { max_uses: Math.min(3, Math.max(1, Math.round(Number(t.max_uses)) || 3)) })];
  }
  const res = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST', signal: out.stream ? undefined : AbortSignal.timeout(150000),
    headers: { 'Content-Type': 'application/json', 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' }, body: JSON.stringify(out) });
  const sse = out.stream && res.ok && /event-stream/i.test(res.headers.get('Content-Type') || '');
  return new Response(res.body, { status: res.status, headers: { 'Content-Type': sse ? 'text/event-stream; charset=utf-8' : 'application/json; charset=utf-8', 'Cache-Control': 'no-store, no-transform', 'X-Accel-Buffering': 'no' } });
}
async function wethr(rest, request, env, stream) {
  if (request.method !== 'GET') return new Response('Method not allowed', { status: 405 });
  if (!env.WETHR_API_KEY) return json({ error: 'No wethr.net key on the server. Add the WETHR_API_KEY secret in Cloudflare.' }, 401, { 'Cache-Control': 'no-store' });
  const g = await keyGuard(request, env); if (g) return g;
  const u = new URL(request.url);
  if (stream) {
    const st = u.searchParams.get('stations') || '';
    if (!/^[A-Za-z0-9,]{3,60}$/.test(st)) return json({ error: 'stations required' }, 400);
    const up = await fetch('https://wethr.net:3443/api/v2/stream?stations=' + st + '&api_key=' + encodeURIComponent(env.WETHR_API_KEY), { headers: { Accept: 'text/event-stream' } });
    if (!up.ok || !up.body) return json({ error: 'wethr.net stream: HTTP ' + up.status }, 502, { 'Cache-Control': 'no-store' });
    return new Response(up.body, { status: 200, headers: { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' } });
  }
  if (!/^[A-Za-z0-9_]+(\.[a-z]{2,4})?(\/[A-Za-z0-9_-]+(\.[a-z]{2,4})?){0,3}$/.test(rest)) return json({ error: 'Unsupported wethr.net path' }, 404);
  u.searchParams.delete('api_key');
  const res = await fetch('https://wethr.net/api/v2/' + rest + (u.search || ''), { signal: AbortSignal.timeout(20000),
    headers: { Authorization: 'Bearer ' + env.WETHR_API_KEY, Accept: 'application/json' } });
  return new Response(res.body, { status: res.status, headers: { 'Content-Type': res.headers.get('Content-Type') || 'application/json', 'Cache-Control': 'no-store' } });
}

/* ---- live lightning flashes (v3.41.0): WarPulse Lightning API (lightningapi.dev), key held as the LIGHTNING_KEY secret ----
   One request shape only: GET /api/lightning/flashes with a latitude/longitude box and a look-back in minutes.
   The API bills one call for every 100 flashes returned (at least one), so the box is limited in size and snapped
   outward to tenths of a degree, and each answer is kept at the edge for 45 seconds: reloading a view inside that
   time is answered from the copy and not billed again. X-Fetched-At tells the page how old a copy is. */
/* GET /api/models (v3.49.0): what GribStream's own catalogue says about each model the app uses: when it runs, how far ahead it
   reaches, its grid. The catalogue is free to read; the server's token rides along and never reaches the browser. The answer is
   the same for everyone and changes rarely, so it is kept at the edge for six hours. */
const MODEL_CODES = ['hrrr', 'hrrrsubh', 'rap', 'rrfs2dfld', 'nbm', 'gfs', 'ifsoper', 'gefsatmos', 'aifsoper', 'aigfssfc', 'aiwpfourcastnet', 'refsct', 'grefs', 'rtmaru', 'urma', 'mrms', 'nwmshortland'];
async function modelCatalogue(request, env, ctx) {
  if (request.method !== 'GET') return new Response('Method not allowed', { status: 405 });
  if (!isSameOriginRead(request)) return json({ error: 'This route only answers the app itself.' }, 401, { 'Cache-Control': 'no-store' });
  if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401, { 'Cache-Control': 'no-store' });
  const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null, key = new Request('https://gribstream.com/api/v2/catalog/datasets?nws-terminal-models=1');
  if (cache) { const hit = await cache.match(key); if (hit) { const h = new Headers(hit.headers); h.set('X-Models-Cache', 'HIT'); h.set('Cache-Control', 'no-store'); return new Response(hit.body, { status: 200, headers: h }); } }
  const headers = { 'User-Agent': UA, Accept: 'application/json' }; if (env.GS_TOKEN) headers.Authorization = 'Bearer ' + env.GS_TOKEN;
  const label = (v) => (v && typeof v === 'object' ? v.label : v) || '';
  // one request for the whole catalogue: asking for sixteen entries at once tripped GribStream's rate limit (HTTP 429)
  const r = await fetch('https://gribstream.com/api/v2/catalog/datasets', { headers, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
  if (!r.ok) return json({ error: 'The GribStream catalogue answered HTTP ' + r.status + '.' }, 502, { 'Cache-Control': 'no-store' });
  const all = await r.json(), list = Array.isArray(all) ? all : (all && (all.datasets || all.items)) || [], byCode = {};
  for (const d of list) if (d && d.code) byCode[d.code] = d;
  const got = MODEL_CODES.map((code) => {
    const c = byCode[code]; if (!c) return { code, error: 'not in the catalogue' };
    return { code, name: String(c.full_name || c.name || code).slice(0, 80), runs: String(label(c.run_cadence)).slice(0, 120), step: String(label(c.time_resolution)).slice(0, 120), grid: String(label(c.spatial_resolution)).slice(0, 80),
             leadMin: String(c.min_lead_time || ''), leadMax: String(c.max_lead_time || ''), members: c.is_ensemble ? +c.member_count || null : null, fields: +c.parameter_count || null };
  });
  const okN = got.filter((m) => !m.error).length;
  if (!okN) return json({ error: 'The GribStream catalogue did not answer.' }, 502, { 'Cache-Control': 'no-store' });
  const body = JSON.stringify({ at: new Date().toISOString(), source: 'https://gribstream.com/api/v2/catalog/datasets', models: got });
  const head = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'X-Models-Cache': 'MISS' };
  if (cache && ctx && ctx.waitUntil && okN === got.length) ctx.waitUntil(cache.put(key, new Response(body, { status: 200, headers: { ...head, 'Cache-Control': 'public, max-age=21600' } })));
  return new Response(body, { status: 200, headers: head });
}

/* GET /api/radar/point (v3.51.0): the radar over one spot across the last 15 minutes, from the WarPulse radar service
   (lightningapi.dev). The RADAR_TILES_KEY secret is traded for a short-lived token; neither one reaches the browser.
   A lookup is billed as one radar tile, so each answer is kept at the edge for two minutes, and lookups stop short of the
   month's allowance: on pay-as-you-go the service keeps answering past it and bills each one. The token answer carries the
   month's allowance and the count used, which is what the stop is based on. */
let RADAR_TOK = null;   // { t, until, used, monthly, n }: token, when to renew it, tiles used when it was issued, the allowance, lookups made since
const RADAR_MARGIN = 250, RADAR_TOKEN_KEY = 'https://cache.nws-terminal/radar-token/v1';
async function radarToken(env, ctx, force) {
  const now = Date.now(), cache = typeof caches !== 'undefined' && caches.default ? caches.default : null;
  if (!force && RADAR_TOK && now < RADAR_TOK.until) return RADAR_TOK;
  if (!force && cache) { const hit = await cache.match(new Request(RADAR_TOKEN_KEY)); const j = hit ? await hit.json().catch(() => null) : null; if (j && j.t && now < j.until) { RADAR_TOK = { ...j, n: RADAR_TOK && RADAR_TOK.t === j.t ? RADAR_TOK.n : 0 }; return RADAR_TOK; } }
  const r = await fetch('https://api.lightningapi.dev/v1/radar-tiles/token', { method: 'POST', headers: { 'X-API-Key': env.RADAR_TILES_KEY, 'User-Agent': UA, Accept: 'application/json' }, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
  if (!r.ok) { const e = new Error('The radar service refused the key (HTTP ' + r.status + ').'); e.status = r.status; throw e; }
  const j = await r.json().catch(() => null);
  if (!j || !j.token) throw new Error('The radar service sent no token.');
  const monthly = Number.isFinite(+j.monthly_tiles) ? +j.monthly_tiles : 0, used = Number.isFinite(+j.tiles_used) ? +j.tiles_used : 0, exp = Number.isFinite(+j.expires_at) ? +j.expires_at * 1000 : now + 36e5;
  // near the allowance the count is re-read every ten minutes; otherwise the token is kept until shortly before it lapses
  RADAR_TOK = { t: String(j.token), until: Math.max(now + 60000, Math.min(exp - 5 * 60000, now + (monthly && used >= monthly - 1000 ? 10 : 50) * 60000)), used, monthly, n: 0 };
  if (cache && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(new Request(RADAR_TOKEN_KEY), new Response(JSON.stringify({ t: RADAR_TOK.t, until: RADAR_TOK.until, used, monthly }), { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=' + Math.max(60, Math.round((RADAR_TOK.until - now) / 1000)) } })));
  return RADAR_TOK;
}
async function radarPoint(request, env, ctx) {
  const NS = { 'Cache-Control': 'no-store' };
  if (request.method !== 'GET') return new Response('Method not allowed', { status: 405 });
  if (!env.RADAR_TILES_KEY) return json({ error: 'No radar key on the server. Add the RADAR_TILES_KEY secret in Cloudflare.' }, 401, NS);
  if (!isSameOriginRead(request)) return json({ error: 'This route only answers the app itself.' }, 401, NS);
  if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401, NS);
  const q = new URL(request.url).searchParams, lat = Number(q.get('lat') || NaN), lon = Number(q.get('lon') || NaN);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return json({ error: 'Give lat and lon.' }, 400, NS);
  if (lat < 24 || lat > 50 || lon < -125 || lon > -66.5) return json({ error: 'This radar covers the continental US only.', outside: true }, 400, NS);
  const la = lat.toFixed(2), lo = lon.toFixed(2), cache = typeof caches !== 'undefined' && caches.default ? caches.default : null, key = new Request('https://cache.nws-terminal/radar-point/v1/' + la + '/' + lo);
  if (cache) { const hit = await cache.match(key); if (hit) { const h = new Headers(hit.headers); h.set('Cache-Control', 'no-store'); h.set('X-Radar-Cache', 'HIT'); return new Response(hit.body, { status: 200, headers: h }); } }
  let tok = await radarToken(env, ctx, false);
  const over = (k) => k.monthly > 0 && k.used + k.n >= k.monthly - RADAR_MARGIN;
  if (over(tok)) return json({ error: 'Radar lookups are paused: this month’s free allowance is nearly used.', paused: true, used: tok.used + tok.n, monthly: tok.monthly }, 429, NS);
  const ask = (k) => fetch('https://tiles.lightningapi.dev/v1/radar/history?lat=' + la + '&lon=' + lo + '&t=' + encodeURIComponent(k.t), { headers: { 'User-Agent': UA, Accept: 'application/json' }, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
  let r = await ask(tok);
  if (r.status === 401) { tok = await radarToken(env, ctx, true); if (over(tok)) return json({ error: 'Radar lookups are paused: this month’s free allowance is nearly used.', paused: true, used: tok.used, monthly: tok.monthly }, 429, NS); r = await ask(tok); }   // the token lapsed early: one new one, one more try
  if (!r.ok) return json({ error: 'The radar service answered HTTP ' + r.status + '.' }, r.status === 429 ? 429 : 502, NS);
  tok.n++;
  const j = await r.json().catch(() => null), pts = j && Array.isArray(j.points) ? j.points : null;
  if (!pts) return json({ error: 'The radar service sent an answer this app does not understand.' }, 502, NS);
  const points = pts.slice(-60).map((p) => ({ f: String(p && p.frame || '').slice(0, 12), dbz: p && typeof p.dbz === 'number' && Number.isFinite(p.dbz) ? Math.round(p.dbz * 10) / 10 : null })).filter((p) => /^\d{12}$/.test(p.f));
  const body = JSON.stringify({ at: new Date().toISOString(), lat: +la, lon: +lo, points, used: tok.used + tok.n, monthly: tok.monthly });
  const head = { 'Content-Type': 'application/json; charset=utf-8', 'X-Content-Type-Options': 'nosniff' };
  if (cache && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(key, new Response(body, { status: 200, headers: { ...head, 'Cache-Control': 'public, max-age=120' } })));
  return new Response(body, { status: 200, headers: { ...head, 'Cache-Control': 'no-store', 'X-Radar-Cache': 'MISS' } });
}

async function lightning(request, env, ctx) {
  if (request.method !== 'GET') return new Response('Method not allowed', { status: 405 });
  if (!env.LIGHTNING_KEY) return json({ error: 'No lightning key on the server. Add the LIGHTNING_KEY secret in Cloudflare.' }, 401, { 'Cache-Control': 'no-store' });
  // a same-origin GET carries no Origin header, and older Safari sends no Sec-Fetch-Site: isSameOriginRead falls back to the Referer
  if (!isSameOriginRead(request)) return json({ error: 'This route only answers the app itself.' }, 401, { 'Cache-Control': 'no-store' });
  if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401, { 'Cache-Control': 'no-store' });
  const q = new URL(request.url).searchParams, num = (k) => { const v = q.get(k); return v == null || v === '' ? NaN : Number(v); };
  let s = num('min_lat'), n = num('max_lat'), w = num('min_lon'), e = num('max_lon'), m = num('since_minutes');
  if (![s, n, w, e].every(Number.isFinite) || s < -90 || n > 90 || w < -180 || e > 180 || s >= n || w >= e) return json({ error: 'Give min_lat, max_lat, min_lon and max_lon.' }, 400, { 'Cache-Control': 'no-store' });
  s = Math.floor(s * 10) / 10; n = Math.ceil(n * 10) / 10; w = Math.floor(w * 10) / 10; e = Math.ceil(e * 10) / 10;
  if (n - s > 25 || e - w > 40) return json({ error: 'That area is too large for live flashes.' }, 400, { 'Cache-Control': 'no-store' });
  m = Number.isFinite(m) ? Math.max(1, Math.min(15, Math.round(m))) : 15;
  const up = 'https://api.lightningapi.dev/v1/flashes?since_minutes=' + m + '&min_lat=' + s.toFixed(1) + '&max_lat=' + n.toFixed(1) + '&min_lon=' + w.toFixed(1) + '&max_lon=' + e.toFixed(1);
  const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null, cacheKey = new Request(up);   // the key is a header, so it is not part of what is stored
  const hit = cache ? await cache.match(cacheKey) : null;
  if (hit) { const h = new Headers(hit.headers); h.set('Cache-Control', 'no-store'); h.set('X-Lightning-Cache', 'hit'); return new Response(hit.body, { status: 200, headers: h }); }
  const res = await fetch(up, { signal: AbortSignal.timeout(20000), headers: { 'X-API-Key': env.LIGHTNING_KEY, Accept: 'application/json' } });
  const body = await res.text(), cost = res.headers.get('X-Quota-Cost') || '';
  if (!res.ok) return new Response(body.slice(0, 2000) || JSON.stringify({ error: 'HTTP ' + res.status }), { status: res.status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });
  const head = { 'Content-Type': 'application/json; charset=utf-8', 'X-Fetched-At': String(Date.now()), 'X-Quota-Cost': cost, 'X-Content-Type-Options': 'nosniff' };
  if (cache && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(cacheKey, new Response(body, { status: 200, headers: { ...head, 'Cache-Control': 'public, max-age=45' } })));
  return new Response(body, { status: 200, headers: { ...head, 'Cache-Control': 'no-store', 'X-Lightning-Cache': 'miss' } });
}

async function proxyGribStream(rest, request, env) {
  if (request.method === 'OPTIONS') return new Response(null, { status: 204 });
  if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });
  if (!/^api\/v2\/[a-z0-9_]+\/(timeseries|history|forecasts?)$/i.test(rest)) {
    return json({ error: 'Unsupported GribStream path' }, 404);
  }
  const body = await request.text();
  if (body.length > 64 * 1024) return json({ error: 'Request body too large' }, 413);
  let auth = request.headers.get('Authorization');
  if (!auth && env.GS_TOKEN) {
    if (!isSameOrigin(request)) return json({ error: 'No GribStream token supplied' }, 401);
    if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401);
    auth = 'Bearer ' + env.GS_TOKEN;
  }
  if (!auth) return json({ error: 'No GribStream token. Add one in Settings & keys.' }, 401);
  const res = await fetch(GS_ORIGIN + '/' + rest, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', Authorization: auth, 'User-Agent': UA },
    body,
    signal: AbortSignal.timeout(30000),
  });
  const headers = new Headers({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  const ct = res.headers.get('Content-Type');
  if (ct) headers.set('Content-Type', ct);
  return new Response(res.body, { status: res.status, headers });
}

/* Same-origin test that also works for GET: browsers send no Origin header
   on a same-origin GET, so fall back to the Referer when Sec-Fetch-Site is
   missing (older Safari). */
function isSameOriginRead(request) {
  const site = request.headers.get('Sec-Fetch-Site');
  if (site) return site === 'same-origin';
  const self = new URL(request.url).origin;
  const origin = request.headers.get('Origin');
  if (origin) return origin === self;
  const ref = request.headers.get('Referer');
  try { return !!ref && new URL(ref).origin === self; } catch { return false; }
}

const WINDY_API = 'https://api.windy.com';
const httpsOnly = (u) => (typeof u === 'string' && /^https:\/\/[^\s"'<>]+$/i.test(u) ? u : '');
function windyOnly(u) {
  u = httpsOnly(u);
  if (!u) return '';
  try { const h = new URL(u).hostname; return h === 'windy.com' || h.endsWith('.windy.com') ? u : ''; } catch { return ''; }
}

/* Webcams near a point. The response is trimmed to the fields the app uses.
   Never cached: free-tier image URLs carry a token that expires after 10
   minutes, so a cached list would hand out dead images. */
async function cams(request, env) {
  if (request.method !== 'GET') return json({ error: 'Method not allowed' }, 405);
  const u = new URL(request.url);
  const lat = Number(u.searchParams.get('lat'));
  const lon = Number(u.searchParams.get('lon'));
  if (!u.searchParams.get('lat') || !u.searchParams.get('lon') ||
      !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    return json({ error: 'lat/lon required' }, 400);
  }
  const r = Math.min(250, Math.max(1, Math.round(Number(u.searchParams.get('r')) || 50)));        // km, API max 250
  const limit = Math.min(50, Math.max(1, Math.round(Number(u.searchParams.get('limit')) || 24))); // API max 50

  let key = request.headers.get('X-Windy-Key');
  if (!key && env.WINDY_WEBCAMS_KEY) {
    // The stored key only serves this app's own pages.
    if (!isSameOriginRead(request)) return json({ error: 'No Windy Webcams key supplied' }, 401);
    if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401);
    key = env.WINDY_WEBCAMS_KEY;
  }
  if (!key) return json({ error: 'No Windy Webcams API key. Add one in Settings & keys.' }, 401);
  if (!/^[A-Za-z0-9_-]{8,128}$/.test(key)) return json({ error: 'That does not look like a Windy API key.' }, 401);

  const noStore = { 'Cache-Control': 'no-store' };
  const page = async (radius, offset) => {
    const res = await fetch(`${WINDY_API}/webcams/api/v3/webcams?nearby=${lat.toFixed(4)},${lon.toFixed(4)},${radius}` +
      `&limit=50&offset=${offset}&include=images,location,player,urls&lang=en`, {
      headers: { 'x-windy-api-key': key, Accept: 'application/json', 'User-Agent': UA },
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    if (!res.ok) { const e = new Error('upstream'); e.status = res.status; throw e; }
    const d = await res.json();
    return { total: Number(d.total) || 0, list: Array.isArray(d.webcams) ? d.webcams : [] };
  };
  /* Windy does not return `nearby` results nearest-first, and one page holds
     50. A wide radius over a metro area would therefore hand back an arbitrary
     50 and miss the closest cameras. So: widen in steps until a ring holds
     enough cameras, read that whole ring (up to 200), and sort it here. */
  const MAX_PAGES = 4;
  const rings = [10, 25, 50, 100].filter((x) => x < r).concat(r);
  let raw = [], total = 0, ring = r;
  try {
    for (const radius of rings) {
      const first = await page(radius, 0);
      ring = radius; total = first.total; raw = first.list;
      if (total >= limit || radius === r) {
        const offsets = [];
        for (let o = 50; o < total && offsets.length < MAX_PAGES - 1; o += 50) offsets.push(o);
        const rest = await Promise.all(offsets.map((o) => page(radius, o)));
        for (const p of rest) raw = raw.concat(p.list);
        break;
      }
    }
  } catch (err) {
    if (!err.status) throw err;
    if (err.status === 401 || err.status === 403) {
      return json({ error: 'Windy did not accept the Webcams API key. Check that it is a Webcams key (keys are per product) and was copied in full.' }, 401, noStore);
    }
    if (err.status === 429) return json({ error: 'Windy rate limit reached. Try again shortly.' }, 429, noStore);
    return json({ error: 'Windy Webcams API returned ' + err.status }, 502, noStore);
  }
  const rad = Math.PI / 180;
  const km = (la, lo) => {
    const a = Math.sin((la - lat) * rad / 2) ** 2 + Math.cos(lat * rad) * Math.cos(la * rad) * Math.sin((lo - lon) * rad / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(a));
  };
  const seen = new Set();
  const active = raw
    .filter((c) => c && c.status === 'active' && c.location && Number.isFinite(c.location.latitude) && Number.isFinite(c.location.longitude))
    .filter((c) => (seen.has(c.webcamId) ? false : seen.add(c.webcamId)))
    .map((c) => ({ c, d: km(c.location.latitude, c.location.longitude) }))
    .sort((a, b) => a.d - b.d);
  const webcams = active.slice(0, limit).map(({ c }) => {
      const cur = (c.images && c.images.current) || {};
      const day = (c.images && c.images.daylight) || {};
      const sz = (c.images && c.images.sizes) || {};
      const which = cur.preview ? 'preview' : cur.thumbnail ? 'thumbnail' : 'icon';
      const p = c.player || {};
      return {
        id: c.webcamId,
        title: String(c.title || '').slice(0, 160),
        lat: c.location.latitude, lon: c.location.longitude,
        city: c.location.city || '', region: c.location.region || '', country: c.location.country_code || '',
        updated: c.lastUpdatedOn || '',
        img: httpsOnly(cur[which]), day: httpsOnly(day[which] || day.preview || day.thumbnail),
        w: (sz[which] && sz[which].width) || 0, h: (sz[which] && sz[which].height) || 0,
        detail: windyOnly(c.urls && c.urls.detail),
        player: { live: windyOnly(p.live), day: windyOnly(p.day), month: windyOnly(p.month), year: windyOnly(p.year) },
      };
    });
  // more: cameras exist inside the asked radius beyond the nearest `limit` returned.
  return json({ radiusKm: r, searchedKm: ring, more: ring < r || active.length > webcams.length || total > raw.length, webcams }, 200, noStore);
}

const NORMALS_TTL = 7 * 86400;
async function normals(request, ctx) {
  const u = new URL(request.url);
  const lat = Number(u.searchParams.get('lat'));
  const lon = Number(u.searchParams.get('lon'));
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    return json({ error: 'lat/lon required' }, 400);
  }
  const la = lat.toFixed(2), lo = lon.toFixed(2);
  const cacheKey = new Request(`https://cache.nws-terminal/normals/v2/${la}/${lo}`);
  const cache = caches.default;
  const hit = await cache.match(cacheKey);
  if (hit) return hit;
  const now = new Date();
  const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 0)).toISOString().slice(0, 10);
  const src = 'https://archive-api.open-meteo.com/v1/archive?latitude=' + la + '&longitude=' + lo +
    '&start_date=1970-01-01&end_date=' + end +
    '&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=auto';
  const r = await fetch(src, {
    headers: { 'User-Agent': UA },
    cf: { cacheTtl: NORMALS_TTL, cacheEverything: true },
    signal: AbortSignal.timeout(25000),
  });
  if (!r.ok) return json({ error: 'Archive API returned ' + r.status }, 502, { 'Cache-Control': 'no-store' });
  const d = await r.json();
  if (!d.daily || !d.daily.time) return json({ error: 'No archive data' }, 502, { 'Cache-Control': 'no-store' });
  const t = d.daily.time, hi = d.daily.temperature_2m_max, lw = d.daily.temperature_2m_min;
  const acc = {};
  let firstYear = 9999, lastYear = 0;
  for (let i = 0; i < t.length; i++) {
    const yr = +t[i].slice(0, 4), key = t[i].slice(5);
    const a = acc[key] || (acc[key] = { hs: 0, hn: 0, ls: 0, ln: 0, rh: null, rhy: 0, rl: null, rly: 0, n: 0 });
    const h = hi[i], l = lw[i];
    if (h == null && l == null) continue;
    a.n++;
    if (yr < firstYear) firstYear = yr;
    if (yr > lastYear) lastYear = yr;
    const inNormal = yr >= 1991 && yr <= 2020;
    if (h != null) {
      if (inNormal) { a.hs += h; a.hn++; }
      if (a.rh == null || h >= a.rh) { a.rh = h; a.rhy = yr; }
    }
    if (l != null) {
      if (inNormal) { a.ls += l; a.ln++; }
      if (a.rl == null || l <= a.rl) { a.rl = l; a.rly = yr; }
    }
  }
  const days = {};
  for (const k of Object.keys(acc)) {
    const a = acc[k];
    days[k] = [
      a.hn ? Math.round(a.hs / a.hn) : null,
      a.ln ? Math.round(a.ls / a.ln) : null,
      a.rh == null ? null : Math.round(a.rh), a.rhy,
      a.rl == null ? null : Math.round(a.rl), a.rly,
      a.n,
    ];
  }
  const out = json(
    { v: 2, lat: +la, lon: +lo, firstYear, lastYear, normals: '1991-2020', source: 'Open-Meteo ERA5 reanalysis',
      fields: ['avgHigh', 'avgLow', 'recHigh', 'recHighYr', 'recLow', 'recLowYr', 'years'], days },
    200,
    { 'Cache-Control': `public, max-age=86400, s-maxage=${NORMALS_TTL}` },
  );
  ctx.waitUntil(cache.put(cacheKey, out.clone()));
  return out;
}

function securityHeaders(res, url) {
  const pathname = url.pathname;
  const h = new Headers(res.headers);
  h.set('X-Content-Type-Options', 'nosniff');
  h.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  h.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
  h.set('Permissions-Policy', 'geolocation=(self), microphone=(), camera=(), payment=()');
  const isDoc = pathname === '/' || pathname.endsWith('.html');
  if (isDoc) h.set('Content-Security-Policy', CSP);
  if (res.ok && /\.(css|js)$/.test(pathname) && pathname !== '/sw.js' && url.searchParams.has('v')) {
    // Versioned by query string from index.html: safe to keep for a year.
    h.set('Cache-Control', 'public, max-age=31536000, immutable');
  } else if (isDoc || pathname === '/sw.js' || /\.(css|js|webmanifest)$/.test(pathname)) {
    h.set('Cache-Control', 'public, max-age=0, must-revalidate');
  } else if (res.ok && /\.(woff2?|png|svg|ico)$/.test(pathname)) {
    h.set('Cache-Control', 'public, max-age=604800');
  }
  if (pathname === '/sw.js') h.set('Service-Worker-Allowed', '/');
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    const g = path.match(/^\/p\/gs\/(.*)$/);
    if (g) {
      try { return await proxyGribStream(g[1], request, env); }
      catch (err) { return json({ error: 'GribStream proxy failed: ' + err.message }, 502); }
    }

    const m = path.match(/^\/p\/([a-z]+)\/(.*)$/);
    if (m) {
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        return new Response('Method not allowed', { status: 405 });
      }
      try { return await proxy(m[1], m[2], request); }
      catch (err) {
        const status = err.name === 'TimeoutError' ? 504 : 502;
        return new Response('Upstream fetch failed: ' + err.message, { status, headers: { 'Cache-Control': 'no-store' } });
      }
    }

    if (path === '/api/normals') {
      try { return await normals(request, ctx); }
      catch (err) { return json({ error: err.message }, 502, { 'Cache-Control': 'no-store' }); }
    }
    if (path === '/api/cams') {
      try { return await cams(request, env); }
      catch (err) {
        const status = err.name === 'TimeoutError' ? 504 : 502;
        return json({ error: 'Webcams request failed: ' + err.message }, status, { 'Cache-Control': 'no-store' });
      }
    }
    if (path === '/api/chat') {
      try { return await chat(request, env); }
      catch (err) { return json({ error: { message: 'Assistant request failed: ' + err.message } }, err.name === 'TimeoutError' ? 504 : 502, { 'Cache-Control': 'no-store' }); }
    }
    if (path === '/api/wethr-stream' || path.startsWith('/api/wethr/')) {
      try { return await wethr(path.slice('/api/wethr/'.length), request, env, path === '/api/wethr-stream'); }
      catch (err) { return json({ error: 'wethr.net request failed: ' + err.message }, err.name === 'TimeoutError' ? 504 : 502, { 'Cache-Control': 'no-store' }); }
    }
    if (path === '/api/models') {
      try { return await modelCatalogue(request, env, ctx); }
      catch (err) { return json({ error: 'Model catalogue request failed: ' + err.message }, 502, { 'Cache-Control': 'no-store' }); }
    }
    if (path === '/api/radar/point') {
      try { return await radarPoint(request, env, ctx); }
      catch (err) { return json({ error: 'Radar lookup failed: ' + String(err && err.message || err).replace(/([?&]t=)[^&\s]+/g, '$1…').slice(0, 160) }, err && err.name === 'TimeoutError' ? 504 : 502, { 'Cache-Control': 'no-store' }); }
    }
    if (path === '/api/lightning/flashes') {
      try { return await lightning(request, env, ctx); }
      catch (err) { return json({ error: 'Lightning request failed: ' + err.message }, err.name === 'TimeoutError' ? 504 : 502, { 'Cache-Control': 'no-store' }); }
    }
    if (path === '/api/unlock') return unlock(request, env);
    if (path === '/api/config') {
      return json({ gsServerToken: !!env.GS_TOKEN, lightningServerKey: !!env.LIGHTNING_KEY, radarServerKey: !!env.RADAR_TILES_KEY, camsServerKey: !!env.WINDY_WEBCAMS_KEY, claudeServerKey: !!env.ANTHROPIC_API_KEY, wethrServerKey: !!env.WETHR_API_KEY,
                    passcode: !!env.APP_PASSCODE, locked: !(await unlocked(request, env)), version: VERSION }, 200, { 'Cache-Control': 'no-store' });
    }
    if (path === '/api/health') {
      return json({ ok: true, version: VERSION, time: new Date().toISOString() }, 200, { 'Cache-Control': 'no-store' });
    }

    const res = await env.ASSETS.fetch(request);
    return securityHeaders(res, url);
  },
};
