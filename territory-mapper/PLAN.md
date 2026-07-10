# Territory Mapper — build plan

## Why this app

Research across G2/Capterra/TrustRadius reviews, Reddit, and vendor material for
Maptitude ($795/yr, 4.7–4.8★), eSpatial ($7,995/yr), AlignMix ($2,400+/yr, 5.0★),
MapBusinessOnline ($500/yr, 4.5★) and BatchGeo/Mapline found the features users
actually praise, and the gaps they complain about:

**Loved (build these):**
1. Paste/import a spreadsheet → pins on a map, no GIS knowledge needed
   (BatchGeo/MBO's signature; "if you can use Excel you can use this" — Maptitude)
2. Build sales territories from counties/states and **see balance totals update
   live while you drag/paint** (AlignMix "Touch Align" — its entire moat)
3. Bundled demographics — population included, no data hunting (Maptitude's
   most-cited pro: ~15 of ~35 reviews)
4. Clean high-res exports for PowerPoint/reports (praised in Maptitude,
   explicit tier feature in AlignMix)
5. Works offline; you own your data (Maptitude markets "the only mapping
   software that can run completely offline"; cloud tools can't)

**Complained about (avoid these):**
- Price ($500–$15,000/yr) → free
- Windows-only desktop (Maptitude, AlignMix) → PWA: Windows/Mac/iOS
- Paying extra to share (Maptitude Online $795/yr) → project files export/import
- Dated UI (MBO), learning curve (all) → one screen, three panels, no manual

## v1 scope

Territory & pin mapping for the US only. One page, installable PWA.

- **Pins:** import CSV (file or paste), auto-detect lat/lng columns, otherwise
  geocode via Census Bureau (JSONP — its JSON API blocks browser CORS) with
  Photon fallback; color pins by any column; popups show the row.
- **Territories:** paint states or counties into named color territories;
  live panel: population (bundled 2024 Census estimates), unit count, pin
  count, sum of a chosen value column per territory.
- **Offline areas:** user draws a box, picks detail level, tiles download into
  IndexedDB; a custom `cached://` protocol serves IndexedDB-first. App shell +
  styles/fonts precached by service worker → full offline after first load.
- **Export:** PNG and PDF at 1x/2x with title + legend composited.
- **Persistence:** projects autosave to IndexedDB; export/import project JSON.

## Stack (versions verified against npm 2026-07)

| Piece | Choice | Why |
|---|---|---|
| Rendering | maplibre-gl 5.x | Standard, healthy (87 sponsors), globe-free vector GL |
| Base tiles | OpenFreeMap (tiles.openfreemap.org) | Free, keyless, "no limits", CORS-open, self-hostable |
| Boundaries | us-atlas TopoJSON (states 112 KB, counties 824 KB) | Census cartographic 1:10m, ships in-app |
| Population | co-est2024 CSV → 44 KB JSON, bundled | Census API now requires a key; static beats leaking one |
| CSV | papaparse | standard |
| Geocode | Census geocoder JSONP → Photon (CORS ✓) fallback | free, no keys |
| Export | map canvas capture + html-to-image (legend) + jspdf 4.x | preserveDrawingBuffer capture; jsPDF actively maintained |
| PWA | vite-plugin-pwa (Workbox) | precache app, runtime-cache styles/glyphs |
| Offline tiles | hand-rolled z/x/y walker → IndexedDB | no lib exists; trivial against z/x/y URLs |

## Architecture

```
src/
  types.ts        data model (Project, Territory, PinLayer, OfflineArea)
  storage.ts      IndexedDB: projects, tiles, areas + persistence request
  geo.ts          tile math, bbox, point-in-county (bbox-indexed ray cast)
  boundaries.ts   TopoJSON → GeoJSON, county/state lookup tables
  map.ts          MapLibre init, cached:// protocol, sources/layers
  territories.ts  assignment ops + live stats rollup
  importer.ts     CSV parse, column mapping, geocode queue
  exporter.ts     PNG/PDF with legend
  offline.ts      area download: enumerate tiles, fetch (8-way), store, progress
  ui.ts           panels, legend, stats table, toasts
  main.ts         boot + autosave
```

Decisions of note:
- **iOS-safe:** capture canvas ≤4096px; request `navigator.storage.persist()`;
  installed-PWA quota is fine for 10–150 MB areas.
- Boundary fill layers use feature-state for territory colors (fast repaint
  while painting).
- Offline detail levels: Overview z0–10, Standard z0–12, Detail z0–13, with
  live tile-count/size estimate and a warning above ~150 MB.
- Attribution: OpenStreetMap contributors + OpenFreeMap, kept in exports.

## Milestones (tracked as session tasks)

1. ✔ Research (5 sub-reports, verified claims)
2. Plan (this file)
3. ✔ Scaffold + data (Vite + TS; boundaries + population bundled)
4. Base map + offline areas
5. Territory editor + live balance
6. CSV import + geocode + pins
7. PNG/PDF export
8. PWA + persistence
9. End-to-end debug in Chromium (import → paint → export → offline reload)
10. Push; move to its own repo when created

## Out of scope for v1 (candidates for v2)

ZIP-code (ZCTA) building blocks (~33k polygons — needs per-state loading),
drive-time rings, route optimization, auto-balance optimizer, multi-user
sharing, CRM integrations.
