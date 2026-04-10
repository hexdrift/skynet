"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";

export function BasicsStep({ w }: { w: SubmitWizardContext }) {
  const { jobName, setJobName, jobDescription, setJobDescription, jobType, setOptimizationType } = w;

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg" data-tutorial="wizard-step-1">
      <CardHeader>
        <CardTitle className="text-lg">פרטים בסיסיים</CardTitle>
        <CardDescription>שם וסוג אופטימיזציה</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>שם האופטימיזציה</Label>
          <Input placeholder="לדוגמא: ניתוח שאלות מתמטיקה" value={jobName} onChange={(e) => setJobName(e.target.value)} dir="rtl" />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>תיאור</Label>
            <span className={cn("text-[10px] tabular-nums transition-colors", jobDescription.length > 280 ? "text-destructive font-medium" : "text-muted-foreground/50")}>{jobDescription.length}/280</span>
          </div>
          <textarea
            data-tutorial="job-description"
            value={jobDescription}
            onChange={(e) => { if (e.target.value.length <= 280) setJobDescription(e.target.value); }}
            placeholder="תיאור קצר של מטרת האופטימיזציה (אופציונלי)"
            dir="rtl"
            rows={4}
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50 resize-none"
          />
        </div>
        <Separator />
        <div className="space-y-3">
          <Label>סוג אופטימיזציה</Label>
          <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
            <div
              className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out"
              style={{ insetInlineStart: jobType === "run" ? 4 : "calc(50% + 2px)" }}
            />
            {([["run", "ריצה בודדת", "אופטימיזציה עם מודל יחיד"], ["grid_search", "סריקה", "סריקת זוגות מודלים למציאת השילוב הטוב ביותר"]] as const).map(([val, label, desc]) => (
              <button key={val} type="button" onClick={() => setOptimizationType(val)}
                className={cn("relative z-10 flex-1 rounded-md px-4 py-2.5 cursor-pointer text-center transition-colors duration-200",
                  jobType === val ? "text-foreground" : "text-foreground/60 hover:text-foreground")}>
                <span className="text-sm font-medium">{label}</span>
                <span className={cn("block text-[11px] mt-0.5 transition-colors duration-200", jobType === val ? "text-muted-foreground" : "text-foreground/40")}>{desc}</span>
              </button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
