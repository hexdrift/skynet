"use client";

import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableCell,
  TableRow,
} from "@/shared/ui/primitives/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/primitives/card";
import { HelpTip } from "@/shared/ui/help-tip";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { msg } from "@/shared/lib/messages";

interface OptimizerComparisonData {
  name: string;
  avgImprovement: number;
  runs: number;
  avgRuntime: number;
}

interface ModelPerformanceData {
  name: string;
  usage: number;
  avgImprovement?: number;
}

export function OptimizerComparisonTable({ data }: { data: OptimizerComparisonData[] }) {
  const [sortKey, setSortKey] = useState<keyof OptimizerComparisonData>("avgImprovement");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    return [...data].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      const cmp = aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  const toggleSort = (key: keyof OptimizerComparisonData) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const TrendIcon = ({ value }: { value: number }) => {
    if (value > 0) return <TrendingUp className="size-3.5 text-emerald-600" />;
    if (value < 0) return <TrendingDown className="size-3.5 text-red-600" />;
    return <Minus className="size-3.5 text-muted-foreground" />;
  };

  return (
    <Card className="border-border/60">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold">
          <HelpTip text={tip("analytics.optimizer_comparison_table")}>
            {msg("auto.features.dashboard.components.analyticstables.1")}
            {TERMS.optimizer}
            {msg("auto.features.dashboard.components.analyticstables.2")}
          </HelpTip>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-b border-border/50">
                <TableHead
                  className="text-start cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => toggleSort("name")}
                >
                  {TERMS.optimizer} {sortKey === "name" && (sortDir === "asc" ? "↑" : "↓")}
                </TableHead>
                <TableHead
                  className="text-center cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => toggleSort("avgImprovement")}
                >
                  {msg("auto.features.dashboard.components.analyticstables.3")}
                  {sortKey === "avgImprovement" && (sortDir === "asc" ? "↑" : "↓")}
                </TableHead>
                <TableHead
                  className="text-center cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => toggleSort("runs")}
                >
                  {msg("auto.features.dashboard.components.analyticstables.4")}
                  {sortKey === "runs" && (sortDir === "asc" ? "↑" : "↓")}
                </TableHead>
                <TableHead
                  className="text-center cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => toggleSort("avgRuntime")}
                >
                  {msg("auto.features.dashboard.components.analyticstables.5")}
                  {sortKey === "avgRuntime" && (sortDir === "asc" ? "↑" : "↓")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((opt) => (
                <TableRow key={opt.name} className="border-border/40">
                  <TableCell className="font-medium" dir="ltr">
                    {opt.name}
                  </TableCell>
                  <TableCell className="text-center">
                    <div className="flex items-center justify-center gap-1.5">
                      <TrendIcon value={opt.avgImprovement} />
                      <span
                        className={`font-mono tabular-nums ${
                          opt.avgImprovement > 0
                            ? "text-emerald-700"
                            : opt.avgImprovement < 0
                              ? "text-red-600"
                              : ""
                        }`}
                      >
                        {opt.avgImprovement > 0 ? "+" : ""}
                        {opt.avgImprovement.toFixed(1)}%
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-center tabular-nums text-sm">{opt.runs}</TableCell>
                  <TableCell className="text-center tabular-nums text-sm" dir="ltr">
                    {Math.floor(opt.avgRuntime / 60)}:
                    {String(Math.floor(opt.avgRuntime % 60)).padStart(2, "0")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

export function ModelPerformanceTable({ data }: { data: ModelPerformanceData[] }) {
  const [sortKey, setSortKey] = useState<keyof ModelPerformanceData>("usage");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    return [...data].sort((a, b) => {
      const aVal = a[sortKey] ?? 0;
      const bVal = b[sortKey] ?? 0;
      const cmp = aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  const toggleSort = (key: keyof ModelPerformanceData) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const maxUsage = Math.max(...data.map((m) => m.usage));

  return (
    <Card className="border-border/60">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold">
          <HelpTip text={tip("analytics.model_performance_table")}>
            {msg("auto.features.dashboard.components.analyticstables.6")}
          </HelpTip>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-b border-border/50">
                <TableHead
                  className="text-start cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => toggleSort("name")}
                >
                  {msg("auto.features.dashboard.components.analyticstables.7")}
                  {sortKey === "name" && (sortDir === "asc" ? "↑" : "↓")}
                </TableHead>
                <TableHead
                  className="text-center cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => toggleSort("usage")}
                >
                  {msg("auto.features.dashboard.components.analyticstables.8")}
                  {sortKey === "usage" && (sortDir === "asc" ? "↑" : "↓")}
                </TableHead>
                <TableHead className="text-center">
                  {msg("auto.features.dashboard.components.analyticstables.9")}
                </TableHead>
                {data.some((m) => m.avgImprovement != null) && (
                  <TableHead
                    className="text-center cursor-pointer hover:text-foreground transition-colors"
                    onClick={() => toggleSort("avgImprovement")}
                  >
                    {msg("auto.features.dashboard.components.analyticstables.10")}
                    {sortKey === "avgImprovement" && (sortDir === "asc" ? "↑" : "↓")}
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((model) => (
                <TableRow key={model.name} className="border-border/40">
                  <TableCell className="font-mono text-sm" dir="ltr">
                    {model.name}
                  </TableCell>
                  <TableCell className="text-center tabular-nums">{model.usage}</TableCell>
                  <TableCell>
                    <div className="w-full max-w-[100px] mx-auto h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary/60 transition-all"
                        style={{ width: `${(model.usage / maxUsage) * 100}%` }}
                      />
                    </div>
                  </TableCell>
                  {data.some((m) => m.avgImprovement != null) && (
                    <TableCell className="text-center">
                      {model.avgImprovement != null ? (
                        <span
                          className={`font-mono tabular-nums ${
                            model.avgImprovement > 0
                              ? "text-emerald-700"
                              : model.avgImprovement < 0
                                ? "text-red-600"
                                : ""
                          }`}
                        >
                          {model.avgImprovement > 0 ? "+" : ""}
                          {model.avgImprovement.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
