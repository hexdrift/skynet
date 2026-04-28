import type { Metadata } from "next";
import { Suspense } from "react";
import { Loader2 } from "lucide-react";
import { TERMS } from "@/shared/lib/terms";

import { formatMsg } from "@/shared/lib/messages";
export const metadata: Metadata = {
  title: "Text Tagger",
  description: formatMsg("auto.app.tagger.layout.template.1", { p1: TERMS.dataset }),
};

export default function TaggerLayout({ children }: { children: React.ReactNode }) {
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
