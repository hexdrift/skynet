import type { Metadata } from "next";
import { TERMS } from "@/shared/lib/terms";

import { formatMsg } from "@/shared/lib/messages";
export const metadata: Metadata = {
  title: "Explore",
  description: formatMsg("auto.app.explore.layout.template.1", { p1: TERMS.optimizationPlural }),
};

export default function ExploreLayout({ children }: { children: React.ReactNode }) {
  return children;
}
