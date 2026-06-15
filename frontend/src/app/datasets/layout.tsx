import type { Metadata } from "next";

import { msg } from "@/shared/lib/messages";

export const metadata: Metadata = {
  title: "Datasets",
  description: msg("datasets.subtitle"),
};

export default function DatasetsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
