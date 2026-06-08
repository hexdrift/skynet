"use client";

import { Suspense } from "react";
import { DatasetsView } from "@/features/datasets";

export default function DatasetsPage() {
  return (
    <Suspense fallback={null}>
      <DatasetsView />
    </Suspense>
  );
}
