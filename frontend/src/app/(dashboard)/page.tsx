"use client";

import { Suspense } from "react";
import { DashboardView } from "@/features/dashboard";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <DashboardView />
    </Suspense>
  );
}
