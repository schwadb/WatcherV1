// IndexedDB persistence, no dependencies. Three stores:
//   projects   — Project objects keyed by id
//   tiles      — cached vector tiles keyed by "z/x/y" (offline areas)
//   areas      — OfflineArea metadata keyed by id
import type { OfflineArea, Project } from './types';

const DB_NAME = 'territory-mapper';
const DB_VERSION = 1;

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains('projects')) db.createObjectStore('projects');
        if (!db.objectStoreNames.contains('tiles')) db.createObjectStore('tiles');
        if (!db.objectStoreNames.contains('areas')) db.createObjectStore('areas');
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

function tx<T>(store: string, mode: IDBTransactionMode, op: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const t = db.transaction(store, mode);
        const req = op(t.objectStore(store));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      }),
  );
}

// --- projects ---

export const saveProject = (p: Project) => tx('projects', 'readwrite', (s) => s.put(p, p.id));
export const loadProject = (id: string) => tx<Project | undefined>('projects', 'readonly', (s) => s.get(id));
export const deleteProject = (id: string) => tx('projects', 'readwrite', (s) => s.delete(id));
export const listProjects = () => tx<Project[]>('projects', 'readonly', (s) => s.getAll());

// --- offline tiles ---

export const putTile = (key: string, data: ArrayBuffer) => tx('tiles', 'readwrite', (s) => s.put(data, key));
export const getTile = (key: string) => tx<ArrayBuffer | undefined>('tiles', 'readonly', (s) => s.get(key));

/** Bulk-write tiles in a single transaction (much faster than one tx per tile). */
export function putTiles(entries: Array<[string, ArrayBuffer]>): Promise<void> {
  return openDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const t = db.transaction('tiles', 'readwrite');
        const s = t.objectStore('tiles');
        for (const [key, data] of entries) s.put(data, key);
        t.oncomplete = () => resolve();
        t.onerror = () => reject(t.error);
      }),
  );
}

export function deleteTiles(keys: string[]): Promise<void> {
  return openDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const t = db.transaction('tiles', 'readwrite');
        const s = t.objectStore('tiles');
        for (const key of keys) s.delete(key);
        t.oncomplete = () => resolve();
        t.onerror = () => reject(t.error);
      }),
  );
}

// --- offline area metadata ---

export const saveArea = (a: OfflineArea) => tx('areas', 'readwrite', (s) => s.put(a, a.id));
export const deleteArea = (id: string) => tx('areas', 'readwrite', (s) => s.delete(id));
export const listAreas = () => tx<OfflineArea[]>('areas', 'readonly', (s) => s.getAll());

/** Ask the browser to protect our data from eviction (best effort). */
export async function requestPersistence(): Promise<boolean> {
  if (navigator.storage?.persist) {
    try {
      return await navigator.storage.persist();
    } catch {
      return false;
    }
  }
  return false;
}

export async function storageEstimate(): Promise<{ usage: number; quota: number } | null> {
  if (navigator.storage?.estimate) {
    const e = await navigator.storage.estimate();
    return { usage: e.usage ?? 0, quota: e.quota ?? 0 };
  }
  return null;
}
