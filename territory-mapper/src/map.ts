// MapLibre setup: base style (OpenFreeMap), cached:// tile protocol
// (IndexedDB-first, network fallback), boundary + pin layers.
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { getTile } from './storage';
import type { Boundaries } from './boundaries';

const STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
const LS_STYLE = 'tm-style-cache';
const LS_TILEJSON = 'tm-tilejson-cache';

export interface TmMap {
  map: maplibregl.Map;
  /** real tile URL template, for the offline downloader */
  tileTemplate: string;
  setUnitLevel(level: 'state' | 'county'): void;
  setUnitColor(fipsNum: number, color: string | null): void;
  clearUnitColors(): void;
}

/** cached://<origin-path with {z}/{x}/{y} already substituted> */
function registerCachedProtocol(): void {
  maplibregl.addProtocol('cached', async (params) => {
    const real = params.url.replace('cached://', 'https://');
    const m = real.match(/\/(\d+)\/(\d+)\/(\d+)\.(pbf|mvt)/);
    if (m) {
      const key = `t/${m[1]}/${m[2]}/${m[3]}`;
      const hit = await getTile(key).catch(() => undefined);
      if (hit) return { data: hit };
    }
    const resp = await fetch(real);
    if (resp.status === 204) return { data: new ArrayBuffer(0) };
    if (!resp.ok) throw new Error(`tile ${resp.status}`);
    return { data: await resp.arrayBuffer() };
  });
}

async function fetchWithFallback(url: string, lsKey: string): Promise<Record<string, unknown>> {
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(String(resp.status));
    const json = await resp.json();
    try {
      localStorage.setItem(lsKey, JSON.stringify(json));
    } catch {
      /* quota — fine */
    }
    return json;
  } catch (err) {
    const cached = localStorage.getItem(lsKey);
    if (cached) return JSON.parse(cached);
    throw err;
  }
}

/** Load the base style and rewrite its vector sources to our cached:// scheme. */
async function buildStyle(): Promise<{ style: maplibregl.StyleSpecification; tileTemplate: string }> {
  const style = (await fetchWithFallback(STYLE_URL, LS_STYLE)) as unknown as maplibregl.StyleSpecification;
  let tileTemplate = '';
  for (const src of Object.values(style.sources)) {
    if (src.type !== 'vector') continue;
    let tiles: string[] | undefined = src.tiles;
    if (!tiles && src.url) {
      const tj = await fetchWithFallback(src.url, LS_TILEJSON);
      tiles = tj.tiles as string[];
      if (tj.minzoom !== undefined) src.minzoom = tj.minzoom as number;
      if (tj.maxzoom !== undefined) src.maxzoom = tj.maxzoom as number;
      delete src.url;
    }
    if (tiles?.length) {
      tileTemplate = tiles[0];
      src.tiles = [tiles[0].replace(/^https:\/\//, 'cached://')];
    }
  }
  return { style, tileTemplate };
}

export async function createMap(container: HTMLElement, boundaries: Boundaries): Promise<TmMap> {
  registerCachedProtocol();
  const { style, tileTemplate } = await buildStyle();

  const map = new maplibregl.Map({
    container,
    style,
    center: [-96.5, 39.5],
    zoom: 4,
    minZoom: 2,
    maxZoom: 15,
    attributionControl: { compact: false },
    canvasContextAttributes: { preserveDrawingBuffer: true }, // needed for export capture
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

  await new Promise<void>((resolve, reject) => {
    map.once('load', () => resolve());
    map.once('error', (e) => {
      // style-level failure only; tile errors also arrive here, so only reject before load
      reject(e.error ?? new Error('map failed to load'));
    });
  }).catch((err) => {
    console.warn('map load warning:', err);
  });

  // Insert our layers beneath the first symbol layer so basemap labels stay on top.
  const firstSymbol = map.getStyle().layers.find((l) => l.type === 'symbol')?.id;

  map.addSource('counties', { type: 'geojson', data: boundaries.counties });
  map.addSource('states', { type: 'geojson', data: boundaries.states });

  for (const level of ['county', 'state'] as const) {
    const src = level === 'county' ? 'counties' : 'states';
    map.addLayer(
      {
        id: `${level}-fill`,
        type: 'fill',
        source: src,
        layout: { visibility: 'none' },
        paint: {
          'fill-color': ['coalesce', ['feature-state', 'color'], 'rgba(0,0,0,0)'],
          'fill-opacity': 0.55,
        },
      },
      firstSymbol,
    );
    map.addLayer(
      {
        id: `${level}-line`,
        type: 'line',
        source: src,
        layout: { visibility: 'none' },
        paint: {
          'line-color': '#5b6472',
          'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.3, 8, 1.2],
          'line-opacity': 0.7,
        },
      },
      firstSymbol,
    );
    map.addLayer(
      {
        id: `${level}-hover`,
        type: 'line',
        source: src,
        layout: { visibility: 'none' },
        paint: { 'line-color': '#1a73e8', 'line-width': 2 },
        filter: ['==', ['id'], -1],
      },
      firstSymbol,
    );
  }

  let currentLevel: 'state' | 'county' = 'county';
  const setUnitLevel = (level: 'state' | 'county') => {
    currentLevel = level;
    for (const l of ['state', 'county'] as const) {
      const vis = l === level ? 'visible' : 'none';
      map.setLayoutProperty(`${l}-fill`, 'visibility', vis);
      map.setLayoutProperty(`${l}-line`, 'visibility', vis);
      map.setLayoutProperty(`${l}-hover`, 'visibility', vis);
    }
  };
  setUnitLevel('county');

  return {
    map,
    tileTemplate,
    setUnitLevel,
    setUnitColor(fipsNum, color) {
      const source = currentLevel === 'county' ? 'counties' : 'states';
      if (color) map.setFeatureState({ source, id: fipsNum }, { color });
      else map.removeFeatureState({ source, id: fipsNum }, 'color');
    },
    clearUnitColors() {
      map.removeFeatureState({ source: 'counties' });
      map.removeFeatureState({ source: 'states' });
    },
  };
}
