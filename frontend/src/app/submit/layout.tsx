import type { Metadata } from "next";
import { Suspense } from "react";
import { Loader2 } from "lucide-react";

export const metadata: Metadata = {
 title: "Skynet",
 description: "צור אופטימיזציית פרומפטים חדשה עם DSPy — בחר מודל, העלה דאטאסט, ושפר ביצועים",
};

export default function SubmitLayout({ children }: { children: React.ReactNode }) {
 return (
 <Suspense fallback={<div className="flex items-center justify-center min-h-[60vh]"><Loader2 className="size-8 animate-spin text-primary" /></div>}>
 {children}
 </Suspense>
 );
}
