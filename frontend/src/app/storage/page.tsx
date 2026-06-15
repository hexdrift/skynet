"use client";

import { Suspense } from "react";
import { StorageView } from "@/features/storage";

export default function StoragePage() {
  return (
    <Suspense fallback={null}>
      <StorageView />
    </Suspense>
  );
}
