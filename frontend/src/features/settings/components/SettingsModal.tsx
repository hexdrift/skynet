"use client";

import * as React from "react";
import { signOut, useSession } from "next-auth/react";
import { toast } from "react-toastify";
import {
  Columns2,
  ExternalLink,
  Keyboard,
  LogOut,
  Pencil,
  Plus,
  RotateCcw,
  Server,
  Shield,
  ShieldCheck,
  Sparkles,
  Table as TableIcon,
  User,
  Info,
  X,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/ui/primitives/table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/shared/ui/primitives/sheet";
import {
  ColumnHeader,
  ResetColumnsButton,
  type SortDir,
  useColumnFilters,
  useColumnResize,
} from "@/shared/ui/excel-filter";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import {
  deleteUserQuotaOverride,
  getUserQuotaOverrides,
  searchAdminUsers,
  setUserQuotaOverride,
  type DirectoryUserMatch,
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

function UsernameCombobox({
  value,
  onChange,
  onSelect,
  disabled,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  onSelect: (entry: DirectoryUserMatch) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [results, setResults] = React.useState<DirectoryUserMatch[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [open, setOpen] = React.useState(false);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    const trimmed = value.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setLoading(true);
    debounceRef.current = setTimeout(() => {
      searchAdminUsers(trimmed, 10)
        .then((data) => setResults(data.matches))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value]);

  return (
    <div className="relative">
      <Input
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // Defer so click on a suggestion can register before the popup unmounts.
          window.setTimeout(() => setOpen(false), 150);
        }}
        placeholder={placeholder}
        disabled={disabled}
        dir="ltr"
        className="h-8 text-xs"
      />
      {open && value.trim().length > 0 && (
        <div className="absolute inset-x-0 top-full z-30 mt-1 max-h-48 overflow-auto rounded-md border border-border/60 bg-background shadow-md">
          {loading && results.length === 0 ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              {msg("settings.admin.quotas.searching")}
            </div>
          ) : results.length === 0 ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              {msg("settings.admin.quotas.no_suggestions")}
            </div>
          ) : (
            <ul role="listbox">
              {results.map((entry) => (
                <li key={`${entry.source}:${entry.username}`}>
                  <button
                    type="button"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      onSelect(entry);
                      setOpen(false);
                    }}
                    className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-start text-xs hover:bg-accent/50"
                    dir="ltr"
                  >
                    <span className="font-mono">{entry.username}</span>
                    {entry.source === "directory" && (
                      <span className="text-[0.6875rem] text-muted-foreground">
                        {msg("settings.admin.quotas.source_directory")}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function EditableQuotaCell({
  value,
  onSave,
  disabled,
}: {
  value: number | null;
  onSave: (next: number) => Promise<void>;
  disabled?: boolean;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState<string>(value == null ? "" : String(value));
  const [saving, setSaving] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    if (!editing) setDraft(value == null ? "" : String(value));
  }, [value, editing]);

  React.useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const cancel = React.useCallback(() => {
    setDraft(value == null ? "" : String(value));
    setEditing(false);
  }, [value]);

  const commit = React.useCallback(async () => {
    const parsed = Number.parseInt(draft, 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
      toast.error(msg("settings.admin.quotas.quota_invalid"));
      return;
    }
    if (parsed === value) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(parsed);
      setEditing(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("settings.admin.quotas.save_failed"));
      cancel();
    } finally {
      setSaving(false);
    }
  }, [cancel, draft, onSave, value]);

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="number"
        min={1}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void commit();
          } else if (event.key === "Escape") {
            event.preventDefault();
            cancel();
          }
        }}
        onBlur={cancel}
        disabled={saving}
        dir="ltr"
        className="mx-auto h-7 w-20 rounded-md border border-border/60 bg-background px-2 text-center text-xs tabular-nums outline-none focus:border-primary"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => !disabled && setEditing(true)}
      disabled={disabled}
      title={msg("settings.admin.quotas.edit_quota_hint")}
      className="group inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs tabular-nums text-muted-foreground hover:bg-accent/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span>{value == null ? msg("settings.admin.quotas.unlimited_label") : value}</span>
      <Pencil className="size-3 opacity-0 transition group-hover:opacity-50" aria-hidden="true" />
    </button>
  );
}

function AdminTab() {
  const { data: session } = useSession();
  const [overrides, setOverrides] = React.useState<UserQuotaOverride[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [tableOpen, setTableOpen] = React.useState(false);
  const [pendingUsername, setPendingUsername] = React.useState("");
  const [pendingQuota, setPendingQuota] = React.useState<number | "">("");
  const colFilters = useColumnFilters();
  const colResize = useColumnResize();
  const [sortKey, setSortKey] = React.useState<string>("username");
  const [sortDir, setSortDir] = React.useState<SortDir>("asc");

  const toggleSort = React.useCallback((key: string) => {
    setSortKey((prevKey) => {
      setSortDir((prevDir) => (prevKey === key ? (prevDir === "asc" ? "desc" : "asc") : "asc"));
      return key;
    });
  }, []);

  const filterOptions = React.useMemo(() => {
    const unique = (key: keyof UserQuotaOverride) => {
      const vals = [
        ...new Set(overrides.map((o) => String(o[key] ?? "")).filter(Boolean)),
      ].sort();
      return vals.map((v) => ({ value: v, label: v }));
    };
    return {
      username: unique("username"),
      updated_by: unique("updated_by"),
    };
  }, [overrides]);

  const filteredOverrides = React.useMemo(() => {
    const items = overrides.filter((o) => {
      for (const [col, allowed] of Object.entries(colFilters.filters)) {
        const val = String((o as unknown as Record<string, unknown>)[col] ?? "");
        if (!allowed.has(val)) return false;
      }
      return true;
    });
    items.sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey];
      const bv = (b as unknown as Record<string, unknown>)[sortKey];
      const aMissing = av == null || av === "";
      const bMissing = bv == null || bv === "";
      let cmp = 0;
      if (aMissing && bMissing) cmp = 0;
      else if (aMissing) cmp = -1;
      else if (bMissing) cmp = 1;
      else if (typeof av === "number" && typeof bv === "number") cmp = av - bv;
      else cmp = String(av).localeCompare(String(bv), "he", { numeric: true });
      return sortDir === "asc" ? cmp : -cmp;
    });
    return items;
  }, [overrides, colFilters.filters, sortKey, sortDir]);

  const loadQuotas = React.useCallback(async () => {
    if (!session?.backendAccessToken) return;
    setLoading(true);
    try {
      const data = await getUserQuotaOverrides();
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

  React.useEffect(() => {
    if (!tableOpen) return;
    const id = setInterval(() => {
      void loadQuotas();
    }, 5000);
    return () => clearInterval(id);
  }, [tableOpen, loadQuotas]);

  const addPendingUser = React.useCallback(async () => {
    const normalizedUsername = pendingUsername.trim().toLowerCase();
    if (!normalizedUsername) {
      toast.error(msg("settings.admin.quotas.username_required"));
      return;
    }
    if (pendingQuota === "" || !Number.isFinite(pendingQuota) || pendingQuota < 1) {
      toast.error(msg("settings.admin.quotas.quota_invalid"));
      return;
    }
    setBusy(true);
    try {
      const saved = await setUserQuotaOverride(normalizedUsername, pendingQuota);
      setOverrides((prev) => {
        const without = prev.filter((row) => row.username !== saved.username);
        return [saved, ...without];
      });
      setPendingUsername("");
      setPendingQuota("");
      toast.success(msg("settings.admin.quotas.saved"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("settings.admin.quotas.save_failed"));
    } finally {
      setBusy(false);
    }
  }, [pendingQuota, pendingUsername]);

  const updateRowQuota = React.useCallback(
    async (targetUsername: string, nextQuota: number) => {
      const before = overrides;
      setOverrides((prev) =>
        prev.map((row) => (row.username === targetUsername ? { ...row, quota: nextQuota } : row)),
      );
      try {
        const saved = await setUserQuotaOverride(targetUsername, nextQuota);
        setOverrides((prev) => prev.map((row) => (row.username === targetUsername ? saved : row)));
        toast.success(msg("settings.admin.quotas.saved"));
      } catch (err) {
        setOverrides(before);
        throw err;
      }
    },
    [overrides],
  );

  const handleDelete = React.useCallback(
    async (targetUsername: string) => {
      const before = overrides;
      setOverrides((prev) => prev.filter((row) => row.username !== targetUsername));
      setBusy(true);
      try {
        await deleteUserQuotaOverride(targetUsername);
        toast.success(msg("settings.admin.quotas.deleted"));
      } catch (err) {
        setOverrides(before);
        toast.error(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [overrides],
  );

  const triggerLabel =
    overrides.length === 0
      ? msg("settings.admin.quotas.view_list")
      : `${msg("settings.admin.quotas.view_list")} (${overrides.length})`;

  return (
    <div className="space-y-4">
      {!session?.backendAccessToken && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {msg("settings.admin.quotas.auth_missing")}
        </div>
      )}

      <SettingsRow icon={Users} label={msg("settings.admin.quotas.title")}>
        <span />
      </SettingsRow>

      <Sheet open={tableOpen} onOpenChange={setTableOpen}>
        <SheetTrigger asChild>
          <Button
            variant="outline"
            disabled={loading || !session?.backendAccessToken}
            className="w-full justify-center gap-2"
          >
            <TableIcon className="size-3.5" />
            <span>{triggerLabel}</span>
          </Button>
        </SheetTrigger>
        <SheetContent
          side="left"
          aria-describedby={undefined}
          className="w-full gap-0 p-0 sm:max-w-2xl"
        >
          <SheetHeader className="border-b border-border/40 px-6 py-4">
            <div className="flex items-center gap-2">
              <TableIcon className="size-4 text-muted-foreground" aria-hidden="true" />
              <SheetTitle>{msg("settings.admin.quotas.title")}</SheetTitle>
            </div>
          </SheetHeader>

          <div className="flex items-center gap-3 border-b border-border/40 bg-muted/20 px-6 py-2">
            <span className="text-[0.6875rem] tabular-nums text-muted-foreground">
              {filteredOverrides.length === overrides.length
                ? overrides.length
                : `${filteredOverrides.length} / ${overrides.length}`}
            </span>
            <ResetColumnsButton resize={colResize} />
            {colFilters.activeCount > 0 && (
              <button
                type="button"
                onClick={colFilters.clearAll}
                className="text-[0.6875rem] text-muted-foreground hover:text-foreground cursor-pointer"
              >
                {msg("settings.admin.quotas.clear_filters")}
              </button>
            )}
          </div>

          <div className="flex-1 overflow-auto">
            <Table style={{ minWidth: "560px" }}>
              <TableHeader className="sticky top-0 z-10 bg-muted/40 backdrop-blur-sm">
                <TableRow>
                  <ColumnHeader
                    label={msg("settings.admin.quotas.username")}
                    sortKey="username"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    filterCol="username"
                    filterOptions={filterOptions.username}
                    filters={colFilters.filters}
                    onFilter={colFilters.setColumnFilter}
                    openFilter={colFilters.openFilter}
                    setOpenFilter={colFilters.setOpenFilter}
                    width={colResize.widths["username"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label={msg("settings.admin.quotas.quota")}
                    sortKey="quota"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    width={colResize.widths["quota"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label={msg("settings.admin.quotas.current")}
                    sortKey="job_count"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    width={colResize.widths["job_count"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label={msg("settings.admin.quotas.updated_by")}
                    sortKey="updated_by"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    filterCol="updated_by"
                    filterOptions={filterOptions.updated_by}
                    filters={colFilters.filters}
                    onFilter={colFilters.setColumnFilter}
                    openFilter={colFilters.openFilter}
                    setOpenFilter={colFilters.setOpenFilter}
                    width={colResize.widths["updated_by"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow className="border-border/40 bg-muted/10">
                  <TableCell className="text-center" dir="ltr">
                    <UsernameCombobox
                      value={pendingUsername}
                      onChange={setPendingUsername}
                      onSelect={(entry) => setPendingUsername(entry.username)}
                      disabled={busy}
                      placeholder={msg("settings.admin.quotas.username_placeholder")}
                    />
                  </TableCell>
                  <TableCell className="text-center">
                    <NumberInput
                      value={pendingQuota}
                      onChange={setPendingQuota}
                      min={1}
                      disabled={busy}
                      className="mx-auto h-8 w-28"
                    />
                  </TableCell>
                  <TableCell className="text-center text-xs text-muted-foreground/70">—</TableCell>
                  <TableCell className="text-center text-xs text-muted-foreground/70">—</TableCell>
                  <TableCell className="w-12 text-center">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => void addPendingUser()}
                          disabled={busy || !pendingUsername.trim() || pendingQuota === ""}
                          aria-label={msg("settings.admin.quotas.add_row")}
                        >
                          <Plus className="size-3.5 text-primary" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>{msg("settings.admin.quotas.add_row")}</TooltipContent>
                    </Tooltip>
                  </TableCell>
                </TableRow>

                {filteredOverrides.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="px-6 py-10 text-center text-sm text-muted-foreground"
                    >
                      {overrides.length === 0
                        ? msg("settings.admin.quotas.empty")
                        : msg("settings.admin.quotas.no_results")}
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredOverrides.map((item) => (
                    <TableRow
                      key={item.username}
                      className="border-border/40 hover:bg-accent/30"
                    >
                      <TableCell
                        className="max-w-[200px] truncate text-center font-mono text-xs text-foreground"
                        dir="ltr"
                        title={item.username}
                      >
                        {item.username}
                      </TableCell>
                      <TableCell className="text-center">
                        <EditableQuotaCell
                          value={item.quota ?? null}
                          onSave={(next) => updateRowQuota(item.username, next)}
                          disabled={busy}
                        />
                      </TableCell>
                      <TableCell
                        className="text-center font-mono text-xs tabular-nums text-muted-foreground"
                        dir="ltr"
                      >
                        {item.job_count}
                      </TableCell>
                      <TableCell
                        className="max-w-[180px] truncate text-center text-xs text-muted-foreground"
                        dir="ltr"
                        title={item.updated_by || msg("settings.admin.quotas.default")}
                      >
                        {item.updated_by || msg("settings.admin.quotas.default")}
                      </TableCell>
                      <TableCell className="w-12 text-center">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              onClick={() => void handleDelete(item.username)}
                              disabled={busy}
                              className="close-button mx-auto disabled:opacity-50 disabled:cursor-not-allowed"
                              aria-label={msg("settings.admin.quotas.delete")}
                            >
                              <X aria-hidden="true" />
                              <span className="sr-only">
                                {msg("settings.admin.quotas.delete")}
                              </span>
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>
                            {msg("settings.admin.quotas.delete")}
                          </TooltipContent>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </SheetContent>
      </Sheet>
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
