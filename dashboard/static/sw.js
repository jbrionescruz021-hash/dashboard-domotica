// Service worker: guarda la página para que la app abra aunque no haya red.
// Los datos de /api siempre se piden al servidor (nunca se guardan en caché).
const CACHE = "domotica-v2";
const ARCHIVOS = ["/", "/manifest.webmanifest", "/static/icon-192.png", "/static/icon-512.png", "/static/chart.umd.min.js"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ARCHIVOS)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  // Primero la red; si no hay conexión, la copia guardada
  e.respondWith(
    fetch(e.request)
      .then(r => { const copia = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copia)); return r; })
      .catch(() => caches.match(e.request))
  );
});
