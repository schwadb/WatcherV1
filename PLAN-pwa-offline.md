# PLAN: PWA + offline support (installable app on Android)

**Rank: 1 of 5 — do this first.**
The app is used from an Android home-screen shortcut pointed at
`https://schwadb.github.io/WatcherV1/`. Today that opens as a plain browser
tab: no app icon splash, URL bar visible, and a dead white page with no
network. A manifest + service worker makes it install as a real app and work
offline — which matters because the core ritual happens in bed at 6 a.m.

## Goal

Chrome on Android offers "Install app" (not just "Add to Home screen
shortcut"), the installed app opens standalone (no URL bar), and the app
fully loads and functions with airplane mode on after one prior visit.
New deploys reach users within one app restart.

## Files to touch

| File | Change |
|---|---|
| `manifest.webmanifest` | **new** — app metadata + icons |
| `icon.svg` | **new** — single SVG app icon |
| `sw.js` | **new** — service worker |
| `index.html` | add manifest link, theme-color metas, SW registration |
| `.github/workflows/pages.yml` | inject cache-busting version into `sw.js` |

## Implementation order

1. **`icon.svg`** at repo root. Simple mark: rounded square, `#2a78d6`
   background, white monospace "W" or a 3×3 grid of dots with one checkmark.
   Keep it a single `<svg viewBox="0 0 512 512">` with no external refs.
   Add generous padding (icon content within the central 60%) so it also
   works with `"purpose": "maskable"`.

2. **`manifest.webmanifest`** at repo root. CRITICAL: this site is served
   from a subpath, so every URL must be relative or subpath-absolute:

   ```json
   {
     "name": "Watcher — Habit Tracker",
     "short_name": "Watcher",
     "start_url": "./",
     "scope": "./",
     "display": "standalone",
     "background_color": "#f9f9f7",
     "theme_color": "#f9f9f7",
     "icons": [
       { "src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any" },
       { "src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable" }
     ]
   }
   ```

3. **`index.html` head** — directly after the `<title>` line add:

   ```html
   <link rel="manifest" href="manifest.webmanifest">
   <link rel="icon" href="icon.svg" type="image/svg+xml">
   <meta name="theme-color" content="#f9f9f7" media="(prefers-color-scheme: light)">
   <meta name="theme-color" content="#0d0d0d" media="(prefers-color-scheme: dark)">
   <meta name="apple-mobile-web-app-capable" content="yes">
   ```

4. **`sw.js`** at repo root (NOT in a subfolder — SW scope is limited to its
   own path prefix). Strategy:
   - `const VERSION = '__BUILD__';` — literal placeholder string, replaced at
     deploy time (step 6). Cache name: `` `watcher-${VERSION}` ``.
   - `install`: `cache.addAll(['./', 'index.html', 'manifest.webmanifest', 'icon.svg'])`
     then `self.skipWaiting()`.
   - `activate`: delete every cache whose name isn't the current one, then
     `self.clients.claim()`.
   - `fetch`: **network-first for navigation requests** (`request.mode ===
     'navigate'`) falling back to `caches.match('index.html')`; cache-first
     for everything else same-origin. Ignore non-GET and cross-origin
     requests entirely (`return;` without `respondWith`).

5. **SW registration** — at the very end of the IIFE in `index.html`, after
   the `renderAll();` call:

   ```js
   if ('serviceWorker' in navigator && location.protocol === 'https:') {
     navigator.serviceWorker.register('sw.js');
   }
   ```

   The `https:` guard keeps local `file://` opening working without console
   errors (SW registration throws on file://).

6. **Cache busting** in `.github/workflows/pages.yml` — add one step between
   `actions/checkout@v4` and `actions/configure-pages@v5`:

   ```yaml
   - name: Stamp service worker version
     run: sed -i "s/__BUILD__/${GITHUB_SHA::8}/" sw.js
   ```

## Edge cases a weaker model would miss

- **The subpath is load-bearing.** The site lives at `/WatcherV1/`, not `/`.
  `start_url: "/"` or registering `/sw.js` silently breaks install and
  scoping. Everything must be relative (`./`) or include `/WatcherV1/`.
- **SVG-only icons are acceptable to Chromium** (which is what Android
  installs use) but the manifest entry must say `"sizes": "any"`. Do not
  fabricate PNG references that don't exist — a 404'd icon fails the
  installability check.
- **`skipWaiting` + network-first-for-navigations** is what makes deploys
  propagate. Cache-first for `index.html` would pin users to the first
  version forever; the `__BUILD__` stamp alone doesn't help if the old SW
  never yields.
- **Do not intercept cross-origin fetches.** Respond only to same-origin
  GETs; anything else must fall through untouched.
- **localStorage is independent of the SW cache** — clearing site data wipes
  habit history. Do not "helpfully" migrate storage into Cache API; leave
  data handling exactly as is.
- **file:// must keep working** (that's the README's "easiest" path). Guard
  registration as in step 5; the manifest link 404s harmlessly there.

## Acceptance criteria

1. Chrome DevTools → Application → Manifest shows no warnings; "Service
   worker" shows activated and running on `https://schwadb.github.io/WatcherV1/`.
2. Lighthouse PWA audit passes "installable".
3. On Android Chrome, the install prompt says **Install app**; the installed
   app opens with no URL bar.
4. Load the site once, enable airplane mode, reopen: the app renders and a
   habit can be ticked (persists after network returns).
5. Push a visible change to `main`; after deploy completes, closing and
   reopening the installed app twice shows the change.
6. Opening `index.html` via `file://` still works with zero console errors.
