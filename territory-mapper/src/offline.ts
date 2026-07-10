// Offline area downloads: enumerate tiles for a bbox, fetch with limited
// concurrency, store in IndexedDB in batches. The cached:// protocol in
// map.ts then serves them IndexedDB-first.
import { countTilesForBBox, tilesForBBox, type BBox } from './geo';
import { deleteArea, deleteTiles, listAreas, putTiles, saveArea } from './storage';
import type { OfflineArea } from './types';

export const DETAIL_LEVELS = [
  { label: 'Overview (state level)', maxZoom: 10 },
  { label: 'Standard (city level)', maxZoom: 12 },
  { label: 'Detail (street level)', maxZoom: 13 },
] as const;

const AVG_TILE_BYTES = 40_000; // planning number for the size estimate

export function estimateArea(bbox: BBox, maxZoom: number): { tiles: number; bytes: number } {
  const tiles = countTilesForBBox(bbox, 0, maxZoom);
  return { tiles, bytes: tiles * AVG_TILE_BYTES };
}

export interface DownloadProgress {
  done: number;
  total: number;
  bytes: number;
  failed: number;
}

export async function downloadArea(
  name: string,
  bbox: BBox,
  maxZoom: number,
  tileTemplate: string,
  onProgress: (p: DownloadProgress) => void,
  signal?: AbortSignal,
): Promise<OfflineArea> {
  const tiles = tilesForBBox(bbox, 0, maxZoom);
  const progress: DownloadProgress = { done: 0, total: tiles.length, bytes: 0, failed: 0 };
  const CONCURRENCY = 8;
  const BATCH = 64;
  let pending: Array<[string, ArrayBuffer]> = [];
  let cursor = 0;

  const flush = async () => {
    if (pending.length) {
      const batch = pending;
      pending = [];
      await putTiles(batch);
    }
  };

  const worker = async () => {
    while (cursor < tiles.length) {
      if (signal?.aborted) throw new DOMException('aborted', 'AbortError');
      const [z, x, y] = tiles[cursor++];
      const url = tileTemplate.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y));
      try {
        const resp = await fetch(url, { signal });
        if (resp.status === 204) {
          // empty tile (ocean) — nothing to store, protocol treats miss+204 the same
        } else if (resp.ok) {
          const buf = await resp.arrayBuffer();
          pending.push([`t/${z}/${x}/${y}`, buf]);
          progress.bytes += buf.byteLength;
          if (pending.length >= BATCH) await flush();
        } else {
          progress.failed++;
        }
      } catch (err) {
        if ((err as Error).name === 'AbortError') throw err;
        progress.failed++;
      }
      progress.done++;
      if (progress.done % 20 === 0 || progress.done === progress.total) onProgress({ ...progress });
    }
  };

  await Promise.all(Array.from({ length: CONCURRENCY }, () => worker()));
  await flush();

  const area: OfflineArea = {
    id: crypto.randomUUID(),
    name,
    bounds: bbox,
    minZoom: 0,
    maxZoom,
    tileCount: progress.total - progress.failed,
    sizeBytes: progress.bytes,
    createdAt: new Date().toISOString(),
  };
  await saveArea(area);
  return area;
}

/** Remove an area's tiles unless another remaining area still covers them. */
export async function removeArea(area: OfflineArea): Promise<void> {
  const others = (await listAreas()).filter((a) => a.id !== area.id);
  const keep = new Set<string>();
  for (const o of others) {
    for (const [z, x, y] of tilesForBBox(o.bounds, o.minZoom, o.maxZoom)) keep.add(`t/${z}/${x}/${y}`);
  }
  const mine = tilesForBBox(area.bounds, area.minZoom, area.maxZoom)
    .map(([z, x, y]) => `t/${z}/${x}/${y}`)
    .filter((k) => !keep.has(k));
  await deleteTiles(mine);
  await deleteArea(area.id);
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}
