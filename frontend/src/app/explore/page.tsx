"use client";

import { Suspense } from "react";
import { ExploreView } from "@/features/explore";

export default function ExplorePage() {
  return (
    <Suspense fallback={null}>
      <ExploreView />
    </Suspense>
  );
}
