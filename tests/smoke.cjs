/* NWS Terminal screen tests (v3.84.0).

   Opens the app in a real browser and walks it the way a person would: the US map, then a place, then every section, a few
   maps, Settings, three screen sizes. It fails on what is always a bug and never on the weather:
     - a script error (uncaught exception or promise), including anything the app's own error reporter picks up
     - a section that comes up blank or will not show
     - a page wider than the screen (sideways scroll)
     - the browser refusing something under the site's content rules
     - the wrong version on screen
   A data source being slow or down is a warning, not a failure.

   Run it against a deployed address:
       node tests/smoke.cjs --base https://nws4.pages.dev
   or against the files in this folder, laid over the live site so its data routes still answer (page changes only; a
   change to _worker.js needs a preview address):
       node tests/smoke.cjs --local .
   Options: --place "City, ST"   --out DIR (screenshots, report.json)   --maps all   --quick (one screen size)
   Needs the 'playwright' package and its Chromium (npx playwright install chromium). Exit code 1 means do not ship. */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require('playwright');

const arg = (name, dflt) => { const i = process.argv.indexOf('--' + name); return i < 0 ? dflt : (process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : true); };
const BASE = String(arg('base', 'https://nws4.pages.dev')).replace(/\/+$/, '');
const LOCAL = arg('local', null) ? path.resolve(String(arg('local', '.'))) : null;
const PLACE = String(arg('place', 'Oconomowoc, WI'));
const OUT = path.resolve(String(arg('out', 'smoke-out')));
const QUICK = !!arg('quick', false), ALL_MAPS = arg('maps', '') === 'all';
const WANT = arg('expect', null);   // a version the page must show (CI passes the one in _worker.js)

const VIEWS = [
  { name: 'ipad', width: 1366, height: 1024, touch: true, full: true },
  { name: 'ipad-portrait', width: 1024, height: 1366, touch: true },
  { name: 'phone', width: 390, height: 844, touch: true, mobile: true },
].slice(0, QUICK ? 1 : 3);
/* Maps that cost nothing to draw (observations and NWS / SPC products). --maps all walks every map on the menu. */
const MAPS = ['temp', 'wind', 'sfcmap', 'alerts', 'fcst', 'tstm'];
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.geojson': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.webmanifest': 'application/manifest+json', '.txt': 'text/plain' };

const fails = [], warns = [], notes = [];
const fail = (where, what) => { fails.push(where + ': ' + what); console.log('  FAIL  ' + where + ': ' + what); };
const warn = (where, what) => { if (warns.length < 60) warns.push(where + ': ' + what); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function localVersion() { try { return (/var APP_VERSION = '([\d.]+)'/.exec(fs.readFileSync(path.join(LOCAL, 'app.js'), 'utf8')) || [])[1] || null; } catch (e) { return null; } }

async function run(browser, view) {
  const ctx = await browser.newContext({ viewport: { width: view.width, height: view.height }, hasTouch: !!view.touch, isMobile: !!view.mobile, deviceScaleFactor: 1,
    serviceWorkers: 'block', timezoneId: 'America/Chicago', locale: 'en-US' });
  const page = await ctx.newPage();
  let at = view.name + ' start', lastNet = Date.now();
  const pending = new Map();   // request -> when it began; live streams and anything older than 15 s do not hold up the walk
  const reported = [];
  const tag = () => view.name + ' / ' + at;

  page.on('pageerror', (e) => fail(tag(), 'script error: ' + String(e && e.message || e).slice(0, 240)));
  page.on('console', (m) => {
    if (m.type() !== 'error') return; const t = m.text();
    if (/Content Security Policy|Refused to (load|execute|connect|apply|frame)/i.test(t)) fail(tag(), 'blocked by the content rules: ' + t.slice(0, 240));
  });
  page.on('request', (r) => { if (r.resourceType() === 'eventsource' || r.resourceType() === 'websocket' || r.resourceType() === 'media') return; pending.set(r, Date.now()); lastNet = Date.now(); });
  const done = (r) => { if (pending.delete(r)) lastNet = Date.now(); };
  page.on('requestfinished', done); page.on('requestfailed', done);
  const busy = () => { const now = Date.now(); let n = 0; pending.forEach((t, r) => { if (now - t > 15000) pending.delete(r); else n++; }); return n; };
  page.on('response', (r) => { const u = r.url(); if (u.startsWith(BASE) && r.status() >= 500) warn(tag(), 'HTTP ' + r.status() + ' from ' + new URL(u).pathname.slice(0, 80)); });

  /* The app's own error reports never leave the test: they are caught here and counted as failures. */
  await page.route(BASE + '/api/err', async (route) => {
    let b = {}; try { b = JSON.parse(route.request().postData() || '{}'); } catch (e) {}
    (b.errs || []).forEach((x) => reported.push(Object.assign({ v: b.v, d: b.d }, x)));
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true,"stored":0,"why":"test"}' });
  });
  if (LOCAL) {
    await page.route((u) => u.origin === BASE && !/^\/(api|p|push)\//.test(u.pathname), async (route) => {
      const u = new URL(route.request().url()); let rel = decodeURIComponent(u.pathname); if (rel === '/') rel = '/index.html';
      const file = path.join(LOCAL, rel);
      if (!file.startsWith(LOCAL) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return route.fulfill({ status: 404, body: 'Not found' });
      await route.fulfill({ status: 200, contentType: TYPES[path.extname(file)] || 'application/octet-stream', body: fs.readFileSync(file) });
    });
    /* The live Worker may be older than these files, so the routes this version adds are answered here. */
    await page.route(BASE + '/api/errors', (route) => route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ version: localVersion(), store: true, day: null, writes: 0, list: [{ id: 'test00000000', k: 'error', m: 'sample <b>error</b> for the test', w: 'app.js:1:1', p: 'radar', d: 'ipad app', v: localVersion(), v0: localVersion(), n: 2, first: new Date().toISOString(), last: new Date().toISOString() }] }) }));
  }

  const settle = async (maxMs) => {   // the page has gone quiet, or enough time has passed
    const t0 = Date.now(); await sleep(350);
    while (Date.now() - t0 < maxMs) { if (busy() === 0 && Date.now() - lastNet > 700) return true; await sleep(150); }
    return false;
  };
  const overflow = async () => {
    const o = await page.evaluate(() => { const d = document.scrollingElement || document.documentElement; return { sw: d.scrollWidth, iw: window.innerWidth }; });
    if (o.sw > o.iw + 2) fail(tag(), 'page is wider than the screen (' + o.sw + ' px against ' + o.iw + ')');
  };
  const shot = async (name) => { try { await page.screenshot({ path: path.join(OUT, view.name + '-' + name + '.jpg'), type: 'jpeg', quality: 60 }); } catch (e) {} };

  /* 1. the opening screen */
  at = 'US map';
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  try { await page.waitForFunction(() => typeof APP_VERSION !== 'undefined' && typeof HOME !== 'undefined' && HOME.on(), null, { timeout: 30000 }); }
  catch (e) {
    fail(tag(), 'the app did not start (app.js did not run, or the US map did not open)');
    try { await page.evaluate(() => window.NWSERR && NWSERR.flush()); await sleep(600); } catch (x) {}
    reported.forEach((x) => fail(tag(), 'the app reported ' + x.k + ': ' + String(x.m).slice(0, 200) + (x.w ? ' (' + x.w + ')' : '')));
    await shot('nostart'); await ctx.close(); return;
  }
  const shown = await page.evaluate(() => ({ v: APP_VERSION, label: (document.getElementById('appVersion') || {}).textContent || '', css: (document.querySelector('link[href^="/app.css"]') || { getAttribute() { return ''; } }).getAttribute('href'),
    js: (document.querySelector('script[src^="/app.js"]') || { getAttribute() { return ''; } }).getAttribute('src') }));
  const want = WANT && WANT !== true ? String(WANT) : LOCAL ? localVersion() : null;
  if (want && shown.v !== want) fail(tag(), 'version on screen is ' + shown.v + ', expected ' + want);
  if (shown.css.indexOf('v=' + shown.v) < 0 || shown.js.indexOf('v=' + shown.v) < 0) fail(tag(), 'index.html asks for ' + shown.js + ' and ' + shown.css + ' but the app says ' + shown.v);
  if (view.full) notes.push('version ' + shown.v);
  await settle(20000);
  const home = await page.evaluate(() => { const h = document.getElementById('homeEl'); return h ? { vis: h.offsetParent !== null || h.getClientRects().length > 0, len: (h.innerText || '').length, gfx: h.querySelectorAll('svg, canvas').length } : null; });
  if (!home || !home.vis) fail(tag(), 'the opening US map is not on screen'); else if (!home.gfx) fail(tag(), 'the opening screen has no map drawn');
  await overflow(); await shot('home');

  /* 2. a place, then every section */
  at = 'load ' + PLACE;
  await page.goto(BASE + '/#loc=' + encodeURIComponent(PLACE) + '&s=forecast', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => { if (!(typeof _lastLoc !== 'undefined' && _lastLoc)) location.reload(); });   // same document, new hash: make sure it boots on the place
  try { await page.waitForFunction(() => typeof _lastLoc !== 'undefined' && !!_lastLoc && typeof currentLat !== 'undefined' && currentLat != null && (document.getElementById('section-forecast').innerText || '').length > 200, null, { timeout: 60000 }); }
  catch (e) { fail(tag(), 'the place did not load within a minute'); await shot('noplace'); await ctx.close(); return; }
  await settle(25000);
  const sections = await page.evaluate(() => SECTIONS.slice());
  const walk = view.full ? sections : ['forecast', 'hourly', 'radar', 'regional'];
  for (const s of walk) {
    if (s === 'satellite') continue;   // one screen with radar since v3.44.0
    at = s;
    const went = await page.evaluate((name) => { try { switchSection(name); } catch (e) { return 'threw: ' + e.message; } return _currentSection; }, s);
    if (went !== s) { if (String(went).startsWith('threw')) fail(tag(), 'switching to it ' + went); else warn(tag(), 'not offered here (landed on ' + went + ')'); continue; }
    const quiet = await settle(s === 'models' || s === 'radar' || s === 'regional' ? 30000 : 18000);
    if (!quiet) warn(tag(), 'still loading after the wait: ' + Array.from(pending.keys()).slice(0, 3).map((r) => { try { const u = new URL(r.url()); return u.hostname + u.pathname.slice(0, 40); } catch (e) { return '?'; } }).join(', '));
    const info = await page.evaluate((name) => { const el = document.getElementById('section-' + name); if (!el) return null; const r = el.getBoundingClientRect();
      return { hidden: el.classList.contains('hidden'), h: Math.round(r.height), len: (el.innerText || '').trim().length, gfx: el.querySelectorAll('svg, canvas, img, iframe').length }; }, s);
    if (!info) fail(tag(), 'no such section in the page');
    else if (info.hidden || info.h < 40) fail(tag(), 'the section is not showing');
    else if (info.len < 30 && !info.gfx) fail(tag(), 'the section is blank');
    await overflow();
    if (view.full) await shot('sec-' + s);
  }

  /* 3. maps */
  if (view.full) {
    at = 'maps'; await page.evaluate(() => switchSection('regional')); await settle(20000);
    const list = ALL_MAPS ? await page.evaluate(() => REGMAP._layers()) : MAPS;
    for (const id of list) {
      at = 'map ' + id;
      const ok = await page.evaluate((layer) => { if (REGMAP._layers().indexOf(layer) < 0) return false; REGMAP._st.layer = layer; REGMAP.again(); return true; }, id);
      if (!ok) { fail(tag(), 'this map is no longer on the menu (update tests/smoke.cjs)'); continue; }
      let state = 'none';
      for (let i = 0; i < 80 && state === 'none'; i++) {
        await sleep(400);
        state = await page.evaluate(() => { const st = document.getElementById('regMapStage'); if (!st) return 'gone'; if (st.querySelector('.regmap-svg') && !/Loading the map/.test(st.innerText || '')) return 'drawn'; const m = st.querySelector('.state-load, .state-err'); return m && !/Loading/.test(m.textContent) ? 'msg:' + m.textContent.trim().slice(0, 120) : 'none'; });
      }
      await settle(12000);
      if (state === 'none' || state === 'gone') fail(tag(), 'the map never drew and gave no reason');
      else if (state !== 'drawn') warn(tag(), state.slice(4));
      await overflow();
      if (!ALL_MAPS) await shot('map-' + id);
    }
  }

  /* 4. Settings, both appearances */
  at = 'settings';
  await page.evaluate(() => openDrawer()); await settle(8000);
  const set = await page.evaluate(() => { const d = document.getElementById('settingsDrawer'), e = document.getElementById('errBox'), p = document.getElementById('pushBox');
    return { open: !!d && d.classList.contains('open'), err: e ? (e.innerText || '').trim() : null, raw: e ? e.innerHTML : '', push: p ? (p.innerText || '').trim().length : 0 }; });
  if (!set.open) fail(tag(), 'Settings did not open');
  if (set.err == null) fail(tag(), 'App health is missing from Settings');
  else if (!set.err || /^Loading/.test(set.err)) fail(tag(), 'App health never finished loading');
  else if (/<b>error<\/b>/.test(set.raw)) fail(tag(), 'App health shows error text as markup instead of plain text');
  if (!set.push) fail(tag(), 'Push alerts box is empty');
  await overflow(); if (view.full) await shot('settings');
  await page.evaluate(() => { closeDrawer(); const b = document.querySelector('[data-theme-set="light"]'); if (b) b.click(); }); await sleep(400);
  at = 'light appearance';
  if (!(await page.evaluate(() => document.documentElement.getAttribute('data-theme') === 'light'))) fail(tag(), 'the Light switch did not take');
  await page.evaluate(() => switchSection('forecast')); await settle(8000); await overflow(); if (view.full) await shot('light');
  await page.evaluate(() => { const b = document.querySelector('[data-theme-set="dark"]'); if (b) b.click(); });

  /* 5. the error reporter itself: anything it sent above is a real error; then one thrown on purpose must arrive, scrubbed */
  at = 'error reporter';
  await page.evaluate(() => window.NWSERR && NWSERR.flush()); await sleep(600);
  reported.forEach((x) => fail(view.name + ' / ' + (x.p || '?'), 'the app reported ' + x.k + ': ' + String(x.m).slice(0, 200) + (x.w ? ' (' + x.w + ')' : '')));
  reported.length = 0;
  if (!(await page.evaluate(() => !!window.NWSERR))) fail(tag(), 'the reporter is not installed');
  else {
    const before = fails.length;
    page.removeAllListeners('pageerror');
    await page.evaluate(() => { setTimeout(() => { throw new Error('smoke test, thrown on purpose at 43.1117,-88.4993 https://example.com/x?key=secret'); }, 0); });
    await sleep(300); await page.evaluate(() => NWSERR.flush()); await sleep(800);
    const got = reported.filter((x) => /thrown on purpose/.test(x.m))[0];
    if (!got) fail(tag(), 'an error thrown on purpose was not reported');
    else if (/43\.1117|88\.4993|key=secret/.test(JSON.stringify(got))) fail(tag(), 'the report was not scrubbed: ' + JSON.stringify(got).slice(0, 200));
    else if (!/^\d+\.\d+\.\d+$/.test(String(got.v)) || !got.p) fail(tag(), 'the report is missing its version or section');
    if (fails.length === before && view.full) notes.push('error reporter: sends, scrubs, tags version ' + got.v + ' and section "' + got.p + '"');
  }
  await ctx.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
  const browser = await chromium.launch(proxy ? { proxy: { server: proxy } } : {});
  console.log('NWS Terminal screen tests: ' + BASE + (LOCAL ? ' with the files in ' + LOCAL : '') + ', ' + PLACE);
  const t0 = Date.now();
  for (const v of VIEWS) { console.log(' ' + v.name + ' ' + v.width + 'x' + v.height); try { await run(browser, v); } catch (e) { fail(v.name, 'the test itself stopped: ' + String(e && e.message || e).slice(0, 300)); } }
  await browser.close();
  const report = { base: BASE, local: !!LOCAL, place: PLACE, at: new Date().toISOString(), seconds: Math.round((Date.now() - t0) / 1000), notes, fails, warns };
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2));
  notes.forEach((n) => console.log('  note  ' + n));
  warns.forEach((w) => console.log('  warn  ' + w));
  console.log((fails.length ? fails.length + ' FAILED' : 'ALL PASS') + ', ' + warns.length + ' warning' + (warns.length === 1 ? '' : 's') + ', ' + report.seconds + ' s');
  process.exit(fails.length ? 1 : 0);
})();
