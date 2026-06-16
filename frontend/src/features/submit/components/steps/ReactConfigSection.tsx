"use client";

import { Label } from "@/shared/ui/primitives/label";
import { Input } from "@/shared/ui/primitives/input";
import { HelpTip } from "@/shared/ui/help-tip";
import { cn } from "@/shared/lib/utils";
import { tip } from "@/shared/lib/tooltips";
import { msg } from "@/shared/lib/messages";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: ReadonlyArray<readonly [T, string]>;
  onChange: (value: T) => void;
}) {
  const index = Math.max(
    0,
    options.findIndex(([val]) => val === value),
  );
  return (
    <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
      <div
        aria-hidden
        className="absolute top-1 bottom-1 rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out pointer-events-none"
        style={{
          width: `calc((100% - 8px) / ${options.length})`,
          insetInlineStart: `calc(${index} * (100% / ${options.length}) + 4px)`,
        }}
      />
      {options.map(([val, label]) => (
        <button
          key={val}
          type="button"
          onClick={() => onChange(val)}
          aria-pressed={value === val}
          className={cn(
            "relative z-[1] flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors text-center cursor-pointer",
            value === val ? "text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function ReactConfigSection({ w }: { w: SubmitWizardContext }) {
  const { reactConfig, updateReactConfig } = w;
  const isLiveMcp = reactConfig.toolSourceKind === "live_mcp";

  return (
    <div
      className="space-y-5 rounded-xl border border-border/60 bg-muted/20 p-4"
      data-tutorial="react-config"
    >
      <div className="space-y-1">
        <Label className="font-semibold">{msg("submit.react.section_title")}</Label>
      </div>

      <div className="space-y-3">
        <Label className="text-sm">
          <HelpTip text={tip("react.tool_source")}>{msg("submit.react.tool_source_label")}</HelpTip>
        </Label>
        <Segmented
          value={reactConfig.toolSourceKind}
          onChange={(v) => updateReactConfig({ toolSourceKind: v })}
          options={
            [
              ["live_mcp", msg("submit.react.tool_source_live_mcp")],
              ["dataset_snapshot", msg("submit.react.tool_source_dataset_snapshot")],
            ] as const
          }
        />
        {isLiveMcp && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">
                <HelpTip text={tip("react.mcp_url")}>{msg("submit.react.mcp_url_label")}</HelpTip>
              </Label>
              <Input
                value={reactConfig.mcpUrl}
                dir="ltr"
                placeholder="http://localhost:8000/mcp/"
                className="h-9 font-mono text-xs"
                onChange={(e) => updateReactConfig({ mcpUrl: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">
                <HelpTip text={tip("react.auth")}>{msg("submit.react.auth_label")}</HelpTip>
              </Label>
              <Input
                type="password"
                value={reactConfig.mcpAuthHeader}
                dir="ltr"
                autoComplete="off"
                placeholder="Bearer …"
                className="h-9 font-mono text-xs"
                onChange={(e) => updateReactConfig({ mcpAuthHeader: e.target.value })}
              />
            </div>
          </div>
        )}
        <div className="space-y-1.5">
          <Label className="text-xs">
            <HelpTip text={tip("react.tool_filter")}>
              {msg("submit.react.tool_filter_label")}
            </HelpTip>
          </Label>
          <Input
            value={reactConfig.toolFilter}
            dir="ltr"
            placeholder={msg("submit.react.tool_filter_placeholder")}
            className="h-9 font-mono text-xs"
            onChange={(e) => updateReactConfig({ toolFilter: e.target.value })}
          />
        </div>
      </div>
    </div>
  );
}
