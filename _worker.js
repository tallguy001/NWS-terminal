/* NWS Terminal edge worker (v3.83.0)
   - serves the app shell from static assets with security + cache headers
   - /p/<kind>/...   same-origin read-only proxy for NOAA hosts without CORS
   - /p/gs/...       GribStream POST proxy (keeps the token off third parties)
   - /api/normals    1991-2020 normals + records, computed once per point and cached
   - /api/cams       Windy Webcams API v3 near a point (key stays a worker secret)
   - /api/wicams     Wisconsin 511 road cameras near a point (key stays a worker secret)
   - /api/wiroads    Wisconsin 511 winter road conditions in a box (same key)
   - /api/config     what the server can do for the client
   - /api/health     liveness for uptime checks
   - /push/...       push alerts: key, sub, unsub, test (the app) and tick (the cron Worker); needs KV bound as PUSH */

const VERSION = '3.89.1';

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
  // The FAA's airport status for the Storm Zone (v3.85.0): one XML document, no CORS.
  faa: 'https://nasstatus.faa.gov',
  // New Mexico DOT's road-camera stills (v3.88.0): served over http only, which an https page cannot show. Snapshot files only.
  nmss: 'http://ss.nmroads.com',
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
  // WisDOT's live road-camera video (v3.66.0). Stills are images, which img-src already allows.
  // v3.86.0: the state DOTs' live road-camera streams (HLS) come from many agency and CDN hosts.
  "media-src 'self' https:",
  "worker-src 'self'",
  "manifest-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
  // No frame-ancestors and no X-Frame-Options: v2.1.1 removed framing limits
  // because they blank the page inside embedded browsers.
].join('; ');

function cacheFor(pathname) {
  if (pathname.startsWith('/snapshots/')) return 60;   // a road camera's newest picture
  if (/\.(png|gif|jpg|jpeg|webp)$/i.test(pathname)) return 600;
  if (pathname.includes('/md/') || pathname.includes('/watch/')) return 120;
  if (pathname.startsWith('/search')) return 86400;
  if (pathname.startsWith('/trade-api/')) return 30;      // market prices
  if (pathname === '/api/airport-status-information') return 60;   // FAA delays change by the minute
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
      !/^vector\/rest\/services\/(outlooks|precip|hazards)\/[A-Za-z0-9_]+\/MapServer\/\d+\/query$/.test(rest) &&
      !/^vector\/rest\/services\/(outlooks\/wpc_wssi|outlooks\/wpc_wssi_p|precip\/wpc_prob_winter_precip)\/MapServer\/(export|legend|identify)$/.test(rest) &&
      !/^eventdriven\/rest\/services\/water\/riv_gauges\/MapServer\/(0|15)\/query$/.test(rest) &&
      !/^eventdriven\/rest\/services\/WWA\/watch_warn_adv\/MapServer\/0\/query$/.test(rest) &&
      !/^raster\/rest\/services\/air_quality\/ndgd_smoke_sfc_1hr_avg_time\/ImageServer\/(exportImage|legend)$/.test(rest) &&
      !/^experimental\/rest\/services\/NWS_HeatRisk\/ImageServer\/(exportImage|legend)$/.test(rest) &&
      !/^raster\/rest\/services\/snow\/NOHRSC_Snow_Analysis\/MapServer\/(export|legend)$/.test(rest) &&
      !/^vector\/rest\/services\/obs\/usnic_greatlakes_ice_chart\/MapServer\/(export|legend)$/.test(rest) &&
      !/^eventdriven\/rest\/services\/radar\/radar_base_reflectivity_time\/ImageServer(\/exportImage)?$/.test(rest) &&
      !/^tropical\/rest\/services\/tropical\/NHC_tropical_weather\/MapServer(\/\d+\/query)?$/.test(rest)) return new Response('Unsupported path', { status: 404 });   // v3.79.0: the Tropical screen
  if (kind === 'nowcoast' && rest !== 'geoserver/satellite/wms' && rest !== 'geoserver/observations/lightning_detection/ows') return new Response('Unsupported path', { status: 404 });
  if (kind === 'opengeo' && !/^geoserver\/[a-z]{4}\/ows$/.test(rest)) return new Response('Unsupported path', { status: 404 });
  if (kind === 'cocorahs' && rest !== 'export/exportreports.aspx') return new Response('Unsupported path', { status: 404 });
  if (kind === 'faa' && rest !== 'api/airport-status-information') return new Response('Unsupported path', { status: 404 });
  if (kind === 'nmss' && !/^snapshots\/[A-Za-z0-9_.-]+\.jpg$/.test(rest)) return new Response('Unsupported path', { status: 404 });
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
   GS_TOKEN, ANTHROPIC_API_KEY, WETHR_API_KEY, WINDY_WEBCAMS_KEY, WI511_KEY and LIGHTNING_KEY never reach the browser. Each route below
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

/* ---- Wisconsin 511 road cameras (v3.66.0) ----
   WisDOT's developer API (511wi.gov). The key is the WI511_KEY secret. The API hands back every camera in the state and allows
   ten calls a minute, so the list is read at most once in ten minutes, trimmed to what the app shows, and kept; each request is
   then answered from that copy by distance. Only two kinds of address are passed on: a still, rebuilt here from the view number
   (511wi.gov/map/Cctv/<n>), and a video playlist on a dot.wi.gov host. */
const WI511 = 'https://511wi.gov', WI_KEEP_MS = 600000;
let wiMem = null;   // { at, list }
function wiVideo(u) {
  u = typeof u === 'string' && /^https:\/\/[^\s"'<>]+$/i.test(u) ? u : '';
  if (!u) return '';
  try { const x = new URL(u); return (x.hostname === 'dot.wi.gov' || x.hostname.endsWith('.dot.wi.gov')) && /\.m3u8$/i.test(x.pathname) ? u : ''; } catch { return ''; }
}
function wiTrim(raw) {
  const out = [], seen = new Set();
  for (const c of Array.isArray(raw) ? raw : []) {
    if (!c) continue;
    const lat = Number(c.Latitude), lon = Number(c.Longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180 || (lat === 0 && lon === 0)) continue;
    const road = String(c.Roadway || c.RoadwayName || '').trim().slice(0, 40);
    const place = String(c.Location || road || 'Road camera').trim().slice(0, 120);
    const dir = String(c.Direction || c.DirectionOfTravel || '').trim();
    // one record per view; an older, flat record carries its one view on the camera itself
    const views = Array.isArray(c.Views) && c.Views.length ? c.Views : [{ Id: c.Id, Url: c.Url, Status: c.Status, Description: '', VideoUrl: c.VideoUrl }];
    for (const v of views) {
      if (!v || /^disabled$/i.test(String(v.Status || '').trim())) continue;
      const m = /\/map\/Cctv\/(\d+)/i.exec(String(v.Url || '')), id = m ? m[1] : (/^\d+$/.test(String(v.Id)) ? String(v.Id) : '');
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const d = String(v.Description || '').trim().slice(0, 60);
      out.push({ id, title: d && d.toLowerCase() !== place.toLowerCase() ? place + ' · ' + d : place, road, dir: /^(none|unknown|)$/i.test(dir) ? '' : dir.slice(0, 20),
                 lat: Math.round(lat * 1e5) / 1e5, lon: Math.round(lon * 1e5) / 1e5, county: String(c.County || '').trim().slice(0, 40), video: wiVideo(v.VideoUrl) });
    }
  }
  return out;
}
async function wiList(env, ctx) {
  const now = Date.now();
  if (wiMem && now - wiMem.at < WI_KEEP_MS) return wiMem.list;
  const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null, cacheKey = new Request(WI511 + '/api/v2/get/cameras?format=json');   // the key is left out of what is stored
  const hit = cache ? await cache.match(cacheKey) : null;
  if (hit) { try { const list = await hit.json(); if (Array.isArray(list)) { wiMem = { at: Number(hit.headers.get('X-Fetched-At')) || now, list }; return list; } } catch { /* read it again below */ } }
  const stop = (status, why) => { const e = new Error(why); e.status = status; return e; };   // never carries the address, which holds the key
  let res;
  const ask = (p) => fetch(WI511 + p + '?key=' + encodeURIComponent(env.WI511_KEY) + '&format=json', { headers: { Accept: 'application/json', 'User-Agent': UA }, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
  try { res = await ask('/api/v2/get/cameras'); if (res.status === 404) res = await ask('/api/getcameras'); }   // the documented address, then the one it replaced
  catch (err) { if (wiMem) return wiMem.list; throw stop(err && err.name === 'TimeoutError' ? 504 : 502, 'no answer'); }
  if (!res.ok) { if (wiMem && res.status !== 401 && res.status !== 403) return wiMem.list; throw stop(res.status, 'refused'); }
  let raw = null; try { raw = await res.json(); } catch { raw = null; }
  if (!Array.isArray(raw)) { if (wiMem) return wiMem.list; throw stop(502, 'no list'); }
  const list = wiTrim(raw);
  wiMem = { at: now, list };
  if (cache && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(cacheKey, new Response(JSON.stringify(list), { status: 200, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=600', 'X-Fetched-At': String(now) } })));
  return list;
}
/* v3.89.0: the maps ask for every camera inside a box (w,s,e,n) rather than the nearest few to a point */
function camBox(u) {
  const v = String(u.searchParams.get('box') || '').split(',').map(Number);
  if (v.length !== 4 || !v.every(Number.isFinite) || v[0] >= v[2] || v[1] >= v[3] || v[0] < -180 || v[2] > 180 || v[1] < -90 || v[3] > 90) return null;
  return v;
}
const inCamBox = (c, b) => c.lon >= b[0] && c.lon <= b[2] && c.lat >= b[1] && c.lat <= b[3];
async function wicams(request, env, ctx) {
  const NS = { 'Cache-Control': 'no-store' };
  if (request.method !== 'GET') return json({ error: 'Method not allowed' }, 405, NS);
  if (!env.WI511_KEY) return json({ error: 'No Wisconsin 511 key on the server. Add the WI511_KEY secret in Cloudflare.' }, 401, NS);
  if (!isSameOriginRead(request)) return json({ error: 'This route only answers the app itself.' }, 401, NS);
  if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401, NS);
  const u = new URL(request.url), lat = Number(u.searchParams.get('lat')), lon = Number(u.searchParams.get('lon')), bx = camBox(u);
  if (bx) {   // v3.89.0: every camera in a box, for the maps
    if (bx[2] < -93.0 || bx[0] > -86.6 || bx[3] < 42.4 || bx[1] > 47.4) return json({ total: 0, cams: [] }, 200, NS);
    let all; try { all = await wiList(env, ctx); } catch (err) { return json({ error: 'Wisconsin 511 cameras are unavailable' + (err && err.status ? ' (' + err.status + ').' : '.') }, 502, NS); }
    const inside = all.filter((c) => inCamBox(c, bx));
    return json({ total: inside.length, cams: inside.slice(0, 5000) }, 200, NS);
  }
  if (!u.searchParams.get('lat') || !u.searchParams.get('lon') || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return json({ error: 'lat/lon required' }, 400, NS);
  const r = Math.min(250, Math.max(1, Math.round(Number(u.searchParams.get('r')) || 50)));          // km
  const limit = Math.min(60, Math.max(1, Math.round(Number(u.searchParams.get('limit')) || 24)));
  const rad = Math.PI / 180, dLat = r / 111, dLon = r / (111 * Math.max(0.2, Math.cos(lat * rad)));
  // a place whose circle cannot reach Wisconsin is answered without asking WisDOT
  if (lat < 42.4 - dLat || lat > 47.4 + dLat || lon < -93.0 - dLon || lon > -86.6 + dLon) return json({ radiusKm: r, total: 0, more: false, cams: [] }, 200, NS);
  let list;
  try { list = await wiList(env, ctx); }
  catch (err) {
    const s = err && err.status;
    if (s === 401 || s === 403) return json({ error: 'Wisconsin 511 did not accept the key in WI511_KEY.' }, 401, NS);
    if (s === 429) return json({ error: 'Wisconsin 511 allows ten requests a minute and that was reached. Try again shortly.' }, 429, NS);
    if (s === 504) return json({ error: 'Wisconsin 511 did not answer in time.' }, 504, NS);
    return json({ error: err && err.message === 'no list' ? 'Wisconsin 511 did not send a camera list. The key may not be active yet.' : 'Wisconsin 511 cameras are unavailable' + (s ? ' (' + s + ').' : '.') }, 502, NS);
  }
  const km = (la, lo) => { const a = Math.sin((la - lat) * rad / 2) ** 2 + Math.cos(lat * rad) * Math.cos(la * rad) * Math.sin((lo - lon) * rad / 2) ** 2; return 12742 * Math.asin(Math.sqrt(a)); };
  const near = list.map((c) => ({ c, d: km(c.lat, c.lon) })).filter((x) => x.d <= r).sort((a, b) => a.d - b.d);
  return json({ radiusKm: r, total: near.length, more: near.length > limit, cams: near.slice(0, limit).map((x) => x.c) }, 200, NS);
}

/* ---- State DOT road cameras whose servers do not answer a browser (v3.86.0) ----
   Michigan DOT (MiDrive), ALDOT (ALGO Traffic), ODOT (TripCheck) and South Dakota DOT publish their camera lists openly but
   send no CORS header, so the app asks here. Each list is read at most once in 30 minutes, trimmed to what a camera card
   needs, and kept in memory and in the edge cache; a request is answered with the cameras nearest the point. No keys. */
const DOT_KEEP_MS = 30 * 60000, dotMem = {};
const DOT_SRC = {
  mi: { url: 'https://mdotjboss.state.mi.us/MiDrive/camera/list', attr: 'Michigan DOT', page: 'https://mdotjboss.state.mi.us/MiDrive/map', trim: (raw) => {
    const out = [];
    for (const c of Array.isArray(raw) ? raw : []) {
      const cty = String(c && c.county || ''), img = String(c && c.image || '');
      const ll = /lat=(-?[\d.]+)&(?:amp;)?lon=(-?[\d.]+)/.exec(cty), id = /[?&](?:amp;)?id=(\d+)/.exec(cty), src = /src="([^"]+)"/.exec(img);
      if (!ll || !src) continue;
      out.push({ id: id ? id[1] : src[1].slice(-40), title: (String(c.route || '') + ' ' + String(c.location || '')).replace(/\s+/g, ' ').trim(), road: String(c.route || '').trim(),
                 county: cty.replace(/<[^>]*>[\s\S]*$/, '').replace(/\s*County\s*$/i, '').trim(), dir: '', img: src[1].replace(/&amp;/g, '&'), lat: +ll[1], lon: +ll[2] });
    }
    return out;
  } },
  al: { url: 'https://api.algotraffic.com/v4.0/Cameras', attr: 'ALDOT ALGO Traffic', page: 'https://algotraffic.com/', trim: (raw) => {
    const out = [];
    for (const c of Array.isArray(raw) ? raw : []) {
      if (!c || (c.accessLevel && c.accessLevel !== 'Public')) continue;
      const L = c.location || {};
      out.push({ id: c.id, title: [L.displayRouteDesignator, L.displayCrossStreet ? '@ ' + L.displayCrossStreet : ''].filter(Boolean).join(' ') + (L.city ? ', ' + L.city : ''), road: L.displayRouteDesignator || '',
                 dir: L.direction || '', county: L.county || '', img: c.snapshotImageUrl || c.mapImageUrl || '', video: c.playbackUrls && c.playbackUrls.hls || '', lat: +L.latitude, lon: +L.longitude, page: c.permLink || '' });
    }
    return out;
  } },
  or: { url: 'https://tripcheck.com/Scripts/map/data/cctvinventory.js', text: true, attr: 'ODOT TripCheck', page: 'https://tripcheck.com/', trim: (txt) => {
    const a = txt.indexOf('{'), b = txt.lastIndexOf('}'); if (a < 0 || b < a) return [];
    let j; try { j = JSON.parse(txt.slice(a, b + 1)); } catch { return []; }
    const out = [];
    for (const f of (j && j.features) || []) {
      const x = f && f.attributes || {}; if (!x.filename) continue;
      out.push({ id: x.cameraId + '-' + x.publishedImageId, title: String(x.title || '').trim(), road: String(x.route || '').trim(), img: 'https://tripcheck.com/RoadCams/cams/' + encodeURIComponent(x.filename), lat: +x.latitude, lon: +x.longitude });
    }
    return out;
  } },
  sd: { url: 'https://sd.cdn.iteris-atis.com/geojson/icons/metadata/icons.cameras.geojson', attr: 'South Dakota DOT', page: 'https://sd511.org/', trim: (raw) => {
    const out = [];
    for (const f of (raw && raw.features) || []) {
      const p = f && f.properties || {}, xy = f && f.geometry && f.geometry.coordinates || [];
      for (const c of p.cameras || []) out.push({ id: f.id + '-' + c.id, title: String(c.description || p.name || '').trim(), road: String(p.route || '').trim(), img: c.image || '', lat: +xy[1], lon: +xy[0] });
    }
    return out;
  } }
};
async function dotList(st, ctx) {
  const S = DOT_SRC[st], now = Date.now(), m = dotMem[st], keep = S.keep || DOT_KEEP_MS;
  if (m && now - m.at < keep) return m.list;
  const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null, cacheKey = new Request('https://nws-terminal.internal/dotcams/' + st);
  const hit = cache ? await cache.match(cacheKey) : null;
  if (hit) { const at = Number(hit.headers.get('X-Fetched-At')) || 0; if (now - at < keep) { try { const list = await hit.json(); dotMem[st] = { at, list }; return list; } catch { /* read it fresh */ } } }
  const one = async (url, text) => {
    let res;
    try { res = await fetch(url, { headers: { Accept: text ? '*/*' : 'application/json', 'User-Agent': UA }, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) }); }
    catch (err) { throw Object.assign(new Error('no answer' + (err && err.message ? ': ' + String(err.message).slice(0, 80) : '')), { status: err && err.name === 'TimeoutError' ? 504 : 502 }); }
    if (!res.ok) throw Object.assign(new Error('refused'), { status: res.status });
    try { return text ? await res.text() : await res.json(); } catch { return null; }
  };
  let raw;
  try { raw = S.urls ? await Promise.all(S.urls.map((url, i) => one(url, S.text && S.text[i]))) : await one(S.url, S.text); }   // v3.88.0: a source may need two files
  catch (err) { if (m) return m.list; throw err; }
  const list = (S.trim(raw) || []).filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lon) && Math.abs(c.lat) <= 90 && Math.abs(c.lon) <= 180 && !(c.lat === 0 && c.lon === 0) && /^https?:\/\//i.test(c.img));
  if (!list.length) { if (m) return m.list; throw Object.assign(new Error('no list'), { status: 502 }); }
  dotMem[st] = { at: now, list };
  if (cache && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(cacheKey, new Response(JSON.stringify(list), { status: 200, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=' + Math.round(keep / 1000), 'X-Fetched-At': String(now) } })));
  return list;
}
async function dotcams(request, env, ctx) {
  const NS = { 'Cache-Control': 'no-store' };
  if (request.method !== 'GET') return json({ error: 'Method not allowed' }, 405, NS);
  if (!isSameOriginRead(request)) return json({ error: 'This route only answers the app itself.' }, 401, NS);
  if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401, NS);
  const u = new URL(request.url), st = u.searchParams.get('st'), lat = Number(u.searchParams.get('lat')), lon = Number(u.searchParams.get('lon')), bx = camBox(u);
  if (!DOT_SRC[st]) return json({ error: 'Unknown camera source' }, 400, NS);
  if (bx) {   // v3.89.0: every camera in a box, for the maps
    let all; try { all = await dotList(st, ctx); }
    catch (err) { return json({ error: DOT_SRC[st].attr + ' cameras are unavailable' + (err && err.status ? ' (' + err.status + ').' : '.') }, 502, NS); }
    const inside = all.filter((c) => inCamBox(c, bx));
    return json({ total: inside.length, cams: inside.slice(0, 5000).map((c) => Object.assign({ attr: DOT_SRC[st].attr, page: c.page || DOT_SRC[st].page }, c)) }, 200, NS);
  }
  if (!u.searchParams.get('lat') || !u.searchParams.get('lon') || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return json({ error: 'lat/lon required' }, 400, NS);
  const r = Math.min(350, Math.max(1, Math.round(Number(u.searchParams.get('r')) || 50))), limit = Math.min(80, Math.max(1, Math.round(Number(u.searchParams.get('limit')) || 40)));
  let list;
  try { list = await dotList(st, ctx); }
  catch (err) { return json({ error: DOT_SRC[st].attr + ' cameras are unavailable' + (err && err.status ? ' (' + err.status + (err.message ? ', ' + err.message : '') + ').' : '.') }, 502, NS); }
  const rad = Math.PI / 180, km = (la, lo) => { const a = Math.sin((la - lat) * rad / 2) ** 2 + Math.cos(lat * rad) * Math.cos(la * rad) * Math.sin((lo - lon) * rad / 2) ** 2; return 12742 * Math.asin(Math.sqrt(a)); };
  const near = list.map((c) => ({ c, d: km(c.lat, c.lon) })).filter((x) => x.d <= r).sort((a, b) => a.d - b.d);
  return json({ radiusKm: r, total: near.length, more: near.length > limit, cams: near.slice(0, limit).map((x) => Object.assign({ attr: DOT_SRC[st].attr, page: x.c.page || DOT_SRC[st].page }, x.c)) }, 200, NS);
}

/* ---- Wisconsin 511 winter road conditions (v3.71.0) ----
   The same developer API and key as the cameras. It hands back every reported segment in the state, each with WisDOT's
   condition (Normal, Partially Covered, Completely Covered, Travel Not Advised, No Report) and its geometry as an encoded
   polyline. Read at most once in ten minutes (the API allows ten calls a minute, shared with the cameras), decoded and
   thinned here, and kept; each request is then answered with the segments that reach a box around the point. */
let wrMem = null;   // { at, list }
function polyDecode(s) {
  const out = []; let i = 0, lat = 0, lon = 0;
  while (i < s.length) {
    let b, sh = 0, r = 0; do { b = s.charCodeAt(i++) - 63; r |= (b & 31) << sh; sh += 5; } while (b >= 32 && i < s.length); lat += r & 1 ? ~(r >> 1) : r >> 1;
    sh = 0; r = 0; do { b = s.charCodeAt(i++) - 63; r |= (b & 31) << sh; sh += 5; } while (b >= 32 && i < s.length); lon += r & 1 ? ~(r >> 1) : r >> 1;
    out.push([lat / 1e5, lon / 1e5]);
  }
  return out;
}
function wrTrim(raw) {
  const list = Array.isArray(raw) ? raw : raw && Array.isArray(raw.WinterRoads) ? raw.WinterRoads : raw && typeof raw === 'object' ? [raw] : [], out = [];
  for (const c of list) {
    if (!c || typeof c !== 'object') continue;
    let cond = String(c['Overall Condition'] || c.Condition || c['Primary Condition'] || c.PrimaryCondition || c['Primary-Condition'] || c['Overall Status'] || c.OverallStatus || c.RoadCondition || c.SurfaceCondition || '').trim();
    if (!cond) for (const k of Object.keys(c)) if (/condition|status/i.test(k) && typeof c[k] === 'string' && c[k].trim()) { cond = c[k].trim(); break; }   // whatever this feed calls it
    cond = cond.slice(0, 40);
    const enc = [].concat(c.Polyline || c.EncodedPolyline || []).filter((x) => typeof x === 'string' && x.length > 3);
    const lines = [], b = [180, 90, -180, -90];
    for (const e of enc) {
      let pts; try { pts = polyDecode(e); } catch { continue; }
      const keep = [], rd = (p) => [Math.round(p[0] * 1e4) / 1e4, Math.round(p[1] * 1e4) / 1e4]; let last = null, li = -1;
      pts.forEach((p, k) => { if (!(Math.abs(p[0]) <= 90 && Math.abs(p[1]) <= 180)) return; if (last && Math.abs(p[0] - last[0]) < 0.002 && Math.abs(p[1] - last[1]) < 0.002) return; keep.push(rd(p)); last = p; li = k; });
      if (li >= 0 && li < pts.length - 1) keep.push(rd(pts[pts.length - 1]));   // the segment still ends where it ends
      if (keep.length < 2) continue;
      for (const p of keep) { b[0] = Math.min(b[0], p[1]); b[1] = Math.min(b[1], p[0]); b[2] = Math.max(b[2], p[1]); b[3] = Math.max(b[3], p[0]); }
      lines.push(keep);
    }
    if (!lines.length) continue;
    out.push({ c: cond, road: String(c.RoadwayName || c.Roadway || '').trim().slice(0, 60), loc: String(c.LocationDescription || c.Location || '').trim().slice(0, 140),
               area: String(c.AreaName || '').trim().slice(0, 40), sf: typeof c.RoadSurface === 'string' ? c.RoadSurface.trim().slice(0, 60) : '', t: Number(c.LastUpdated) || 0, lines, b });
  }
  return out;
}
async function wrList(env, ctx) {
  const now = Date.now();
  if (wrMem && now - wrMem.at < WI_KEEP_MS) return wrMem.list;
  const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null, cacheKey = new Request(WI511 + '/api/v2/get/winterroads?format=json');   // the key is left out of what is stored
  const hit = cache ? await cache.match(cacheKey) : null;
  if (hit) { try { const list = await hit.json(); if (Array.isArray(list)) { wrMem = { at: Number(hit.headers.get('X-Fetched-At')) || now, list }; return list; } } catch { /* read it again below */ } }
  const stop = (status, why) => { const e = new Error(why); e.status = status; return e; };   // never carries the address, which holds the key
  const ask = (p) => fetch(WI511 + p + '?key=' + encodeURIComponent(env.WI511_KEY) + '&format=json', { headers: { Accept: 'application/json', 'User-Agent': UA }, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
  let res;
  try { res = await ask('/api/v2/get/winterroads'); if (res.status === 404) res = await ask('/api/getwinterroadconditions'); }   // the newer address, then the documented older one
  catch (err) { if (wrMem) return wrMem.list; throw stop(err && err.name === 'TimeoutError' ? 504 : 502, 'no answer'); }
  if (!res.ok) { if (wrMem && res.status !== 401 && res.status !== 403) return wrMem.list; throw stop(res.status, 'refused'); }
  let raw = null; try { raw = await res.json(); } catch { raw = null; }
  if (!raw) { if (wrMem) return wrMem.list; throw stop(502, 'no list'); }
  const list = wrTrim(raw), first = Array.isArray(raw) ? raw[0] : raw;
  list.fields = first && typeof first === 'object' ? Object.keys(first).slice(0, 30) : [];   // field names only, to tell an empty report from a renamed field
  wrMem = { at: now, list, fields: list.fields };
  if (cache && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(cacheKey, new Response(JSON.stringify(list), { status: 200, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=600', 'X-Fetched-At': String(now) } })));
  return list;
}
async function wiroads(request, env, ctx) {
  const NS = { 'Cache-Control': 'no-store' };
  if (request.method !== 'GET') return json({ error: 'Method not allowed' }, 405, NS);
  if (!env.WI511_KEY) return json({ error: 'No Wisconsin 511 key on the server. Add the WI511_KEY secret in Cloudflare.' }, 401, NS);
  if (!isSameOriginRead(request)) return json({ error: 'This route only answers the app itself.' }, 401, NS);
  if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401, NS);
  const u = new URL(request.url), q = ['w', 's', 'e', 'n'].map((k) => Number(u.searchParams.get(k)));
  if (q.some((x) => !Number.isFinite(x)) || q[0] >= q[2] || q[1] >= q[3] || q[2] - q[0] > 12 || q[3] - q[1] > 8) return json({ error: 'w, s, e and n (a box up to 12 by 8 degrees) required' }, 400, NS);
  if (q[2] < -93.0 || q[0] > -86.6 || q[3] < 42.4 || q[1] > 47.4) return json({ total: 0, segs: [], at: 0 }, 200, NS);   // the box does not reach Wisconsin
  let list;
  try { list = await wrList(env, ctx); }
  catch (err) {
    const s = err && err.status;
    if (s === 401 || s === 403) return json({ error: 'Wisconsin 511 did not accept the key in WI511_KEY.' }, 401, NS);
    if (s === 429) return json({ error: 'Wisconsin 511 allows ten requests a minute and that was reached. Try again shortly.' }, 429, NS);
    if (s === 504) return json({ error: 'Wisconsin 511 did not answer in time.' }, 504, NS);
    return json({ error: 'Wisconsin 511 road conditions are unavailable' + (s ? ' (' + s + ').' : '.') }, 502, NS);
  }
  const segs = list.filter((x) => !(x.b[2] < q[0] || x.b[0] > q[2] || x.b[3] < q[1] || x.b[1] > q[3]));
  return json({ total: segs.length, segs, at: wrMem ? wrMem.at : 0, fields: wrMem && wrMem.fields ? wrMem.fields : undefined }, 200, NS);
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

/* ---- push alerts (v3.83.0) ----
   Web Push to the installed app for the places a device chooses (home plus saved places): NWS warnings, watches and advisories,
   SPC Slight risk or higher at home on Day 1 or 2, and rain or snow starting within about 30 minutes (HRRR 15-minute steps,
   checked against MRMS radar). Needs one KV namespace bound as PUSH, and a timer that POSTs /push/tick every two minutes
   (a small cron Worker). Storage is kept to a few keys so the free KV allowance (1,000 writes a day) is never near:
     vapid  the server's signing key pair, made on first use (never leaves the server; the public half is the app's key)
     subs   every device: endpoint, its two keys, places, which alerts, time zone
     sent   what each device has been sent (alert ids, SPC level per day, last rain notice per place), written only on a send
     beat   when the timer last ran, written at most every 30 minutes
   Pages Functions have no timer of their own, hence the cron Worker. */
const PUSH_HOSTS = /^(([a-z0-9-]+\.)*(googleapis\.com|google\.com)|updates\.push\.services\.mozilla\.com|([a-z0-9-]+\.)*push\.apple\.com|[a-z0-9-]+\.notify\.windows\.com)$/;
const PUSH_MAX_SUBS = 40, PUSH_MAX_PLACES = 16, PUSH_RAIN_COOL = 3 * 3600e3;
const TE = new TextEncoder();
const b64u = (buf) => { const a = new Uint8Array(buf); let s = ''; for (let i = 0; i < a.length; i++) s += String.fromCharCode(a[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); };
const unb64u = (s) => { s = String(s).replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; const b = atob(s); const o = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) o[i] = b.charCodeAt(i); return o; };
const cat = (...a) => { const o = new Uint8Array(a.reduce((q, x) => q + x.length, 0)); let i = 0; for (const x of a) { o.set(x, i); i += x.length; } return o; };

async function vapidKeys(env) {
  let v = await env.PUSH.get('vapid', 'json');
  if (v && v.pub && v.jwk) return v;
  const kp = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
  v = { pub: b64u(await crypto.subtle.exportKey('raw', kp.publicKey)), jwk: await crypto.subtle.exportKey('jwk', kp.privateKey), at: new Date().toISOString() };
  await env.PUSH.put('vapid', JSON.stringify(v));
  return v;
}
async function vapidAuth(v, endpoint, origin) {   // RFC 8292: a signed token the push service checks against the app's public key
  const enc = (o) => b64u(TE.encode(JSON.stringify(o)));
  const unsigned = enc({ typ: 'JWT', alg: 'ES256' }) + '.' + enc({ aud: new URL(endpoint).origin, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: origin });
  const key = await crypto.subtle.importKey('jwk', v.jwk, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, key, TE.encode(unsigned));
  return 'vapid t=' + unsigned + '.' + b64u(sig) + ', k=' + v.pub;
}
async function hkdf(salt, ikm, info, n) {
  const k = await crypto.subtle.importKey('raw', ikm, 'HKDF', false, ['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: 'HKDF', hash: 'SHA-256', salt, info }, k, n * 8));
}
async function pushEncrypt(keys, text) {   // RFC 8291, aes128gcm: only the device can read the message, not the push service
  const ua = unb64u(keys.p256dh), auth = unb64u(keys.auth);
  const eph = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  const asPub = new Uint8Array(await crypto.subtle.exportKey('raw', eph.publicKey));
  const uaKey = await crypto.subtle.importKey('raw', ua, { name: 'ECDH', namedCurve: 'P-256' }, false, []);
  const secret = new Uint8Array(await crypto.subtle.deriveBits({ name: 'ECDH', public: uaKey }, eph.privateKey, 256));
  const ikm = await hkdf(auth, secret, cat(TE.encode('WebPush: info\u0000'), ua, asPub), 32);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, ikm, TE.encode('Content-Encoding: aes128gcm\u0000'), 16);
  const nonce = await hkdf(salt, ikm, TE.encode('Content-Encoding: nonce\u0000'), 12);
  const key = await crypto.subtle.importKey('raw', cek, 'AES-GCM', false, ['encrypt']);
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, key, cat(TE.encode(text), new Uint8Array([2]))));
  const head = new Uint8Array(21); head.set(salt, 0); new DataView(head.buffer).setUint32(16, 4096); head[20] = 65;
  return cat(head, asPub, ct);
}
async function pushSend(v, sub, msg, origin) {   // -> HTTP status from the push service
  const body = await pushEncrypt(sub.k, JSON.stringify(msg));
  const r = await fetch(sub.ep, { method: 'POST', body, signal: AbortSignal.timeout(10000),
    headers: { Authorization: await vapidAuth(v, sub.ep, origin), 'Content-Encoding': 'aes128gcm', 'Content-Type': 'application/octet-stream', TTL: String(msg.ttl || 3600), Urgency: msg.urgent ? 'high' : 'normal' } });
  return r.status;
}
const pushId = async (ep) => (await sha256hex('push:' + ep)).slice(0, 20);
function pushClock(ms, tz, withDay) {
  const o = { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' };
  try { if (tz) o.timeZone = tz; if (withDay) o.weekday = 'short'; return new Date(ms).toLocaleString('en-US', o); }
  catch (e) { delete o.timeZone; return new Date(ms).toLocaleString('en-US', o); }
}
function sameDay(a, b, tz) { const f = (ms) => { try { return new Date(ms).toLocaleDateString('en-US', tz ? { timeZone: tz } : {}); } catch (e) { return new Date(ms).toDateString(); } }; return f(a) === f(b); }
async function cacheLock(name, seconds) {   // true when this call holds the lock (one run per window at this edge location)
  const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null; if (!cache) return true;
  const key = new Request('https://cache.nws-terminal/push-lock/' + name);
  if (await cache.match(key)) return false;
  await cache.put(key, new Response('1', { headers: { 'Cache-Control': 'public, max-age=' + seconds } }));
  return true;
}
const placeKey = (p) => (+p.la).toFixed(2) + ',' + (+p.lo).toFixed(2);
const placeUrl = (origin, p, s) => origin + '/#loc=' + encodeURIComponent(p.n) + (s ? '&s=' + s : '');

/* ---- NWS alerts ---- */
function alertGroup(ev) { return /(Warning|Emergency)$/i.test(ev) ? 'warn' : /(Watch|Advisory)$/i.test(ev) ? 'watch' : null; }
function alertTag(p) {   // what an update must add to be sent again: tornado seen, a higher damage threat
  const q = (k) => String((p && p[k] && p[k][0]) || '').toUpperCase();
  return [q('tornadoDetection'), q('tornadoDamageThreat'), q('thunderstormDamageThreat'), q('flashFloodDamageThreat')].join('|');
}
const TAG_RANK = { '': 0, POSSIBLE: 1, 'RADAR INDICATED': 1, OBSERVED: 2, BASE: 1, CONSIDERABLE: 2, DESTRUCTIVE: 2, CATASTROPHIC: 3 };
function escalated(was, now) { const a = String(was || '').split('|'), b = now.split('|'); return b.some((x, i) => (TAG_RANK[x] || 0) > (TAG_RANK[a[i] || ''] || 0)); }
function alertText(a, tz, now) {
  const p = a.properties || {}, end = Date.parse(p.ends || p.expires || ''), t = alertTag(p).split('|');
  const lead = t[0] === 'OBSERVED' ? 'Tornado observed. ' : t[1] === 'CATASTROPHIC' ? 'Tornado emergency. ' : t[1] === 'CONSIDERABLE' ? 'Particularly dangerous situation. ' : t[2] === 'DESTRUCTIVE' ? 'Destructive winds or hail. ' : '';
  const until = isFinite(end) ? 'Until ' + pushClock(end, tz, !sameDay(end, now, tz)) + '. ' : '';
  const d = String(p.description || '');
  const m = d.match(/\*\s*(At \d{1,4} [AP]M [A-Z]{3,4},[\s\S]*?)(?:\n\s*\n|$)/) || d.match(/\*\s*WHAT\.\.\.([\s\S]*?)(?:\n\s*\n|\n\s*\*|$)/);
  let say = m ? m[1] : String((p.parameters && p.parameters.NWSheadline && p.parameters.NWSheadline[0]) || '');
  say = say.replace(/\s+/g, ' ').trim();
  if (say && say === say.toUpperCase()) say = say.charAt(0) + say.slice(1).toLowerCase();   // the all-capitals headline, as a sentence
  if (!say) say = String(p.areaDesc || '').slice(0, 160);
  if (say && !/[.!]$/.test(say)) say += '.';
  const all = lead + until + say; return all.length <= 300 ? all : all.slice(0, 297).replace(/\s+\S*$/, '') + '…';
}

/* ---- SPC Day 1 and 2 at a point (the categorical layers' own point query: a few hundred bytes) ---- */
const SPC_SVC = 'https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/SPC_wx_outlks/MapServer/';
const SPC_WORD = { 2: 'thunderstorms', 3: 'Marginal risk', 4: 'Slight risk', 5: 'Enhanced risk', 6: 'Moderate risk', 8: 'High risk' }, SPC_LEVEL = { 3: 1, 4: 2, 5: 3, 6: 4, 8: 5 };
async function spcAt(p, layer) {
  const u = SPC_SVC + layer + '/query?geometry=' + (+p.lo).toFixed(4) + ',' + (+p.la).toFixed(4) + '&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=dn,valid,expire,issue&returnGeometry=false&f=json';
  const r = await fetch(u, { headers: { 'User-Agent': UA, Accept: 'application/json' }, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
  const j = await r.json(); if (!r.ok || j.error) throw new Error('SPC point query failed');
  let best = null; for (const f of j.features || []) { const a = f.attributes || {}; if (!best || +a.dn > +best.dn) best = a; }
  return best;   // null: outside every area
}
const spcDay = (a) => { const e = String(a.expire || ''); const d = new Date(Date.UTC(+e.slice(0, 4), +e.slice(4, 6) - 1, +e.slice(6, 8)) - 864e5); return d.toISOString().slice(0, 10); };   // the convective day the outlook covers
const spcMs = (s) => { s = String(s || ''); return Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8), +s.slice(8, 10), +s.slice(10, 12)); };

/* ---- rain or snow starting: HRRR 15-minute steps, with MRMS radar as the check that it has not already started ---- */
const PX_V = [['PRATE', 'surface', 'pr'], ['REFD', '1000 m above ground', 'd'], ['CSNOW', 'surface', 'sn'], ['CRAIN', 'surface', 'ra'], ['CFRZR', 'surface', 'fz'], ['CICEP', 'surface', 'pl']].map((x) => ({ name: x[0], level: x[1], alias: x[2] }));
async function gsRows(env, model, body) {
  const r = await fetch(GS_ORIGIN + '/api/v2/' + model + '/timeseries', { method: 'POST', body: JSON.stringify(body), signal: AbortSignal.timeout(25000),
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', Authorization: 'Bearer ' + env.GS_TOKEN, 'User-Agent': UA } });
  if (!r.ok) throw new Error(model + ' HTTP ' + r.status);
  const j = await r.json(); if (!Array.isArray(j)) throw new Error(model + ' answered no rows'); return j;
}
function pxKind(f) { return f.fz ? 'freezing rain' : f.pl ? 'sleet' : f.sn && f.ra ? 'rain and snow' : f.sn ? 'snow' : f.ra ? 'rain' : 'rain or snow'; }
function pxStart(rows, now) {   // -> { t, kind, peak, run } when the model starts it within about 30 minutes, else null
  const by = {};
  for (const r of rows) { const t = Date.parse(r.forecasted_time); if (!isFinite(t)) continue; const x = by[t] || (by[t] = { t, run: 0 }); for (const v of PX_V) if (r[v.alias] != null && isFinite(+r[v.alias])) x[v.alias] = +r[v.alias]; const ra = Date.parse(r.forecasted_at); if (ra > x.run) x.run = ra; }
  const F = Object.values(by).sort((a, b) => a.t - b.t).filter((x) => x.t >= now - 450e3).map((x) => {
    const r = x.pr != null ? x.pr * 3600 / 25.4 : 0, flag = x.sn || x.ra || x.fz || x.pl;
    return { t: x.t, run: x.run, r, k: pxKind(x), wet: r >= 0.01 || (!!flag && x.d != null && x.d >= 15) };
  });
  if (F.length < 3 || now - Math.max(...F.map((f) => f.run)) > 3 * 3600e3) return null;
  if (F[0].wet && F[0].t <= now) return null;   // the model has it already falling: nothing is starting
  for (let i = 0; i < F.length; i++) {
    const f = F[i]; if (!f.wet) continue;
    if (f.t > now + 2250e3) return null;   // first rain is more than about 37 minutes out
    if (f.r < 0.03 && !(F[i + 1] && F[i + 1].wet)) continue;   // a lone light blip
    const ahead = F.slice(i, i + 4).filter((g) => g.wet), peak = Math.max(...ahead.map((g) => g.r));
    return { t: Math.max(f.t, now), kind: f.k, peak, run: f.run };
  }
  return null;
}
const pxRate = (r) => (r >= 0.3 ? 'heavy' : r >= 0.1 ? 'moderate' : 'light');

async function pushTick(env, origin, force) {
  if (!env.PUSH) return { ok: false, error: 'No PUSH storage bound.' };
  if (!force && !(await cacheLock('tick', 80))) return { ok: true, skipped: 'ran less than 80 seconds ago' };
  const now = Date.now(), out = { ok: true, at: new Date(now).toISOString(), subs: 0, places: 0, sent: 0, gone: 0, checks: [] };
  const beat = await env.PUSH.get('beat', 'json');
  if (!beat || now - Date.parse(beat.at) > 30 * 60e3) await env.PUSH.put('beat', JSON.stringify({ at: out.at }));
  const subs = (await env.PUSH.get('subs', 'json')) || {}, ids = Object.keys(subs); out.subs = ids.length;
  if (!ids.length) return out;
  const sent = (await env.PUSH.get('sent', 'json')) || {}, v = await vapidKeys(env);
  let dirtySent = false, dirtySubs = false;
  const P = {};   // every distinct place across devices
  for (const id of ids) for (const p of subs[id].places || []) { const k = placeKey(p); (P[k] || (P[k] = { la: +p.la, lo: +p.lo })); }
  out.places = Object.keys(P).length;
  const queue = [];   // [id, message]
  const st = (id) => sent[id] || (sent[id] = { a: {}, s: {}, r: {} });

  // 1. NWS alerts, every run
  const wantA = ids.some((id) => subs[id].on && (subs[id].on.warn || subs[id].on.watch));
  if (wantA) {
    await Promise.all(Object.keys(P).map(async (k) => {
      try {
        const r = await fetch('https://api.weather.gov/alerts/active?point=' + P[k].la.toFixed(4) + ',' + P[k].lo.toFixed(4), { headers: { 'User-Agent': UA, Accept: 'application/geo+json' }, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        P[k].alerts = ((await r.json()).features || []).filter((f) => f && f.properties && f.properties.status === 'Actual');
      } catch (e) { P[k].alertErr = String(e.message || e).slice(0, 60); }
    }));
    out.checks.push('alerts');
    for (const id of ids) {
      const s = subs[id], on = s.on || {}, me = st(id);
      for (const p of s.places || []) {
        const list = P[placeKey(p)].alerts; if (!list) continue;
        for (const a of list) {
          const pr = a.properties, aid = pr.id || a.id, g = alertGroup(pr.event || ''); if (!aid || !g || !on[g] || me.a[aid + '@' + placeKey(p)]) continue;
          const end = Date.parse(pr.ends || pr.expires || ''), tag = alertTag(pr), key = aid + '@' + placeKey(p);
          me.a[key] = { x: isFinite(end) ? end : now + 6 * 3600e3, g: tag }; dirtySent = true;
          const hl = String((pr.parameters && pr.parameters.NWSheadline && pr.parameters.NWSheadline[0]) || '');
          if (pr.messageType === 'Cancel' || (isFinite(end) && end < now) || /CANCELL?ED|HAS EXPIRED|WILL EXPIRE/i.test(hl)) continue;
          const refs = (pr.references || []).map((x) => (x.identifier || x['@id'] || '') + '@' + placeKey(p)), prior = refs.map((x) => me.a[x]).filter(Boolean);
          if (prior.length && !prior.some((x) => escalated(x.g, tag))) continue;   // an update with nothing new
          queue.push([id, { title: pr.event + ' · ' + p.n, body: alertText(a, s.tz, now), tag: 'a:' + pr.event + ':' + placeKey(p), renotify: true, urgent: g === 'warn', sticky: /Tornado|Extreme Wind|Flash Flood Emergency/.test(pr.event) && g === 'warn',
                               url: placeUrl(origin, p, 'alerts'), ttl: Math.max(600, Math.min(86400, Math.round(((isFinite(end) ? end : now + 3600e3) - now) / 1000))) }]);
        }
      }
    }
  }

  // 2. SPC Slight or higher at home, Day 1 and 2, every 15 minutes
  const homes = ids.filter((id) => subs[id].on && subs[id].on.spc).map((id) => [id, (subs[id].places || []).find((p) => p.home)]).filter((x) => x[1]);
  if (homes.length && (force || await cacheLock('spc', 900))) {
    out.checks.push('spc');
    const H = {};
    await Promise.all(homes.map(async ([, p]) => { const k = placeKey(p); if (H[k]) return; H[k] = {}; try { const r = await Promise.all([spcAt(p, 1), spcAt(p, 9)]); H[k] = { d1: r[0], d2: r[1] }; } catch (e) { H[k] = { err: true }; } }));
    for (const [id, p] of homes) {
      const h = H[placeKey(p)], me = st(id), tz = subs[id].tz;
      for (const [dd, a] of [[1, h.d1], [2, h.d2]]) {
        if (!a || +a.dn < 4 || !SPC_LEVEL[+a.dn]) continue;
        const day = spcDay(a), sk = day + '@' + placeKey(p); if ((me.s[sk] || 0) >= +a.dn) continue;
        me.s[sk] = +a.dn; dirtySent = true;
        const start = spcMs(a.valid), when = sameDay(Math.max(start, now), now, tz) ? 'today' : sameDay(Math.max(start, now), now + 864e5, tz) ? 'tomorrow' : 'Day ' + dd;
        queue.push([id, { title: SPC_WORD[+a.dn] + ' of severe storms ' + when + ' · ' + p.n, body: 'SPC Day ' + dd + ' outlook, level ' + SPC_LEVEL[+a.dn] + ' of 5, issued ' + pushClock(spcMs(a.issue), tz) + '.',
                             tag: 'spc:' + day, renotify: true, urgent: +a.dn >= 5, url: placeUrl(origin, p, 'spc'), ttl: 12 * 3600 }]);
      }
    }
  }

  // 3. rain or snow starting within about 30 minutes, every 10 minutes
  const rainers = ids.filter((id) => subs[id].on && subs[id].on.rain);
  if (rainers.length && env.GS_TOKEN && (force || await cacheLock('rain', 540))) {
    out.checks.push('rain');
    const R = {}; for (const id of rainers) for (const p of subs[id].places || []) { const k = placeKey(p); if (!R[k] && p.la >= 21 && p.la <= 50 && p.lo >= -125 && p.lo <= -66) R[k] = { la: +p.la, lo: +p.lo }; }
    const keys = Object.keys(R).slice(0, 40), coords = keys.map((k) => ({ lat: +R[k].la.toFixed(4), lon: +R[k].lo.toFixed(4), name: k }));
    if (coords.length) {
      try {
        const [hr, mr] = await Promise.all([
          gsRows(env, 'hrrrsubh', { fromTime: new Date(now - 900e3).toISOString(), untilTime: new Date(now + 3600e3).toISOString(), coordinates: coords, variables: PX_V }),
          gsRows(env, 'mrms', { fromTime: new Date(now - 1500e3).toISOString(), untilTime: new Date(now + 300e3).toISOString(), coordinates: coords, variables: [{ name: 'PrecipRate', level: '0 m above mean sea level', alias: 'r' }] }) ]);
        for (const k of keys) {
          const m = mr.filter((x) => x.name === k);
          if (!m.length) continue;   // no radar to check against: say nothing (start stays undefined)
          if (m.some((x) => +x.r >= 0.2)) { R[k].wet = true; continue; }   // already falling there
          R[k].start = pxStart(hr.filter((x) => x.name === k), now);
        }
        out.rain = keys.map((k) => k + ' ' + (R[k].wet ? 'falling' : R[k].start ? 'starting' : R[k].start === null ? 'dry' : 'no radar'));
      } catch (e) { out.rainErr = String(e.message || e).slice(0, 80); }
    }
    for (const id of rainers) {
      const me = st(id), tz = subs[id].tz;
      for (const p of subs[id].places || []) {
        const k = placeKey(p), x = R[k] && R[k].start; if (!x) continue;
        if (now - (me.r[k] || 0) < PUSH_RAIN_COOL) continue;
        me.r[k] = now; dirtySent = true;
        const k2 = x.kind.charAt(0).toUpperCase() + x.kind.slice(1);
        queue.push([id, { title: k2 + ' starting about ' + pushClock(x.t, tz).replace(/ [A-Z]{2,5}$/, '') + ' · ' + p.n,
                          body: pxRate(x.peak).charAt(0).toUpperCase() + pxRate(x.peak).slice(1) + ' at first, by the HRRR ' + pushClock(x.run, tz).replace(/:00/, '') + ' run. Radar shows none there yet.',
                          tag: 'rain:' + k, renotify: true, url: placeUrl(origin, p, 'forecast'), ttl: 1800 }]);
      }
    }
  }

  // send, a few per device per run; endpoints the push service has dropped are forgotten
  const per = {};
  for (const [id, msg] of queue) {
    if ((per[id] = (per[id] || 0) + 1) > 6 || !subs[id]) continue;
    try {
      msg.ts = now; const code = await pushSend(v, subs[id], msg, origin);
      if (code === 404 || code === 410) { delete subs[id]; delete sent[id]; dirtySubs = dirtySent = true; out.gone++; }
      else if (code >= 200 && code < 300) out.sent++;
    } catch (e) { /* the next run tries again only for new items; a missed send is not retried */ }
  }
  // forget expired alert ids and old SPC days
  for (const id of Object.keys(sent)) {
    if (!subs[id]) { delete sent[id]; dirtySent = true; continue; }
    const me = sent[id];
    for (const k of Object.keys(me.a || {})) if (me.a[k].x < now - 3600e3) { delete me.a[k]; dirtySent = true; }
    for (const k of Object.keys(me.s || {})) if (Date.parse(k.slice(0, 10)) < now - 3 * 864e5) { delete me.s[k]; dirtySent = true; }
  }
  if (dirtySubs) await env.PUSH.put('subs', JSON.stringify(subs));
  if (dirtySent) await env.PUSH.put('sent', JSON.stringify(sent));
  return out;
}

function cleanPlaces(list) {
  const out = [], seen = {};
  for (const p of Array.isArray(list) ? list : []) {
    const la = +p.la, lo = +p.lo, n = String(p.n || '').replace(/[\u0000-\u001f<>]/g, '').slice(0, 60).trim();
    if (!n || !isFinite(la) || !isFinite(lo) || la < 10 || la > 72 || lo < -180 || lo > -60) continue;
    const k = placeKey({ la, lo }); if (seen[k]) { if (p.home) out.find((q) => placeKey(q) === k).home = true; continue; }
    seen[k] = 1; out.push({ n, la: +la.toFixed(4), lo: +lo.toFixed(4), home: !!p.home });
    if (out.length >= PUSH_MAX_PLACES) break;
  }
  if (out.filter((p) => p.home).length > 1) { let f = false; for (const p of out) { if (p.home && f) p.home = false; if (p.home) f = true; } }
  return out;
}
async function pushRoute(path, request, env) {
  const NS = { 'Cache-Control': 'no-store' }, origin = new URL(request.url).origin;
  if (path === '/push/tick') {
    if (request.method !== 'POST') return json({ error: 'POST only' }, 405, NS);
    if (!env.PUSH) return json({ ok: false, error: 'No PUSH storage bound to this site yet.' }, 503, NS);
    return json(await pushTick(env, origin, false), 200, NS);
  }
  if (path === '/push/key') {
    if (!isSameOriginRead(request)) return json({ error: 'This route only answers the app itself.' }, 401, NS);
    if (!(await unlocked(request, env))) return json({ error: 'Locked. Enter the access code in Settings.' }, 401, NS);
    if (!env.PUSH) return json({ ready: false, why: 'storage' }, 200, NS);
    const [v, beat] = await Promise.all([vapidKeys(env), env.PUSH.get('beat', 'json')]);
    return json({ ready: true, key: v.pub, beat: beat && beat.at || null, rain: !!env.GS_TOKEN }, 200, NS);
  }
  const bad = await keyGuard(request, env); if (bad) return bad;
  if (request.method !== 'POST') return json({ error: 'POST only' }, 405, NS);
  if (!env.PUSH) return json({ ok: false, error: 'No PUSH storage bound to this site yet.' }, 503, NS);
  const raw = await request.text(); if (raw.length > 16384) return json({ error: 'Too large' }, 413, NS);
  let b; try { b = JSON.parse(raw); } catch (e) { return json({ error: 'Bad JSON' }, 400, NS); }
  const ep = String(b && (b.endpoint || (b.sub && b.sub.endpoint)) || '');
  let host = ''; try { const u = new URL(ep); host = u.protocol === 'https:' ? u.hostname : ''; } catch (e) { host = ''; }
  if (!PUSH_HOSTS.test(host)) return json({ error: 'Not a push service address.' }, 400, NS);
  const id = await pushId(ep), subs = (await env.PUSH.get('subs', 'json')) || {};
  if (path === '/push/sub') {
    const k = b.sub && b.sub.keys || {};
    if (!/^[A-Za-z0-9_-]{80,100}$/.test(k.p256dh || '') || !/^[A-Za-z0-9_-]{16,32}$/.test(k.auth || '')) return json({ error: 'Missing subscription keys.' }, 400, NS);
    if (!subs[id] && Object.keys(subs).length >= PUSH_MAX_SUBS) return json({ error: 'Too many devices.' }, 429, NS);
    const on = b.on || {}, tz = /^[A-Za-z_]+(\/[A-Za-z0-9_+-]+){0,2}$/.test(b.tz || '') ? b.tz : 'America/Chicago';
    subs[id] = { ep, k: { p256dh: k.p256dh, auth: k.auth }, places: cleanPlaces(b.places), on: { warn: !!on.warn, watch: !!on.watch, spc: !!on.spc, rain: !!on.rain }, tz, at: new Date().toISOString() };
    await env.PUSH.put('subs', JSON.stringify(subs));
    return json({ ok: true, id, places: subs[id].places.length }, 200, NS);
  }
  if (path === '/push/unsub') {
    if (subs[id]) { delete subs[id]; await env.PUSH.put('subs', JSON.stringify(subs)); }
    return json({ ok: true }, 200, NS);
  }
  if (path === '/push/test') {
    const s = subs[id]; if (!s) return json({ error: 'This device is not signed up yet.' }, 404, NS);
    if (!(await cacheLock('test-' + id, 20))) return json({ error: 'One test every 20 seconds.' }, 429, NS);
    const home = s.places.find((p) => p.home) || s.places[0];
    const code = await pushSend(await vapidKeys(env), s, { title: 'NWS Terminal test', body: 'Alerts are on for ' + s.places.length + ' place' + (s.places.length === 1 ? '' : 's') + (home ? ', home ' + home.n : '') + '. Sent ' + pushClock(Date.now(), s.tz) + '.', tag: 'test', url: origin + '/', ttl: 600, ts: Date.now() }, origin);
    if (code === 404 || code === 410) { delete subs[id]; await env.PUSH.put('subs', JSON.stringify(subs)); return json({ error: 'The push service dropped this device. Turn alerts off and on again.' }, 410, NS); }
    return json({ ok: code >= 200 && code < 300, status: code }, code >= 200 && code < 300 ? 200 : 502, NS);
  }
  return json({ error: 'Unknown push route' }, 404, NS);
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
    if (path === '/api/wicams') {
      try { return await wicams(request, env, ctx); }
      catch (err) { return json({ error: 'Wisconsin 511 request failed.' }, err && err.name === 'TimeoutError' ? 504 : 502, { 'Cache-Control': 'no-store' }); }   // no detail: an upstream address would carry the key
    }
    if (path === '/api/dotcams') {   // v3.86.0
      try { return await dotcams(request, env, ctx); }
      catch (err) { return json({ error: 'Road cameras are unavailable.' }, 502, { 'Cache-Control': 'no-store' }); }
    }
    if (path === '/api/wiroads') {   // v3.71.0
      try { return await wiroads(request, env, ctx); }
      catch (err) { return json({ error: 'Wisconsin 511 request failed.' }, err && err.name === 'TimeoutError' ? 504 : 502, { 'Cache-Control': 'no-store' }); }
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
    if (path.startsWith('/push/')) {   // v3.83.0
      try { return await pushRoute(path, request, env); }
      catch (err) { return json({ error: 'Push request failed: ' + String(err && err.message || err).slice(0, 120) }, 502, { 'Cache-Control': 'no-store' }); }
    }
    if (path === '/api/unlock') return unlock(request, env);
    if (path === '/api/config') {
      return json({ gsServerToken: !!env.GS_TOKEN, lightningServerKey: !!env.LIGHTNING_KEY, radarServerKey: !!env.RADAR_TILES_KEY, camsServerKey: !!env.WINDY_WEBCAMS_KEY, wi511ServerKey: !!env.WI511_KEY, claudeServerKey: !!env.ANTHROPIC_API_KEY, wethrServerKey: !!env.WETHR_API_KEY, pushStore: !!env.PUSH,
                    passcode: !!env.APP_PASSCODE, locked: !(await unlocked(request, env)), version: VERSION }, 200, { 'Cache-Control': 'no-store' });
    }
    if (path === '/api/health') {
      return json({ ok: true, version: VERSION, time: new Date().toISOString() }, 200, { 'Cache-Control': 'no-store' });
    }

    const res = await env.ASSETS.fetch(request);
    return securityHeaders(res, url);
  },
};
