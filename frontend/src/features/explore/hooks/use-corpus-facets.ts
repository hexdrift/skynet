"use client";

import { useEffect, useState } from "react";
import { getCorpusFacets, type CorpusFacets } from "@/shared/lib/api";
import type { ExploreCorpus } from "./use-semantic-search";

const EMPTY: CorpusFacets = { models: [], optimizers: [], modules: [] };

function sortFacets(facets: CorpusFacets): CorpusFacets {
  const byLocale = (a: string, b: string) => a.localeCompare(b);
  return {
    models: [...facets.models].sort(byLocale),
    optimizers: [...facets.optimizers].sort(byLocale),
    modules: [...facets.modules].sort(byLocale),
  };
}

/**
 * Distinct filter options (models / optimizers / modules) for the active
 * corpus tab, so each tab offers exactly the chips it can filter to — a model
 * private to "mine" never shows under "public". Refetches when the corpus or
 * signed-in user changes; signed-out "mine"/"shared" have nothing to fetch and
 * resolve to empty. Sorted with the same `localeCompare` the public-points
 * fallback uses so option order stays stable across tabs.
 */
export function useCorpusFacets(
  corpus: ExploreCorpus,
  sessionUser: string,
): CorpusFacets {
  const [facets, setFacets] = useState<CorpusFacets>(EMPTY);

  useEffect(() => {
    let cancelled = false;

    if (corpus !== "public" && !sessionUser) {
      setFacets(EMPTY);
      return;
    }

    const scope =
      corpus === "mine"
        ? { owner_username: sessionUser }
        : corpus === "shared"
          ? { shared_with_username: sessionUser }
          : {};

    void (async () => {
      try {
        const data = await getCorpusFacets(scope);
        if (!cancelled) setFacets(sortFacets(data));
      } catch {
        if (!cancelled) setFacets(EMPTY);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [corpus, sessionUser]);

  return facets;
}
