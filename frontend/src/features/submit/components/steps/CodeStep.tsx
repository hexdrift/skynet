"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { HelpTip } from "@/components/help-tip";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";

const CodeEditor = dynamic(
  () => import("@/components/code-editor").then((m) => m.CodeEditor),
  { ssr: false, loading: () => <div className="h-[200px] rounded-lg border border-border/40 bg-muted/20 animate-pulse" /> },
);

export function CodeStep({ w }: { w: SubmitWizardContext }) {
  const {
    signatureCode, setSignatureCode, setSignatureManuallyEdited, signatureValidation, setSignatureValidation,
    metricCode, setMetricCode, metricValidation, setMetricValidation,
    runSignatureValidation, runMetricValidation,
  } = w;

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg" data-tutorial="wizard-step-4">
      <CardHeader>
        <CardTitle className="text-lg">קוד</CardTitle>
        <CardDescription>הגדר את חתימת המשימה ופונקציית המדידה</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2" data-tutorial="signature-editor">
          <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"><HelpTip text="הגדרת שדות הקלט והפלט של המשימה — מה המודל מקבל ומה הוא צריך להחזיר">חתימה (Signature)</HelpTip></Label>
          <CodeEditor
            value={signatureCode}
            onChange={(v) => { setSignatureCode(v); setSignatureManuallyEdited(true); setSignatureValidation(null); }}
            height="180px"
            onRun={runSignatureValidation}
            validationResult={signatureValidation}
          />
        </div>
        <Separator />
        <div className="space-y-2" data-tutorial="metric-editor">
          <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"><HelpTip text="פונקציה שמודדת את איכות התשובה — מחזירה ציון מספרי לכל דוגמה">מטריקה (Metric)</HelpTip></Label>
          <CodeEditor
            value={metricCode}
            onChange={(v) => { setMetricCode(v); setMetricValidation(null); }}
            height="180px"
            onRun={runMetricValidation}
            validationResult={metricValidation}
          />
        </div>
      </CardContent>
    </Card>
  );
}
