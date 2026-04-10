"use client";

import { Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";

export function DatasetStep({ w }: { w: SubmitWizardContext }) {
  const {
    parsedDataset,
    datasetFileName,
    fileInputRef,
    handleFileUpload,
    columnRoles,
    setColumnRoles,
  } = w;

  return (
    <Card
      className=" border-border/50 bg-card/80 backdrop-blur-xl shadow-lg"
      data-tutorial="wizard-step-2"
    >
      <CardHeader>
        <CardTitle className="text-lg">דאטאסט</CardTitle>
        <CardDescription>העלה קובץ נתונים והגדר את מיפוי העמודות</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <label
          className={cn(
            "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-300 block group",
            parsedDataset
              ? "border-primary/40 bg-primary/5"
              : "hover:border-primary/50 hover:bg-muted/30",
          )}
        >
          <Upload className="h-10 w-10 mx-auto mb-3 text-muted-foreground group-hover:text-primary/70 transition-colors duration-300" />
          <p
            className="text-sm font-medium truncate max-w-full px-4"
            title={datasetFileName ?? undefined}
          >
            {datasetFileName ?? "לחץ להעלאת קובץ CSV או JSON"}
          </p>
          {parsedDataset && (
            <Badge variant="secondary" className="mt-2">
              {parsedDataset.rowCount} שורות · {parsedDataset.columns.length} עמודות
            </Badge>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            className="hidden"
            onChange={handleFileUpload}
          />
        </label>

        {parsedDataset && parsedDataset.columns.length > 0 && (
          <>
            <Separator />
            <div className="space-y-3" data-tutorial="column-mapping">
              <Label>מיפוי עמודות</Label>
              <p className="text-xs text-muted-foreground">סמן כל עמודה כקלט, פלט, או התעלם</p>
              <div className="space-y-2">
                {parsedDataset.columns.map((col) => (
                  <div key={col} className="flex items-center justify-between gap-2">
                    <span className="text-xs sm:text-sm font-mono truncate" dir="ltr">
                      {col}
                    </span>
                    {(() => {
                      const options = [
                        ["input", "קלט"],
                        ["output", "פלט"],
                        ["ignore", "התעלם"],
                      ] as const;
                      const activeIdx = options.findIndex(([v]) => v === columnRoles[col]);
                      const pillLeft =
                        activeIdx >= 0 ? `calc(${activeIdx} * 100% / 3 + 2px)` : "2px";
                      return (
                        <div
                          className="relative inline-grid grid-cols-3 shrink-0 rounded-lg bg-muted p-0.5 gap-0.5"
                          dir="rtl"
                        >
                          <div
                            className="absolute top-0.5 bottom-0.5 rounded-md bg-stone-500/15 shadow-sm transition-[inset-inline-start] duration-100 ease-out"
                            style={{ width: "calc((100% - 6px) / 3)", insetInlineStart: pillLeft }}
                          />
                          {options.map(([val, label]) => (
                            <button
                              key={val}
                              type="button"
                              onClick={() => setColumnRoles((prev) => ({ ...prev, [col]: val }))}
                              className={cn(
                                "relative z-10 rounded-md px-3 py-1 text-xs font-medium text-center transition-colors duration-100 cursor-pointer",
                                columnRoles[col] === val
                                  ? "text-stone-600"
                                  : "text-muted-foreground hover:text-foreground",
                              )}
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      );
                    })()}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
