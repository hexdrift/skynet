"use client";

import { Suspense, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ExploreView } from "@/features/explore";
import { useUserPrefs } from "@/features/settings";

export default function ExplorePage() {
  const router = useRouter();
  const { prefs } = useUserPrefs();

  useEffect(() => {
    if (!prefs.advancedMode) router.replace("/");
  }, [prefs.advancedMode, router]);

  if (!prefs.advancedMode) return null;

  return (
    <Suspense fallback={null}>
      <ExploreView />
    </Suspense>
  );
}
