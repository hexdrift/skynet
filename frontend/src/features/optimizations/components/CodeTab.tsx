"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { Code, Sparkles, Wrench } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/primitives/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/primitives/tabs";
import { FadeIn } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import { Skeleton } from "@/shared/ui/skeleton";
import type { OptimizedPredictor, ReactOverlay } from "@/shared/types/api";
import { tip } from "@/shared/lib/tooltips";
import { CopyButton } from "./ui-primitives";
import { msg } from "@/shared/lib/messages";

const CodeEditor = dynamic(() => import("@/shared/ui/code-editor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => <Skeleton height={180} borderRadius={8} />,
});

export function CodeTab({
  signatureCode,
  metricCode,
  optimizedPrompt,
  reactOverlay,
}: {
  signatureCode: string;
  metricCode: string;
  optimizedPrompt: OptimizedPredictor | null;
  reactOverlay?: ReactOverlay | null;
}) {
  const [activeCodeTab, setActiveCodeTab] = useState<string>("signature");
  return (
    <>
      <FadeIn>
        <p className="text-sm text-muted-foreground">
          {msg("auto.features.optimizations.components.codetab.1")}
        </p>
      </FadeIn>
      {(signatureCode || metricCode) && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Code className="size-4" />
              <HelpTip text={tip("code.signature_metric")}>
                {msg("auto.features.optimizations.components.codetab.2")}
              </HelpTip>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs
              defaultValue={signatureCode ? "signature" : "metric"}
              dir="ltr"
              onValueChange={setActiveCodeTab}
            >
              <TabsList className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto">
                {signatureCode && metricCode && (
                  <div
                    className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
                    style={{
                      insetInlineStart: activeCodeTab === "signature" ? 4 : "calc(50% + 2px)",
                    }}
                  />
                )}
                {signatureCode && (
                  <TabsTrigger
                    value="signature"
                    className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                  >
                    {msg("auto.features.optimizations.components.codetab.3")}
                  </TabsTrigger>
                )}
                {metricCode && (
                  <TabsTrigger
                    value="metric"
                    className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                  >
                    {msg("auto.features.optimizations.components.codetab.4")}
                  </TabsTrigger>
                )}
              </TabsList>
              {signatureCode && (
                <TabsContent value="signature">
                  <CodeEditor
                    value={signatureCode}
                    onChange={() => {}}
                    height={`${(signatureCode.split("\n").length + 1) * 19.6 + 8}px`}
                    readOnly
                  />
                </TabsContent>
              )}
              {metricCode && (
                <TabsContent value="metric">
                  <CodeEditor
                    value={metricCode}
                    onChange={() => {}}
                    height={`${(metricCode.split("\n").length + 1) * 19.6 + 8}px`}
                    readOnly
                  />
                </TabsContent>
              )}
            </Tabs>
          </CardContent>
        </Card>
      )}

      {optimizedPrompt && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="size-4" />
              <HelpTip text={tip("prompt.optimized")}>
                {msg("auto.features.optimizations.components.codetab.5")}
              </HelpTip>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="relative group">
              <pre
                className="text-sm font-mono bg-muted/50 rounded-lg p-4 pe-10 overflow-x-auto whitespace-pre-wrap leading-relaxed"
                dir="ltr"
              >
                {optimizedPrompt.formatted_prompt}
              </pre>
              <CopyButton
                text={optimizedPrompt.formatted_prompt}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100"
              />
            </div>
            {optimizedPrompt.demos && optimizedPrompt.demos.length > 0 && (
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-xs text-muted-foreground mb-2">
                  {optimizedPrompt.demos.length}{" "}
                  <HelpTip text={tip("prompt.demonstrations")}>
                    {msg("auto.features.optimizations.components.codetab.6")}
                  </HelpTip>
                </p>
                <div className="space-y-2">
                  {optimizedPrompt.demos.map((demo, i) => (
                    <div key={i} className="text-xs font-mono bg-muted/50 rounded-lg p-3" dir="ltr">
                      {Object.entries(demo.inputs).map(([k, v]) => (
                        <div key={k}>
                          <span className="text-muted-foreground">{k}:</span> {String(v)}
                        </div>
                      ))}
                      {Object.entries(demo.outputs).map(([k, v]) => (
                        <div key={k}>
                          <span className="text-stone-600">{k}:</span> {String(v)}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {reactOverlay && Object.keys(reactOverlay.tool_descriptions).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Wrench className="size-4" />
              {msg("optimizations.react.optimized_tools")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {Object.entries(reactOverlay.tool_descriptions).map(([name, desc]) => {
              const renamed = reactOverlay.tool_names?.[name];
              const argDescs = reactOverlay.tool_arg_descriptions?.[name];
              return (
                <div key={name} className="rounded-lg bg-muted/40 p-3">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-mono text-xs text-foreground" dir="ltr">
                      {renamed || name}
                    </span>
                    {renamed && renamed !== name && (
                      <span className="text-[0.625rem] text-muted-foreground" dir="ltr">
                        ({name})
                      </span>
                    )}
                  </div>
                  <p className="text-xs leading-relaxed text-muted-foreground" dir="auto">
                    {desc}
                  </p>
                  {argDescs && Object.keys(argDescs).length > 0 && (
                    <div className="mt-1.5 space-y-0.5 border-t border-border/40 pt-1.5">
                      {Object.entries(argDescs).map(([arg, argDesc]) => (
                        <div key={arg} className="text-[0.6875rem] text-muted-foreground" dir="auto">
                          <span className="font-mono text-foreground/70" dir="ltr">
                            {arg}
                          </span>
                          {argDesc ? ` — ${argDesc}` : ""}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </>
  );
}
