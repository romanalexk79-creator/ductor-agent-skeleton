/* {{PROJECT_NAME}} service worker — network-first shell, cache fallback for offline */
const CACHE = "app-v1";
const ASSETS = [
  "./", "./index.html",
  "./static/style.css", "./static/app.js", "./static/demo-data.js",
  "./static/telegram-web-app.js", "./static/chart.umd.min.js",
  "./static/icon.svg", "./manifest.json"
];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // Live data + same-origin app shell: network-first so updates are never masked.
  if (url.origin === location.origin) {
    e.respondWith(
      fetch(e.request).then(r => {
        // Refresh the cached copy so offline fallback stays current.
        if (r && r.ok && !url.pathname.includes("/data/") && !url.pathname.includes("/api/")) {
          const copy = r.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
        }
        return r;
      }).catch(() => caches.match(e.request))
    );
  } else {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
  }
});
