"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { useSettingsModal } from "../hooks/use-settings-modal";

// The settings modal (1300+ lines, Recharts via UsageTab, @lobehub/icons via
// ByokKeysSection) never renders on first paint — the dialog starts closed —
// yet the always-mounted root layout pulls its entire static import graph
// into the shared first-load chunk on every route. Re-export it lazily so the
// chunk fetches post-hydration, off the first-paint critical path. Kept in a
// dedicated "use client" module because `ssr: false` is only valid in Client
// Components.
const LazySettingsModal = dynamic(() => import("./SettingsModal").then((m) => m.SettingsModal), {
  ssr: false,
});

// Idle-time warm-up bound: the dashboard's first data fetches have settled by
// then on any machine, so the modal chunk group stops competing with them.
const WARM_IDLE_TIMEOUT_MS = 3000;
// Browsers without requestIdleCallback (Safari) warm this long after `load`.
const WARM_FALLBACK_MS = 1500;

/**
 * Mount the lazy settings modal once it is needed, or once the page has gone
 * idle after loading — whichever comes first.
 *
 * Merely rendering the `dynamic()` component starts its chunk fetch, and that
 * group (settings, the admin tables, the provider icon set) is the
 * heaviest thing on a page load after the app itself. Holding it back until
 * idle keeps it off the same connection budget as the dashboard's first data
 * fetches; an explicit open still mounts it immediately, and once mounted it
 * stays mounted so close animations behave as before.
 */
export function SettingsModal() {
  const { open } = useSettingsModal();
  const [warm, setWarm] = React.useState(false);

  React.useEffect(() => {
    if (warm) return;
    if (open) {
      setWarm(true);
      return;
    }
    let idleId: number | undefined;
    let timer: number | undefined;
    const schedule = () => {
      if (typeof window.requestIdleCallback === "function") {
        idleId = window.requestIdleCallback(() => setWarm(true), { timeout: WARM_IDLE_TIMEOUT_MS });
      } else {
        timer = window.setTimeout(() => setWarm(true), WARM_FALLBACK_MS);
      }
    };
    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });
    return () => {
      window.removeEventListener("load", schedule);
      if (idleId !== undefined) window.cancelIdleCallback(idleId);
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [open, warm]);

  return warm ? <LazySettingsModal /> : null;
}
