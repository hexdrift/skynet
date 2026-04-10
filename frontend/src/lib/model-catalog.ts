/* Model catalog client — fires a single fetch on module load and caches forever.
 * Also persists to localStorage for instant availability on subsequent visits.
 */
import type { ModelCatalogResponse, DiscoverModelsResponse } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const LS_KEY = "skynet:model-catalog";
const LS_TTL = 10 * 60 * 1000; // 10 min TTL for localStorage cache

// Try to hydrate from localStorage immediately (sync, zero latency)
let _cache: ModelCatalogResponse | null = null;
try {
  const raw = typeof window !== "undefined" ? localStorage.getItem(LS_KEY) : null;
  if (raw) {
    const parsed = JSON.parse(raw);
    if (parsed.ts && Date.now() - parsed.ts < LS_TTL) {
      _cache = parsed.data as ModelCatalogResponse;
    }
  }
} catch { /* ignore parse errors */ }

// Kick off network fetch — updates cache and localStorage
const _ready: Promise<ModelCatalogResponse> = (async () => {
  try {
    const res = await fetch(`${API}/models`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data: ModelCatalogResponse = await res.json();
    _cache = data;
    try { localStorage.setItem(LS_KEY, JSON.stringify({ data, ts: Date.now() })); } catch {}
    return data;
  } catch {
    // Return cached or empty catalog on failure
    if (_cache) return _cache;
    const empty: ModelCatalogResponse = { providers: [], models: [] };
    _cache = empty;
    return empty;
  }
})();

export function getModelCatalog(): Promise<ModelCatalogResponse> {
  return _ready;
}

/** Synchronously inspect the cached catalog (returns null only before first fetch resolves). */
export function cachedCatalog(): ModelCatalogResponse | null {
  return _cache;
}

export async function discoverModels(baseUrl: string, apiKey?: string): Promise<DiscoverModelsResponse> {
  const res = await fetch(`${API}/models/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_url: baseUrl, api_key: apiKey || undefined }),
  });
  if (!res.ok) throw new Error(`Server error: ${res.status}`);
  return res.json();
}
