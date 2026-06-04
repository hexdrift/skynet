"use client";

import dynamic from "next/dynamic";

// ConceptsGuide is a 1625-line tutorial modal shown only on demand, but the
// always-mounted AppShell pulls it into the shared first-load chunk through the
// feature barrel. Re-export a lazily-loaded version so it code-splits out of the
// barrel's static graph; the shell additionally gates it on `conceptsOpen`, so
// the chunk only fetches when the user opens it. Kept in a dedicated "use client"
// module because `ssr: false` is only valid in Client Components.
export const ConceptsGuide = dynamic(
  () => import("./concepts-guide").then((m) => m.ConceptsGuide),
  { ssr: false },
);
