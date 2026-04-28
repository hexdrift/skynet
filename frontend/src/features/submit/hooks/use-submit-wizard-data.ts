import { useCallback, useEffect, useState, type MutableRefObject } from "react";
import { getModelCatalog, cachedCatalog } from "@/shared/lib/model-catalog";
import { profileDataset } from "@/shared/lib/api";
import type {
  ColumnMapping,
  DatasetProfile,
  ModelCatalogResponse,
  ModelConfig,
  SplitFractions,
  SplitPlan,
} from "@/shared/types/api";
import type { ParsedDataset } from "@/shared/lib/parse-dataset";
import { MAX_RECENT, RECENT_KEY } from "../constants";

type ColumnRole = "input" | "output" | "ignore";

export function buildColumnMapping(columnRoles: Record<string, ColumnRole>): ColumnMapping {
  const inputs: Record<string, string> = {};
  const outputs: Record<string, string> = {};
  Object.entries(columnRoles).forEach(([col, role]) => {
    if (role === "input") inputs[col] = col;
    else if (role === "output") outputs[col] = col;
  });
  return { inputs, outputs };
}

export function useRecentModelConfigs() {
  const [recentConfigs, setRecentConfigs] = useState<ModelConfig[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    } catch {
      return [];
    }
  });

  const saveToRecent = useCallback((config: ModelConfig) => {
    if (!config.name) return;
    setRecentConfigs((prev) => {
      const deduped = prev.filter((c) => c.name !== config.name);
      const next = [config, ...deduped].slice(0, MAX_RECENT);
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const clearRecentConfigs = useCallback(() => {
    setRecentConfigs([]);
    localStorage.removeItem(RECENT_KEY);
  }, []);

  return { recentConfigs, saveToRecent, clearRecentConfigs };
}

export function useModelCatalog() {
  const [catalog, setCatalog] = useState<ModelCatalogResponse | null>(cachedCatalog);

  useEffect(() => {
    if (catalog) return;
    let cancelled = false;
    getModelCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [catalog]);

  return catalog;
}

export function useDatasetProfiling({
  parsedDataset,
  columnRoles,
  splitModeRef,
  setDatasetProfile,
  setSplitPlan,
  setProfileLoading,
  setSplit,
  setShuffle,
  setSeed,
  setStratify,
  setStratifyColumn,
}: {
  parsedDataset: ParsedDataset | null;
  columnRoles: Record<string, ColumnRole>;
  splitModeRef: MutableRefObject<"auto" | "manual">;
  setDatasetProfile: (profile: DatasetProfile | null) => void;
  setSplitPlan: (plan: SplitPlan | null) => void;
  setProfileLoading: (loading: boolean) => void;
  setSplit: (split: SplitFractions) => void;
  setShuffle: (shuffle: boolean) => void;
  setSeed: (seed: number | undefined) => void;
  setStratify: (stratify: boolean) => void;
  setStratifyColumn: (column: string | null) => void;
}) {
  useEffect(() => {
    if (!parsedDataset || parsedDataset.rowCount === 0) return;
    const mapping = buildColumnMapping(columnRoles);
    if (Object.keys(mapping.inputs).length === 0) return;

    let cancelled = false;
    const handle = setTimeout(() => {
      setProfileLoading(true);
      profileDataset({
        dataset: parsedDataset.rows as Array<Record<string, unknown>>,
        column_mapping: mapping,
      })
        .then((response) => {
          if (cancelled) return;
          setDatasetProfile(response.profile);
          setSplitPlan(response.plan);
          if (splitModeRef.current === "auto") {
            setSplit(response.plan.fractions);
            setShuffle(response.plan.shuffle);
            setSeed(response.plan.seed);
            setStratify(response.plan.stratify);
            setStratifyColumn(response.plan.stratify_column);
          }
        })
        .catch(() => {
          /* non-blocking: manual controls still work */
        })
        .finally(() => {
          if (!cancelled) setProfileLoading(false);
        });
    }, 400);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [
    columnRoles,
    parsedDataset,
    setDatasetProfile,
    setProfileLoading,
    setSeed,
    setShuffle,
    setSplit,
    setSplitPlan,
    setStratify,
    setStratifyColumn,
    splitModeRef,
  ]);
}
