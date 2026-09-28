"use client";

import type { Locale } from "@/shared/lib/locale";
import { getPublishedCatalog, serializeMessages } from "@/shared/lib/runtime-messages";

/**
 * Inline `window.__SKYNET_MESSAGES__` shim, rendered so the catalog reaches the
 * browser exactly once.
 *
 * A `<script>` emitted by the Server Component layout is serialized into the
 * RSC Flight payload as well as the HTML, so the ~300KB catalog shipped twice
 * per page. Rendering it from a client component whose only prop is the locale
 * keeps the Flight copy down to that prop: during SSR the catalog comes from
 * the per-locale registry the layout publishes, and during hydration from the
 * object the shim itself already installed, which serializes byte-identically.
 *
 * Args:
 *   locale: Locale resolved server-side for this request.
 */
export function MessagesShim({ locale }: { locale: Locale }) {
  const catalog =
    typeof window === "undefined"
      ? getPublishedCatalog(locale)
      : (window.__SKYNET_MESSAGES__ ?? {});
  return (
    <script
      id="skynet-messages"
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: serializeMessages(catalog) }}
    />
  );
}
