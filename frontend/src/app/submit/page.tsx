"use client";

import { Suspense } from "react";
import { SubmitEntry } from "@/features/submit";

export default function SubmitPage() {
  return (
    <Suspense fallback={null}>
      <SubmitEntry />
    </Suspense>
  );
}
