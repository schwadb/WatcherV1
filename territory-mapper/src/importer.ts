// CSV import: parse, detect columns, geocode address rows.
// Census geocoder is JSONP-only from browsers (no CORS on its JSON API);
// Photon (komoot) sends CORS headers and is the fallback.
import Papa from 'papaparse';

export interface ParsedCsv {
  columns: string[];
  rows: Array<Record<string, string>>;
}

export function parseCsv(text: string): ParsedCsv {
  const res = Papa.parse<Record<string, string>>(text.trim(), {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h) => h.trim(),
  });
  const columns = res.meta.fields ?? [];
  return { columns, rows: res.data };
}

export interface ColumnGuess {
  lat: string | null;
  lng: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  name: string | null;
}

export function guessColumns(columns: string[]): ColumnGuess {
  const find = (patterns: RegExp[]) => {
    for (const p of patterns) {
      const hit = columns.find((c) => p.test(c.toLowerCase().replace(/[^a-z0-9]/g, '')));
      if (hit) return hit;
    }
    return null;
  };
  return {
    lat: find([/^lat(itude)?$/, /^y$/, /lat/]),
    lng: find([/^(lng|lon|long|longitude)$/, /^x$/, /(lng|lon)/]),
    address: find([/^(street)?address1?$/, /^street$/, /address/]),
    city: find([/^city$/, /^town$/, /city/]),
    state: find([/^(state|st)$/, /^province$/, /state/]),
    zip: find([/^(zip|zipcode|postalcode|postcode)$/, /zip/]),
    name: find([/^(name|title|label|company|account|customer|location)$/, /name/]),
  };
}

export interface GeocodeResult {
  lng: number;
  lat: number;
  source: 'census' | 'photon';
}

let jsonpCounter = 0;

/** Census geocoder via JSONP (officially documented browser path). */
function censusGeocode(oneLine: string, timeoutMs = 8000): Promise<GeocodeResult | null> {
  return new Promise((resolve) => {
    const cb = `__tmGeo${++jsonpCounter}`;
    const script = document.createElement('script');
    const cleanup = () => {
      delete (window as unknown as Record<string, unknown>)[cb];
      script.remove();
    };
    const timer = setTimeout(() => {
      cleanup();
      resolve(null);
    }, timeoutMs);
    (window as unknown as Record<string, unknown>)[cb] = (data: {
      result?: { addressMatches?: Array<{ coordinates: { x: number; y: number } }> };
    }) => {
      clearTimeout(timer);
      cleanup();
      const m = data?.result?.addressMatches?.[0];
      resolve(m ? { lng: m.coordinates.x, lat: m.coordinates.y, source: 'census' } : null);
    };
    script.onerror = () => {
      clearTimeout(timer);
      cleanup();
      resolve(null);
    };
    const url =
      'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress' +
      `?address=${encodeURIComponent(oneLine)}&benchmark=Public_AR_Current&format=jsonp&callback=${cb}`;
    script.src = url;
    document.head.appendChild(script);
  });
}

/** Photon fallback (CORS-enabled). Bounded to the continental US + AK/HI. */
async function photonGeocode(oneLine: string): Promise<GeocodeResult | null> {
  try {
    const url = `https://photon.komoot.io/api?q=${encodeURIComponent(oneLine + ', USA')}&limit=1`;
    const resp = await fetch(url);
    if (!resp.ok) return null;
    const json = await resp.json();
    const f = json?.features?.[0];
    if (!f) return null;
    const [lng, lat] = f.geometry.coordinates;
    // sanity: inside US-ish bounds
    if (lng < -180 || lng > -60 || lat < 15 || lat > 72) return null;
    return { lng, lat, source: 'photon' };
  } catch {
    return null;
  }
}

export async function geocodeOne(oneLine: string): Promise<GeocodeResult | null> {
  return (await censusGeocode(oneLine)) ?? (await photonGeocode(oneLine));
}

/** Build the one-line address for a row given mapped columns. */
export function rowAddress(row: Record<string, string>, g: ColumnGuess): string {
  return [g.address && row[g.address], g.city && row[g.city], g.state && row[g.state], g.zip && row[g.zip]]
    .filter(Boolean)
    .join(', ');
}

export function parseLatLng(row: Record<string, string>, g: ColumnGuess): { lat: number; lng: number } | null {
  if (!g.lat || !g.lng) return null;
  const lat = parseFloat(row[g.lat]);
  const lng = parseFloat(row[g.lng]);
  if (Number.isNaN(lat) || Number.isNaN(lng)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  if (lat === 0 && lng === 0) return null;
  return { lat, lng };
}
