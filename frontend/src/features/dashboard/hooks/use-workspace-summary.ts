"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import {
  listDatasets,
  listTaggerSessions,
  setApiAuthToken,
  type DatasetSummary,
  type DatasetUsageMeter,
  type TaggerSessionSummary,
} from "@/shared/lib/api";

const RECENT_LIMIT = 2;

export interface WorkspaceTaggingSummary {
  total: number;
  recent: TaggerSessionSummary[];
}

export interface WorkspaceDatasetsSummary {
  total: number;
  recent: DatasetSummary[];
  usage: DatasetUsageMeter;
}

export interface WorkspaceSummary {
  tagging: WorkspaceTaggingSummary | null;
  datasets: WorkspaceDatasetsSummary | null;
  loading: boolean;
}

function byRecency(a: { updated_at: string }, b: { updated_at: string }): number {
  return b.updated_at.localeCompare(a.updated_at);
}

/**
 * Fetch the light workspace summaries the dashboard strip renders: labeling
 * sessions and the dataset library. Both calls are cheap list endpoints; each
 * fails soft to null so one outage never blanks the other card.
 */
export function useWorkspaceSummary(): WorkspaceSummary {
  const { data: session, status } = useSession();
  const [tagging, setTagging] = useState<WorkspaceTaggingSummary | null>(null);
  const [datasets, setDatasets] = useState<WorkspaceDatasetsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const token = session?.backendAccessToken;
  const hasToken = Boolean(token);
  // Declared before the fetch effect so the bearer is installed first on mount
  // (child effects run before ApiAuthTokenBridge's). Keyed on the token value
  // so a rotated token is picked up without re-fetching the summary below.
  useEffect(() => {
    if (token) setApiAuthToken(token);
  }, [token]);

  // Every NextAuth session refetch mints a fresh backend JWT (new iat/jti), so
  // keying this on the token *value* re-pulled both lists on each rotation
  // (twice during dev hydration). The data does not depend on which token
  // signed the request, so only re-run when auth state actually changes.
  useEffect(() => {
    if (status === "loading") return;
    let cancelled = false;
    void Promise.allSettled([listTaggerSessions({ limit: 12 }), listDatasets()]).then(
      ([sessions, library]) => {
        if (cancelled) return;
        if (sessions.status === "fulfilled") {
          setTagging({
            total: sessions.value.total,
            recent: [...sessions.value.items].sort(byRecency).slice(0, RECENT_LIMIT),
          });
        }
        if (library.status === "fulfilled") {
          setDatasets({
            total: library.value.datasets.length,
            recent: [...library.value.datasets].sort(byRecency).slice(0, RECENT_LIMIT),
            usage: library.value.usage,
          });
        }
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [status, hasToken]);

  return { tagging, datasets, loading };
}
