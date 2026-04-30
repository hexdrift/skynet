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
  RefreshCw,
  Save,
  Trash2,
  Users,
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
import { Input } from "@/shared/ui/primitives/input";
import { NumberInput } from "@/shared/ui/number-input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import {
  deleteUserQuotaOverride,
  getUserQuotaOverrides,
  setUserQuotaOverride,
  type UserQuotaOverride,
} from "@/shared/lib/api";

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

function AdminTab() {
  const { data: session } = useSession();
  const [username, setUsername] = React.useState("");
  const [quota, setQuota] = React.useState<number | "">("");
  const [defaultQuota, setDefaultQuota] = React.useState<number | null>(null);
  const [overrides, setOverrides] = React.useState<UserQuotaOverride[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);

  const loadQuotas = React.useCallback(async () => {
    if (!session?.backendAccessToken) return;
    setLoading(true);
    try {
      const data = await getUserQuotaOverrides();
      setDefaultQuota(data.default_quota);
      setOverrides(data.overrides);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [session?.backendAccessToken]);

  React.useEffect(() => {
    void loadQuotas();
  }, [loadQuotas]);

  const handleSave = React.useCallback(async () => {
    const normalizedUsername = username.trim();
    if (!normalizedUsername) {
      toast.error(msg("settings.admin.quotas.username_required"));
      return;
    }
    if (quota === "") {
      toast.error(msg("settings.admin.quotas.quota_required"));
      return;
    }
    if (!Number.isFinite(quota) || quota < 1) {
      toast.error(msg("settings.admin.quotas.quota_invalid"));
      return;
    }
    setSaving(true);
    try {
      await setUserQuotaOverride(normalizedUsername, quota);
      toast.success(msg("settings.admin.quotas.saved"));
      setUsername("");
      setQuota("");
      await loadQuotas();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }, [loadQuotas, quota, username]);

  const handleDelete = React.useCallback(
    async (targetUsername: string) => {
      setSaving(true);
      try {
        await deleteUserQuotaOverride(targetUsername);
        toast.success(msg("settings.admin.quotas.deleted"));
        await loadQuotas();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : String(err));
      } finally {
        setSaving(false);
      }
    },
    [loadQuotas],
  );

  return (
    <div className="space-y-4">
      {!session?.backendAccessToken && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {msg("settings.admin.quotas.auth_missing")}
        </div>
      )}

      <SettingsRow
        icon={Users}
        label={msg("settings.admin.quotas.title")}
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon-sm"
              onClick={() => void loadQuotas()}
              disabled={loading}
              aria-label={msg("settings.admin.quotas.refresh")}
            >
              <RefreshCw className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{msg("settings.admin.quotas.refresh")}</TooltipContent>
        </Tooltip>
      </SettingsRow>

      <div className="grid gap-3 rounded-lg border border-border/50 bg-muted/20 p-3 sm:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto] sm:items-end">
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">
            {msg("settings.admin.quotas.username")}
          </span>
          <Input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder={msg("settings.admin.quotas.username_placeholder")}
            dir="ltr"
          />
        </label>
        <label className="space-y-1.5">
          <span className="flex items-baseline justify-between gap-2 text-xs font-medium text-muted-foreground">
            <span>{msg("settings.admin.quotas.quota")}</span>
            {defaultQuota != null && (
              <span className="font-mono tabular-nums text-muted-foreground/70" dir="ltr">
                {msg("settings.admin.quotas.default")}: {defaultQuota}
              </span>
            )}
          </span>
          <NumberInput
            value={quota}
            onChange={setQuota}
            min={1}
          />
        </label>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="default"
              size="icon"
              onClick={handleSave}
              disabled={saving || loading}
              className="size-9 rounded-xl"
              aria-label={msg("settings.admin.quotas.save")}
            >
              <Save className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{msg("settings.admin.quotas.save")}</TooltipContent>
        </Tooltip>
      </div>

      <div className="overflow-hidden rounded-lg border border-border/50">
        {overrides.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            {loading ? msg("settings.admin.quotas.refresh") : msg("settings.admin.quotas.empty")}
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {overrides.map((item) => (
              <div
                key={item.username}
                className="grid gap-3 px-3 py-3 sm:grid-cols-[minmax(0,1.4fr)_0.7fr_0.7fr_0.9fr_auto] sm:items-center"
              >
                <span className="min-w-0 truncate font-mono text-xs text-foreground" dir="ltr">
                  {item.username}
                </span>
                <span className="text-xs text-muted-foreground">
                  {item.quota == null ? msg("settings.admin.quotas.unlimited_label") : item.quota}
                </span>
                <span className="text-xs text-muted-foreground">
                  {msg("settings.admin.quotas.current")}:{" "}
                  <span className="font-mono tabular-nums" dir="ltr">
                    {item.job_count}
                  </span>
                </span>
                <span className="min-w-0 truncate text-xs text-muted-foreground" dir="ltr">
                  {item.updated_by || msg("settings.admin.quotas.default")}
                </span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => void handleDelete(item.username)}
                      disabled={saving}
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={msg("settings.admin.quotas.delete")}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{msg("settings.admin.quotas.delete")}</TooltipContent>
                </Tooltip>
              </div>
            ))}
          </div>
        )}
      </div>

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
  "admin",
  "account",
  "about",
] as const;
type SettingsTab = (typeof SETTINGS_TAB_ORDER)[number];

const SETTINGS_TAB_TRIGGER_CLASS =
  "relative z-10 w-full min-w-0 whitespace-nowrap text-center text-[clamp(0.75rem,2.2vw,0.875rem)] rounded-md px-1.5 py-2 font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5 leading-tight";

export function SettingsModal() {
  const { open, setOpen } = useSettingsModal();
  const { data: session } = useSession();
  const isAdmin = session?.user?.role === "admin";
  const [activeTab, setActiveTab] = React.useState<SettingsTab>("wizard");
  const tabs = React.useMemo(
    () => SETTINGS_TAB_ORDER.filter((tab) => isAdmin || tab !== "admin"),
    [isAdmin],
  );
  React.useEffect(() => {
    if (!tabs.includes(activeTab)) setActiveTab("wizard");
  }, [activeTab, tabs]);
  const tabIndex = tabs.indexOf(activeTab);
  const tabCount = tabs.length;
  const indicatorOffset =
    tabIndex <= 0
      ? "4px"
      : `calc(${((tabIndex * 100) / tabCount).toFixed(3)}% + ${(4 - (tabIndex * 4) / tabCount).toFixed(3)}px)`;

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
          <TabsList
            className="relative grid w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto items-stretch"
            style={{ gridTemplateColumns: `repeat(${tabCount}, minmax(0, 1fr))` }}
          >
            <div
              className="absolute top-1 bottom-1 rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
              style={{
                width: `calc(${(100 / tabCount).toFixed(3)}% - 5px)`,
                insetInlineStart: indicatorOffset,
              }}
            />
            <TabsTrigger value="wizard" className={SETTINGS_TAB_TRIGGER_CLASS}>
              {msg("settings.tab.wizard")}
            </TabsTrigger>
            <TabsTrigger value="agent" className={SETTINGS_TAB_TRIGGER_CLASS}>
              {msg("settings.tab.agent")}
            </TabsTrigger>
            {isAdmin && (
              <TabsTrigger value="admin" className={SETTINGS_TAB_TRIGGER_CLASS}>
                {msg("settings.tab.admin")}
              </TabsTrigger>
            )}
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
            {isAdmin && (
              <TabsContent value="admin">
                <AdminTab />
              </TabsContent>
            )}
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
