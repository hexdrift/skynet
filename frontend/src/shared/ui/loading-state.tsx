import { CircleNotch } from "@/shared/ui/icons";
import { msg } from "@/shared/lib/messages";
import { cn } from "@/shared/lib/utils";

interface LoadingStateProps {
  /** Visible caption under the spinner (also what screen readers announce). */
  label?: string;
  /** Screen-reader-only label when there is no visible caption. */
  srLabel?: string;
  /** Route-level fallback: taller box and a bigger spinner. */
  fullPage?: boolean;
  className?: string;
}

/** Centered loader for a page, panel or dialog body. */
export function LoadingState({ label, srLabel, fullPage = false, className }: LoadingStateProps) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center gap-2 py-10",
        fullPage && "min-h-[60vh]",
        className,
      )}
    >
      <CircleNotch
        className={cn(
          "animate-spin text-primary motion-reduce:animate-none",
          fullPage ? "size-8" : "size-6",
        )}
        aria-hidden="true"
      />
      {label ? (
        <p className="text-xs text-muted-foreground">{label}</p>
      ) : (
        <span className="sr-only">{srLabel ?? msg("share.loading")}</span>
      )}
    </div>
  );
}
