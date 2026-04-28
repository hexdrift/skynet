"use client";

import * as React from "react";
import { signOut, useSession } from "next-auth/react";
import { toast } from "react-toastify";
import {
  Columns2,
  ExternalLink,
  Keyboard,
  LogOut,
  RotateCcw,
  Server,
  Shield,
  ShieldCheck,
  Sparkles,
  User,
  Info,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/primitives/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/primitives/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/primitives/select";
import { Switch } from "@/shared/ui/primitives/switch";
import { Button } from "@/shared/ui/primitives/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";

import { useUserPrefs } from "../hooks/use-user-prefs";
import { useSettingsModal } from "../hooks/use-settings-modal";
import { ShortcutRecorder } from "./ShortcutRecorder";

interface SettingsRowProps {
  label: string;
  description?: string;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}

function SettingsRow({ label, description, icon: Icon, children }: SettingsRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border/40 last:border-b-0">
      <div className="flex items-start gap-3 flex-1 min-w-0">
        {Icon && (
          <Icon className="size-4 mt-0.5 text-muted-foreground shrink-0" aria-hidden="true" />
        )}
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="text-sm font-medium text-foreground">{label}</span>
          {description && (
            <span className="text-xs text-muted-foreground/80">{description}</span>
          )}
        </div>
      </div>
      <div className="shrink-0 flex items-center gap-2">{children}</div>
    </div>
  );
}

function WizardTab() {
  const { prefs, setPref } = useUserPrefs();

  return (
    <div className="space-y-1">
      <SettingsRow icon={Sparkles} label={msg("settings.wizard.code_assist.label")}>
        <Select
          value={prefs.wizardCodeAssist}
          onValueChange={(v) => setPref("wizardCodeAssist", v as typeof prefs.wizardCodeAssist)}
        >
          <SelectTrigger className="min-w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">{msg("settings.wizard.code_assist.auto")}</SelectItem>
            <SelectItem value="manual">{msg("settings.wizard.code_assist.manual")}</SelectItem>
          </SelectContent>
        </Select>
      </SettingsRow>

      <SettingsRow icon={Columns2} label={msg("settings.wizard.split_mode.label")}>
        <Select
          value={prefs.wizardSplitMode}
          onValueChange={(v) => setPref("wizardSplitMode", v as typeof prefs.wizardSplitMode)}
        >
          <SelectTrigger className="min-w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">{msg("settings.wizard.split_mode.auto")}</SelectItem>
            <SelectItem value="manual">{msg("settings.wizard.split_mode.manual")}</SelectItem>
          </SelectContent>
        </Select>
      </SettingsRow>
    </div>
  );
}

function AgentTab() {
  const { prefs, setPref } = useUserPrefs();

  return (
    <div className="space-y-1">
      <SettingsRow
        icon={Shield}
        label={msg("settings.agent.trust.label")}
        description={msg("settings.agent.trust.description")}
      >
        <Select
          value={prefs.agentTrustMode}
          onValueChange={(v) => setPref("agentTrustMode", v as typeof prefs.agentTrustMode)}
        >
          <SelectTrigger className="min-w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ask">{msg("settings.agent.trust.ask")}</SelectItem>
            <SelectItem value="auto_safe">{msg("settings.agent.trust.auto_safe")}</SelectItem>
            <SelectItem value="yolo">{msg("settings.agent.trust.yolo")}</SelectItem>
          </SelectContent>
        </Select>
      </SettingsRow>

      <SettingsRow
        icon={Keyboard}
        label={msg("settings.agent.shortcut.label")}
        description={msg("settings.agent.shortcut.description")}
      >
        <ShortcutRecorder />
      </SettingsRow>
    </div>
  );
}

function AccountTab() {
  const { data: session } = useSession();
  const { prefs, setPref } = useUserPrefs();
  const username = session?.user?.name ?? "";
  const role = (session?.user as Record<string, unknown> | undefined)?.role;
  const isAdmin = role === "admin";

  return (
    <div className="space-y-1">
      <SettingsRow icon={User} label={msg("settings.account.username.label")}>
        <span className="text-sm font-mono text-foreground" dir="ltr">
          {username || msg("settings.account.signed_out")}
        </span>
      </SettingsRow>

      <SettingsRow icon={ShieldCheck} label={msg("settings.account.role.label")}>
        <span className="text-xs uppercase tracking-wide font-semibold text-muted-foreground">
          {isAdmin ? msg("settings.account.role.admin") : msg("settings.account.role.user")}
        </span>
      </SettingsRow>

      <SettingsRow
        icon={Sparkles}
        label={msg("settings.account.advanced.label")}
        description={msg("settings.account.advanced.description")}
      >
        <Switch
          checked={prefs.advancedMode}
          onCheckedChange={(v) => setPref("advancedMode", v)}
        />
      </SettingsRow>

      <SettingsRow icon={LogOut} label={msg("settings.account.logout.label")}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon-sm"
              onClick={() => signOut({ callbackUrl: "/login" })}
              disabled={!username}
              aria-label={msg("settings.account.logout.action")}
            >
              <LogOut className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{msg("settings.account.logout.action")}</TooltipContent>
        </Tooltip>
      </SettingsRow>
    </div>
  );
}

function AboutTab() {
  const { resetAll } = useUserPrefs();
  const { apiUrl, appVersion: version } = getRuntimeEnv();
  const docsUrl = `${apiUrl}/scalar`;

  const handleResetAll = React.useCallback(() => {
    resetAll();
    toast.success(msg("settings.about.reset_all.success"));
  }, [resetAll]);

  return (
    <div className="space-y-1">
      <SettingsRow icon={Info} label={msg("settings.about.version.label")}>
        <span className="text-sm font-mono text-foreground" dir="ltr">
          {version}
        </span>
      </SettingsRow>

      <SettingsRow icon={Server} label={msg("settings.about.api_url.label")}>
        <span className="text-xs font-mono text-muted-foreground" dir="ltr">
          {apiUrl}
        </span>
      </SettingsRow>

      <SettingsRow icon={ExternalLink} label={msg("settings.about.docs.label")}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon-sm"
              asChild
              aria-label={msg("settings.about.docs.action")}
            >
              <a href={docsUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="size-3.5" />
              </a>
            </Button>
          </TooltipTrigger>
          <TooltipContent>{msg("settings.about.docs.action")}</TooltipContent>
        </Tooltip>
      </SettingsRow>

      <SettingsRow
        icon={RotateCcw}
        label={msg("settings.about.reset_all.label")}
        description={msg("settings.about.reset_all.description")}
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon-sm"
              onClick={handleResetAll}
              className="text-destructive hover:text-destructive"
              aria-label={msg("settings.about.reset_all.action")}
            >
              <RotateCcw className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{msg("settings.about.reset_all.action")}</TooltipContent>
        </Tooltip>
      </SettingsRow>
    </div>
  );
}

const SETTINGS_TAB_ORDER = [
  "wizard",
  "agent",
  "account",
  "about",
] as const;
type SettingsTab = (typeof SETTINGS_TAB_ORDER)[number];

const SETTINGS_TAB_TRIGGER_CLASS =
  "relative z-10 w-full min-w-0 whitespace-nowrap text-center text-[clamp(0.75rem,2.2vw,0.875rem)] rounded-md px-1.5 py-2 font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5 leading-tight";

export function SettingsModal() {
  const { open, setOpen } = useSettingsModal();
  const [activeTab, setActiveTab] = React.useState<SettingsTab>("wizard");
  const tabIndex = SETTINGS_TAB_ORDER.indexOf(activeTab);
  const indicatorOffset =
    tabIndex <= 0
      ? "4px"
      : `calc(${((tabIndex * 100) / SETTINGS_TAB_ORDER.length).toFixed(3)}% + ${(4 - (tabIndex * 4) / SETTINGS_TAB_ORDER.length).toFixed(3)}px)`;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-2xl sm:max-w-2xl p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-border/40">
          <DialogTitle>{msg("settings.title")}</DialogTitle>
          <DialogDescription>{msg("settings.subtitle")}</DialogDescription>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as SettingsTab)}
          dir="rtl"
          className="px-6 pb-6 pt-2"
        >
          <TabsList className="relative grid grid-cols-4 w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto items-stretch">
            <div
              className="absolute top-1 bottom-1 rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
              style={{
                width: "calc(25% - 5px)",
                insetInlineStart: indicatorOffset,
              }}
            />
            <TabsTrigger value="wizard" className={SETTINGS_TAB_TRIGGER_CLASS}>
              {msg("settings.tab.wizard")}
            </TabsTrigger>
            <TabsTrigger value="agent" className={SETTINGS_TAB_TRIGGER_CLASS}>
              {msg("settings.tab.agent")}
            </TabsTrigger>
            <TabsTrigger value="account" className={SETTINGS_TAB_TRIGGER_CLASS}>
              {msg("settings.tab.account")}
            </TabsTrigger>
            <TabsTrigger value="about" className={SETTINGS_TAB_TRIGGER_CLASS}>
              {msg("settings.tab.about")}
            </TabsTrigger>
          </TabsList>

          <div className="mt-4 max-h-[60vh] overflow-y-auto pr-1">
            <TabsContent value="wizard">
              <WizardTab />
            </TabsContent>
            <TabsContent value="agent">
              <AgentTab />
            </TabsContent>
            <TabsContent value="account">
              <AccountTab />
            </TabsContent>
            <TabsContent value="about">
              <AboutTab />
            </TabsContent>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
