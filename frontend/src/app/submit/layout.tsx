import type { Metadata } from "next";
import { Suspense } from "react";
import { Loader2 } from "lucide-react";
import { TERMS } from "@/shared/lib/terms";

export const metadata: Metadata = {
  title: "New Optimization",
  description: `צור אופטימיזציית פרומפטים חדשה עם DSPy — בחר ${TERMS.model}, העלה ${TERMS.dataset}, ושפר ביצועים`,
};

export default function SubmitLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="size-8 animate-spin text-primary" />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}
