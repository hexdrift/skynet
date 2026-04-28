"use client";

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
        className={
          recording
            ? "font-mono text-xs bg-amber-100 border border-amber-300 px-2 py-1 rounded animate-pulse cursor-pointer"
            : "font-mono text-xs bg-muted/60 border border-border/60 px-2 py-1 rounded cursor-pointer hover:bg-muted hover:border-border transition-colors"
        }
      >
        {recording ? msg("settings.agent.shortcut.recording") : display}
      </button>
      <span className="text-[10px] text-muted-foreground/70 whitespace-nowrap">
        {msg("settings.agent.shortcut.hint")}
      </span>
    </div>
  );
}
