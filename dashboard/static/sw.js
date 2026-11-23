/* Network first, cache as a fallback: the TV page and its files still load while the server restarts.
   API calls are never cached; the widgets already wait and retry. */
const CACHE = "watcher-dashboard-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

async function remember(key, res) {
  const cache = await caches.open(CACHE);
  const url = new URL(key, self.location.origin);
  for (const old of await cache.keys()) {  // one copy per file, whatever its ?v= version
    const o = new URL(old.url);
    if (o.pathname === url.pathname && o.search !== url.search) await cache.delete(old);
  }
  await cache.put(key, res);
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  const page = req.mode === "navigate" && url.pathname === "/";
  if (!page && !url.pathname.startsWith("/static/")) return;
  const key = page ? "/" : req.url;
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) e.waitUntil(remember(key, res.clone()));
        return res;
      })
      .catch(() => caches.match(key).then((hit) => hit || Response.error()))
  );
});
