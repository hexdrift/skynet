import type { Metadata } from "next";
import { Suspense } from "react";
import { Loader2 } from "lucide-react";
import { TERMS } from "@/shared/lib/terms";

export const metadata: Metadata = {
  title: "Text Tagger",
  description: `הגדרות תיוג — סווג, תייג וחלץ מידע מ${TERMS.dataset}ים`,
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
