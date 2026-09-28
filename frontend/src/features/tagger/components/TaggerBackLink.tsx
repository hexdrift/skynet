"use client";

import { BackLink } from "@/shared/ui/back-link";
import { msg } from "@/shared/lib/messages";
import { clearRecentSession } from "@/shared/lib/recent-session";

/**
 * The quiet destination-labeled back link to the labeling-sessions list, shown
 * above every tagger session screen. By default it is a real ``<Link>`` to
 * ``/tagger`` that drops the resume mark — a deliberate exit, so the sidebar's
 * Text-tagging button offers a fresh start instead of bouncing back in. Pass
 * ``onExit`` for sessions still living on ``/tagger`` itself (the pre-persist
 * wizard flow), where "back" must reset local state rather than navigate. Pass
 * ``label`` to relabel the destination — e.g. a finished session's row view
 * points back to its own results overview, not out to the sessions list.
 */
export function TaggerBackLink({ onExit, label }: { onExit?: () => void; label?: string }) {
  const text = label ?? msg("tagger.session.back");
  if (onExit) return <BackLink label={text} onClick={onExit} />;
  return <BackLink label={text} href="/tagger" onClick={() => clearRecentSession("tagger")} />;
}
