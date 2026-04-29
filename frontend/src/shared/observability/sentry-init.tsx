"use client";

import { useEffect } from "react";
import { setMissingKeyHandler } from "@/shared/lib/i18n";

/**
 * Mount-time hook that initialises Sentry and wires the i18n
 * missing-key handler to ``error.unmapped_code`` breadcrumbs. No-op when
 * ``NEXT_PUBLIC_SENTRY_DSN`` is unset, and the SDK is lazy-imported so
 * air-gapped builds without a DSN never ship the bundle.
 */
export function SentryInit(): null {
  useEffect(() => {
    const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
    if (!dsn) return;

    let cancelled = false;
    void (async () => {
      const Sentry = await import("@sentry/browser");
      if (cancelled) return;
      Sentry.init({
        dsn,
        environment: process.env.NEXT_PUBLIC_SENTRY_ENV ?? "production",
      });
      setMissingKeyHandler((key, params) => {
        Sentry.addBreadcrumb({
          category: "i18n",
          message: "error.unmapped_code",
          level: "warning",
          data: { key, ...(params ?? {}) },
        });
      });
    })();

    return () => {
      cancelled = true;
      setMissingKeyHandler(null);
    };
  }, []);

  return null;
}
