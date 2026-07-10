# Territory Mapper

Free territory & pin mapping for the US that runs on **Windows, Mac, and iOS**
(any modern browser, installable as an app) and **works offline**. Built to do
what people love commercial tools like Maptitude, AlignMix, and
MapBusinessOnline for — without the $500–$15,000/year price tag.

- **Paste a spreadsheet → pins on a map.** Lat/long columns map instantly;
  address columns are geocoded free via the US Census Bureau. Color pins by
  any column, sum any column into territory totals.
- **Paint territories** from counties or states, and watch each territory's
  population, unit count, pin count, and value totals update live as you
  paint — the balancing workflow reviewers praise commercial tools for.
- **Bundled demographics** — 2024 Census county population estimates ship in
  the app; no data hunting, no API keys.
- **Offline areas** — download the region you work in (like Google Maps
  offline), then everything works with no internet. No competitor in this
  category works offline at all.
- **Print-ready exports** — PNG or PDF with title, legend, and attribution;
  plus territory assignments as a FIPS→Territory CSV (the industry
  interchange format) that can be reimported later.
- **Your data never leaves your device** — projects live in browser storage;
  there is no server, no account, no telemetry.

See [PLAN.md](PLAN.md) for the research (what users love/hate about the
commercial tools) and architecture decisions.

## Run it

```bash
npm install
npm run dev        # development server
npm run build      # production build into dist/
npm run preview    # serve the production build
```

Deploy `dist/` to any static host (GitHub Pages, Cloudflare Pages, Netlify, a
NAS…). HTTPS is required for the service worker (offline support) except on
localhost.

**Install as an app:** open the deployed URL → browser menu → *Install* (or on
iOS Safari: Share → *Add to Home Screen*).

## Testing

`e2e/drive.mjs` drives the real app in Chromium end-to-end: paint territories →
import a spreadsheet → geocode an address → export PNG + assignments CSV →
download an offline area → reload with the network cut and verify everything
still works.

```bash
npm run build && npm run preview &
node e2e/drive.mjs http://localhost:4173 /tmp/tm-shots
```

## Data & attribution

- Base map tiles: [OpenFreeMap](https://openfreemap.org) (free, keyless) —
  data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
- Boundaries: US Census Bureau cartographic boundary files via
  [us-atlas](https://github.com/topojson/us-atlas)
- Population: US Census Bureau 2024 county population estimates
- Geocoding: [US Census Bureau geocoder](https://geocoding.geo.census.gov)
  with [Photon](https://photon.komoot.io) fallback

## Roadmap (v2 candidates)

ZIP-code (ZCTA) building blocks (~3 MB gzipped TopoJSON, feasible), radius/
drive-time rings, auto-balance suggestions, shareable read-only map links.
