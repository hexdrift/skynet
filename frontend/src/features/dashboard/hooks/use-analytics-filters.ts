import { useState } from "react";

export type AnalyticsFilters = {
  model: string;
  status: string;
  jobId: string | null;
  date: string | null;
  leaderboardLimit: number;
};

export type UseAnalyticsFiltersReturn = AnalyticsFilters & {
  setModel: (v: string) => void;
  setStatus: (v: string) => void;
  setJobId: (v: string | null) => void;
  setDate: (v: string | null) => void;
};

const LEADERBOARD_LIMIT = 5;

export function useAnalyticsFilters(): UseAnalyticsFiltersReturn {
  const [model, setModel] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [jobId, setJobId] = useState<string | null>(null);
  const [date, setDate] = useState<string | null>(null);

  return {
    model,
    status,
    jobId,
    date,
    leaderboardLimit: LEADERBOARD_LIMIT,
    setModel,
    setStatus,
    setJobId,
    setDate,
  };
}
