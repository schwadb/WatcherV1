// Tile math and point-in-polygon. No dependencies.

export type BBox = [number, number, number, number]; // w, s, e, n

export function lonToTileX(lon: number, z: number): number {
  return Math.floor(((lon + 180) / 360) * 2 ** z);
}

export function latToTileY(lat: number, z: number): number {
  const rad = (lat * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * 2 ** z);
}

/** Enumerate all z/x/y tiles covering bbox for zoom levels [minZ, maxZ]. */
export function tilesForBBox(bbox: BBox, minZ: number, maxZ: number): Array<[number, number, number]> {
  const [w, s, e, n] = bbox;
  const out: Array<[number, number, number]> = [];
  for (let z = minZ; z <= maxZ; z++) {
    const x0 = Math.max(0, lonToTileX(w, z));
    const x1 = Math.min(2 ** z - 1, lonToTileX(e, z));
    const y0 = Math.max(0, latToTileY(n, z)); // north => smaller y
    const y1 = Math.min(2 ** z - 1, latToTileY(s, z));
    for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) out.push([z, x, y]);
  }
  return out;
}

export function countTilesForBBox(bbox: BBox, minZ: number, maxZ: number): number {
  const [w, s, e, n] = bbox;
  let count = 0;
  for (let z = minZ; z <= maxZ; z++) {
    const x0 = Math.max(0, lonToTileX(w, z));
    const x1 = Math.min(2 ** z - 1, lonToTileX(e, z));
    const y0 = Math.max(0, latToTileY(n, z));
    const y1 = Math.min(2 ** z - 1, latToTileY(s, z));
    count += (x1 - x0 + 1) * (y1 - y0 + 1);
  }
  return count;
}

// --- point in polygon (GeoJSON Polygon / MultiPolygon), ray casting ---

function inRing(pt: [number, number], ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > pt[1] !== yj > pt[1] && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function inPolygon(pt: [number, number], coords: number[][][]): boolean {
  if (!inRing(pt, coords[0])) return false;
  for (let i = 1; i < coords.length; i++) if (inRing(pt, coords[i])) return false; // holes
  return true;
}

export function pointInFeature(pt: [number, number], geom: GeoJSON.Geometry): boolean {
  if (geom.type === 'Polygon') return inPolygon(pt, geom.coordinates as number[][][]);
  if (geom.type === 'MultiPolygon') {
    for (const poly of geom.coordinates as number[][][][]) if (inPolygon(pt, poly)) return true;
  }
  return false;
}

export function geomBBox(geom: GeoJSON.Geometry): BBox {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const scan = (coords: unknown): void => {
    if (typeof (coords as number[])[0] === 'number') {
      const [x, y] = coords as [number, number];
      if (x < w) w = x;
      if (x > e) e = x;
      if (y < s) s = y;
      if (y > n) n = y;
    } else {
      for (const c of coords as unknown[]) scan(c);
    }
  };
  scan((geom as GeoJSON.Polygon).coordinates);
  return [w, s, e, n];
}
