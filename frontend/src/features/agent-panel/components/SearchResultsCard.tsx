"use client";

import { EmptyState } from "@/shared/ui/empty-state";
import { ScorePill } from "@/shared/ui/outcome-chip";
import { Badge } from "@/shared/ui/primitives/badge";
import * as React from "react";
import { Sparkle, TextT } from "@/shared/ui/icons";
import { formatMsg, msg } from "@/shared/lib/messages";

import type { AgentToolCall } from "@/shared/ui/agent/types";

import { ToolCallRow } from "./ToolCallRow";

interface SearchResultsCardProps {
  call: AgentToolCall;
}

interface SearchResultItem {
  optimization_id?: string;
  task_name?: string | null;
  summary_text?: string | null;
  optimizer_name?: string | null;
  winning_model?: string | null;
  module_name?: string | null;
  relevance?: number | null;
}

interface SearchPayload {
  results?: SearchResultItem[];
  total?: number;
  search_type?: "semantic" | "lexical" | null;
}

function extractPayload(call: AgentToolCall): SearchPayload | null {
  const payload = (call.payload ?? {}) as Record<string, unknown>;
  const result = payload.result;
  if (!result || typeof result !== "object" || Array.isArray(result)) return null;
  return result as SearchPayload;
}

function buildSummary(data: SearchPayload | null, isRunning: boolean): string | null {
  if (isRunning) return msg("auto.features.agent.panel.components.searchresultscard.running");
  if (!data) return null;
  const shown = data.results?.length ?? 0;
  const total = data.total ?? shown;
  if (shown === 0) return msg("auto.features.agent.panel.components.searchresultscard.empty");
  if (total > shown) {
    return formatMsg("auto.features.agent.panel.components.searchresultscard.count_truncated", {
      p1: shown,
      p2: total,
    });
  }
  if (shown === 1) return msg("auto.features.agent.panel.components.searchresultscard.count_one");
  return formatMsg("auto.features.agent.panel.components.searchresultscard.count_many", {
    p1: shown,
  });
}

export function SearchResultsCard({ call }: SearchResultsCardProps) {
  const data = extractPayload(call);
  const summary = buildSummary(data, call.status === "running");

  if (!data) {
    return <ToolCallRow call={call} summary={summary} />;
  }

  const results = data.results ?? [];
  const searchType = data.search_type ?? null;

  const customBody = (
    <div className="space-y-2">
      {searchType && <SearchTypeChip kind={searchType} />}
      {results.length === 0 ? (
        <EmptyState
          variant="compact"
          title={msg("auto.features.agent.panel.components.searchresultscard.empty")}
          className="gap-1 px-3 py-3"
        />
      ) : (
        <ul className="divide-y divide-border/40">
          {results.map((row, idx) => (
            <li key={row.optimization_id ?? idx} className="py-1.5 first:pt-0 last:pb-0">
              <SearchResultRow row={row} searchType={searchType} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return <ToolCallRow call={call} summary={summary} customBody={customBody} />;
}

function SearchTypeChip({ kind }: { kind: "semantic" | "lexical" }) {
  const isSemantic = kind === "semantic";
  const Icon = isSemantic ? Sparkle : TextT;
  const label = isSemantic
    ? msg("auto.features.agent.panel.components.searchresultscard.type_semantic")
    : msg("auto.features.agent.panel.components.searchresultscard.type_lexical");
  return (
    <Badge variant="outline" size="sm" title={label}>
      <Icon aria-hidden="true" />
      <span>{label}</span>
    </Badge>
  );
}

function SearchResultRow({
  row,
  searchType,
}: {
  row: SearchResultItem;
  searchType: "semantic" | "lexical" | null;
}) {
  const title =
    row.task_name?.trim() ||
    row.optimization_id?.slice(0, 8) ||
    msg("auto.features.agent.panel.components.searchresultscard.no_title");
  const summary = row.summary_text?.trim();
  const showRelevance = searchType === "semantic" && row.relevance != null;

  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-[0.75rem] font-medium text-foreground/90">
          {title}
        </span>
        {showRelevance && <RelevanceBadge relevance={row.relevance!} />}
      </div>
      {summary && (
        <p className="line-clamp-2 text-[0.6875rem] leading-snug text-foreground/65">{summary}</p>
      )}
    </div>
  );
}

function RelevanceBadge({ relevance }: { relevance: number }) {
  const pct = Math.max(0, Math.min(1, relevance)) * 100;
  return (
    <ScorePill tone="neutral" className="shrink-0" title={msg("explore.row.relevance.title")}>
      <span>{formatMsg("explore.row.relevance", { pct: pct.toFixed(0) })}</span>
    </ScorePill>
  );
}
