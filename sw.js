/* NWS Terminal service worker (v3.83.0): push alerts only. It does not touch page requests, so every load still comes
   straight from the network. A push carries { title, body, tag, url, renotify, sticky, ts }, encrypted for this device. */
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });

self.addEventListener('push', function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.title || 'NWS Terminal', {
    body: d.body || '', tag: d.tag || undefined, renotify: !!(d.tag && d.renotify), requireInteraction: !!d.sticky,
    icon: '/icons/icon-192.png', badge: '/icons/icon-192.png', timestamp: d.ts || Date.now(), data: { url: d.url || '/' }
  }));
});

self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var url = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin);
  if (url.origin !== self.location.origin) url = new URL('/', self.location.origin);
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      var c = list[i];
      if (new URL(c.url).origin !== url.origin) continue;
      return c.focus().then(function (w) { (w || c).postMessage({ nwsOpen: url.hash }); return w; });
    }
    return self.clients.openWindow(url.href);
  }));
});
