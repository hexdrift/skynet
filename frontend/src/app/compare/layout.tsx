import type { Metadata } from "next";
import { Suspense } from "react";
import { Loader2 } from "lucide-react";

export const metadata: Metadata = {
 title: "Compare",
 description: "השוואת תוצאות בין שתי אופטימיזציות",
};

export default function CompareLayout({ children }: { children: React.ReactNode }) {
 return (
 <Suspense fallback={<div className="flex items-center justify-center min-h-[60vh]"><Loader2 className="size-8 animate-spin text-primary" /></div>}>
 {children}
 </Suspense>
 );
}
