/* NWS Terminal service worker.
   App shell only, network-first: every load still asks the network (so a
   deploy lands immediately) and falls back to the cached shell when offline.
   Weather data (/p/*, /api/*, and every cross-origin API) is never cached
   here — stale weather presented as current is worse than an error. */
const CACHE = 'nwst-shell-v3.64.0';
const SHELL = ['/', '/app.js?v=3.64.0', '/app.css?v=3.64.0', '/favicon.svg', '/manifest.webmanifest',
               '/icons/icon-192.png', '/icons/apple-touch-icon.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/p/') || url.pathname.startsWith('/api/')) return;

  const isNav = req.mode === 'navigate';
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(isNav ? '/' : req, copy));
        }
        return res;
      })
      .catch(() => caches.match(isNav ? '/' : req).then((r) => r || caches.match('/')))
  );
});
