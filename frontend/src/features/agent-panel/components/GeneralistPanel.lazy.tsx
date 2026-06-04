"use client";

import dynamic from "next/dynamic";

// The full agent-chat tree (conversation store, transcript, react-markdown via
// agent-bubble) never renders on first paint, yet the always-mounted AppShell
// pulls it into the shared first-load chunk through the feature barrel. Re-export
// a lazily-loaded GeneralistPanel so the body code-splits out of the barrel's
// static graph; it owns the floating launcher, so it stays mounted and its chunk
// fetches post-hydration, off the first-paint critical path. Kept in a dedicated
// "use client" module because `ssr: false` is only valid in Client Components.
export const GeneralistPanel = dynamic(
  () => import("./GeneralistPanel").then((m) => m.GeneralistPanel),
  { ssr: false },
);
