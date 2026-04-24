import Link from "next/link";
import { SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-5 text-center px-4">
      <SearchX className="size-14 text-muted-foreground/40" />
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-foreground">הדף לא נמצא</h1>
        <p className="text-sm text-muted-foreground">
          הכתובת שחיפשת לא קיימת או שהועברה למיקום אחר
        </p>
      </div>
      <Button asChild variant="outline">
        <Link href="/">חזרה ללוח בקרה</Link>
      </Button>
    </div>
  );
}
