import { Suspense } from "react";
import { OptimizationDetailGate } from "@/features/optimizations";

export default function JobDetailPage() {
  return (
    <Suspense fallback={null}>
      <OptimizationDetailGate />
    </Suspense>
  );
}
