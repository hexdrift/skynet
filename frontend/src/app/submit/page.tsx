"use client";

import { Suspense } from "react";
import { SubmitWizard } from "@/features/submit";

export default function SubmitPage() {
  return (
    <Suspense fallback={null}>
      <SubmitWizard />
    </Suspense>
  );
}
