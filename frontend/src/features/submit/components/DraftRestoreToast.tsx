"use client";

import { CircleNotch, ClockCounterClockwise, WarningCircle } from "@/shared/ui/icons";
import { Button } from "@/shared/ui/primitives/button";

export type DraftRestoreState = "offer" | "working" | "failed";

/**
 * The body of the restore offer: the question, one line saying which
 * stage it reopens on, and the two choices as labelled buttons,
 * secondary before primary and end-aligned like the wizard's own footer. It
 * never closes on its own, so the buttons are the only way out of the offer.
 * The width is fixed so the failure line replacing the summary, or the
 * spinner entering the primary button, never resizes the toast under the
 * cursor.
 */
export function DraftRestoreToast({
  title,
  summary,
  state,
  failureText,
  continueLabel,
  retryLabel,
  startNewLabel,
  onContinue,
  onStartNew,
}: {
  title: string;
  /** The stage the saved setup reopens on, or null when unknown. */
  summary: string | null;
  state: DraftRestoreState;
  failureText: string | null;
  continueLabel: string;
  retryLabel: string;
  startNewLabel: string;
  onContinue: () => void;
  onStartNew: () => void;
}) {
  const working = state === "working";
  const failed = state === "failed";
  const supporting = failed ? failureText : summary;

  return (
    <div className="flex w-72 max-w-full flex-col gap-3" data-tutorial="submit-draft-offer">
      <div className="flex items-start gap-2.5">
        {failed ? (
          <WarningCircle className="size-5 shrink-0 text-destructive" aria-hidden="true" />
        ) : (
          <ClockCounterClockwise
            className="size-5 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-pretty font-semibold leading-snug text-foreground">{title}</p>
          {supporting && (
            <p
              className={`mt-1 text-pretty text-xs leading-relaxed ${
                failed ? "text-destructive" : "text-muted-foreground"
              }`}
            >
              {supporting}
            </p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={onStartNew}
          disabled={working}
          data-tutorial="submit-draft-start-new"
        >
          {startNewLabel}
        </Button>
        <Button
          size="sm"
          onClick={onContinue}
          disabled={working}
          aria-busy={working || undefined}
          data-tutorial="submit-draft-continue"
        >
          {working && (
            <CircleNotch className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
          )}
          {failed ? retryLabel : continueLabel}
        </Button>
      </div>
    </div>
  );
}
