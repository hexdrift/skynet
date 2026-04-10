import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Optimization Details",
  description: "צפה בפרטי האופטימיזציה, לוגים, מטריקות ותוצאות",
};

export default function JobLayout({ children }: { children: React.ReactNode }) {
  return children;
}
