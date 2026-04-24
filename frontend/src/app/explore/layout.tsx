import type { Metadata } from "next";
import { TERMS } from "@/shared/lib/terms";

export const metadata: Metadata = {
  title: "Explore",
  description: `מה ${TERMS.optimizationPlural} מריצים עכשיו ומה הם מנסים לפתור`,
};

export default function ExploreLayout({ children }: { children: React.ReactNode }) {
  return children;
}
