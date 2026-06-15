import type { Metadata } from "next";

import { msg } from "@/shared/lib/messages";

export const metadata: Metadata = {
  title: "Storage",
  description: msg("storage.page.subtitle"),
};

export default function StorageLayout({ children }: { children: React.ReactNode }) {
  return children;
}
