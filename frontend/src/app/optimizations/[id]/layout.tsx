import type { Metadata } from "next";
import { Suspense } from "react";
import { Loader2 } from "lucide-react";
import { TERMS } from "@/shared/lib/terms";

export const metadata: Metadata = {
  title: "Optimization Details",
  description: `צפה בפרטי ה${TERMS.optimization}, לוגים, ציונים ותוצאות`,
};

export default function JobLayout({ children }: { children: React.ReactNode }) {
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
