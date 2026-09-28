"use client";

import { cn } from "@/shared/lib/utils";
import { KBD_CLASS } from "@/shared/ui/kbd";
import * as React from "react";
import { toast } from "react-toastify";
import { msg } from "@/shared/lib/messages";
import { useUserPrefs } from "../hooks/use-user-prefs";
import { formatShortcut, recordShortcut } from "../lib/shortcuts";

const RECORDING_TIMEOUT_MS = 5000;

export function ShortcutRecorder() {
  const { prefs, setPref } = useUserPrefs();
  const [recording, setRecording] = React.useState(false);

  React.useEffect(() => {
    if (!recording) return;
    let captured = false;
    const timeoutId = window.setTimeout(() => {
      if (captured) return;
      setRecording(false);
      toast.warning(msg("settings.agent.shortcut.reserved_warning"), {
        autoClose: 4000,
        toastId: "shortcut-reserved",
      });
    }, RECORDING_TIMEOUT_MS);
    const handler = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === "Escape") {
        captured = true;
        setRecording(false);
        return;
      }
      const next = recordShortcut(e);
      if (!next) return;
      captured = true;
      setPref("agentShortcut", next);
      setRecording(false);
    };
    window.addEventListener("keydown", handler, true);
    return () => {
      window.clearTimeout(timeoutId);
      window.removeEventListener("keydown", handler, true);
    };
  }, [recording, setPref]);

  const display = formatShortcut(prefs.agentShortcut);

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => setRecording((v) => !v)}
        title={msg("settings.agent.shortcut.change")}
        className={cn(
          KBD_CLASS,
          "h-7 cursor-pointer px-2 font-mono text-xs transition-colors",
          recording
            ? "border-[var(--warning-border)] bg-[var(--warning-dim)] motion-safe:animate-pulse"
            : "hover:border-border hover:bg-muted",
        )}
      >
        {recording ? msg("settings.agent.shortcut.recording") : display}
      </button>
      <span className="text-[10px] text-muted-foreground/70 text-end leading-snug">
        {msg("settings.agent.shortcut.hint")}
      </span>
    </div>
  );
}
