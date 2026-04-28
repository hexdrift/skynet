"use client";

import { Settings } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { msg } from "@/shared/lib/messages";
import { useSettingsModal } from "../hooks/use-settings-modal";

interface SettingsTriggerProps {
  collapsed?: boolean;
}

export function SettingsTrigger({ collapsed = false }: SettingsTriggerProps) {
  const { setOpen } = useSettingsModal();

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="p-2 rounded-lg text-muted-foreground hover:bg-sidebar-accent/40 hover:text-foreground cursor-pointer transition-colors"
        title={msg("settings.title")}
        aria-label={msg("settings.open")}
      >
        <Settings className="size-4" />
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className={cn(
        "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium",
        "text-sidebar-foreground/60 hover:bg-sidebar-accent/40 hover:text-sidebar-foreground transition-all duration-200 hover:translate-x-[-2px] cursor-pointer w-full",
      )}
      aria-label={msg("settings.open")}
    >
      <Settings className="size-4" />
      <span>{msg("settings.title")}</span>
    </button>
  );
}
