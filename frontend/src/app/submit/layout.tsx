import type { Metadata } from "next";
import { Suspense } from "react";
import { Loader2 } from "lucide-react";
import { TERMS } from "@/shared/lib/terms";

import { formatMsg } from "@/shared/lib/messages";
export const metadata: Metadata = {
  title: "New Optimization",
  description: formatMsg("auto.app.submit.layout.template.1", {
    p1: TERMS.model,
    p2: TERMS.dataset,
  }),
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
