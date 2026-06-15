import type { Metadata } from "next";

// Share pages must never be indexed — they expose a read-only dataset to anyone
// with the link, not to crawlers.
export const metadata: Metadata = {
  title: "Shared dataset",
  robots: { index: false, follow: false },
};

export default function DatasetShareLayout({ children }: { children: React.ReactNode }) {
  return children;
}
