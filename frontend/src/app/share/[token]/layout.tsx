import type { Metadata } from "next";

// Public share pages must never be indexed by search engines — they expose a
// (scrubbed) read-only optimization to anyone with the link, not to crawlers.
export const metadata: Metadata = {
  title: "Shared optimization",
  robots: { index: false, follow: false },
};

export default function ShareLayout({ children }: { children: React.ReactNode }) {
  return children;
}
