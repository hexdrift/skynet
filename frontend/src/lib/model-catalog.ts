/* Model catalog client — fires a single fetch on module load and caches forever. */
import type { ModelCatalogResponse, DiscoverModelsResponse } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Kick off immediately on import — by the time the picker opens, data is ready.
let _cache: ModelCatalogResponse | null = null;
const _ready: Promise<ModelCatalogResponse> = (async () => {
  try {
    const res = await fetch(`${API}/models`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data: ModelCatalogResponse = await res.json();
    _cache = data;
    return data;
  } catch {
    // Return empty catalog on failure — picker still works with custom input
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
