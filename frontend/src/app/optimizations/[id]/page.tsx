import { Suspense } from "react";
import { OptimizationDetailView } from "@/features/optimizations";

export default function JobDetailPage() {
  return (
    <Suspense fallback={null}>
      <OptimizationDetailView />
    </Suspense>
  );
}
