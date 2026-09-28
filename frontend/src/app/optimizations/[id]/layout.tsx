import type { Metadata } from "next";
import { LoadingState } from "@/shared/ui/loading-state";
import { Suspense } from "react";
import { TERMS } from "@/shared/lib/terms";

import { formatMsg, msg } from "@/shared/lib/messages";
// generateMetadata, not a static `metadata` object: the description resolves
// i18n, which must follow the request locale rather than freeze at module load.
export function generateMetadata(): Metadata {
  return {
    title: msg("optimizations.detail.title"),
    description: formatMsg("auto.app.optimizations.id.layout.template.1", {
      p1: TERMS.optimization,
    }),
  };
}

export default function JobLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingState fullPage />}>{children}</Suspense>;
}
