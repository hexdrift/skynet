"use client";

import * as React from "react";
import {
  getStorageUsage,
  STORAGE_QUOTA_EVENT,
  type StorageUsageResponse,
} from "@/shared/lib/api";
import { StorageQuotaModal } from "./StorageQuotaModal";

const BYTES_PER_MB = 1024 * 1024;

/** Seed a provisional usage figure from the 409 envelope's MB-rounded params. */
function seedFromDetail(detail: unknown): StorageUsageResponse | null {
  if (!detail || typeof detail !== "object") return null;
  const { used_mb, quota_mb } = detail as { used_mb?: number; quota_mb?: number };
  if (typeof used_mb !== "number" || typeof quota_mb !== "number") return null;
  return { used_bytes: used_mb * BYTES_PER_MB, quota_bytes: quota_mb * BYTES_PER_MB, breakdown: {} };
}

/**
 * Global listener that surfaces the storage-budget modal whenever a write is
 * blocked by the account-wide quota. Mounted once at the app root: the central
 * ``request()`` path dispatches {@link STORAGE_QUOTA_EVENT}, this fetches the
 * exact breakdown and shows it — so every producer flow opens the one modal.
 *
 * The 409 envelope's MB-rounded ``used``/``quota`` seed the meter immediately so
 * the headline reads correctly while the precise per-category fetch is in flight
 * (and even if it fails).
 */
export function StorageQuotaModalHost() {
  const [open, setOpen] = React.useState(false);
  const [usage, setUsage] = React.useState<StorageUsageResponse | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    const onExceeded = (event: Event) => {
      setUsage(seedFromDetail((event as CustomEvent).detail));
      setOpen(true);
      setLoading(true);
      getStorageUsage()
        .then((res) => setUsage(res))
        .catch(() => {
          /* keep the seeded headline; the breakdown just stays empty */
        })
        .finally(() => setLoading(false));
    };
    window.addEventListener(STORAGE_QUOTA_EVENT, onExceeded);
    return () => window.removeEventListener(STORAGE_QUOTA_EVENT, onExceeded);
  }, []);

  return (
    <StorageQuotaModal
      open={open}
      usage={usage}
      loading={loading}
      onClose={() => setOpen(false)}
    />
  );
}
