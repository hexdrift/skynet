import { Suspense } from "react";
import { CompareView } from "@/features/compare";

export default function ComparePage() {
  return (
    <Suspense fallback={null}>
      <CompareView />
    </Suspense>
  );
}
