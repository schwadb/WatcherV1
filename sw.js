// Offline support for Watcher: serve the app shell from cache, refresh it in the background.
const CACHE = 'watcher-shell-v1';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png'];
const SHELL_URLS = new Set(SHELL.map(p => new URL(p, self.registration.scope).href));

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('watcher-shell-') && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  url.search = '';
  url.hash = '';
  // Only the habit tracker's own files; the dashboard and anything else pass straight through.
  if (e.request.method !== 'GET' || !SHELL_URLS.has(url.href)) return;
  e.respondWith(caches.open(CACHE).then(async cache => {
    const cached = await cache.match(url.href);
    const fresh = fetch(e.request)
      .then(res => { if (res.ok) cache.put(url.href, res.clone()); return res; })
      .catch(() => cached);
    if (cached) { e.waitUntil(fresh); return cached; }
    return fresh;
  }));
});
