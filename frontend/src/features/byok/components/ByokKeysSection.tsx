"use client";

import * as React from "react";
import {
  Check,
  CircleNotch,
  FloppyDisk,
  Key,
  PencilSimple,
  Plus,
  Trash,
  X,
} from "@/shared/ui/icons";
import { toast } from "react-toastify";
import { msg, formatMsg } from "@/shared/lib/messages";
import { cn } from "@/shared/lib/utils";
import { useLocale } from "@/shared/providers";
import { Button } from "@/shared/ui/primitives/button";
import { Input } from "@/shared/ui/primitives/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";
import { KeyFormActions } from "@/shared/ui/key-form-actions";
import { LoadingState } from "@/shared/ui/loading-state";
import { StatusPill, type StatusTone } from "@/shared/ui/status-badge";
import { TOUCH_FIELD, TOUCH_FIELD_SM } from "@/shared/ui/touch";
import { useByokKeys } from "../providers/byok-provider";
import { type KeyStatus, type ProviderKey } from "../lib/byok";
import { ByokJsonImport } from "./ByokJsonImport";

/** The status pill next to a saved key. */
function KeyStatusPill({ status }: { status: KeyStatus }) {
  const map: Record<KeyStatus, { label: string; tone: StatusTone }> = {
    verified: { label: msg("settings.keys.verified"), tone: "success" },
    unverified: { label: msg("settings.keys.unverified"), tone: "pending" },
    invalid: { label: msg("settings.keys.invalid"), tone: "failed" },
  };
  const { label, tone } = map[status];
  return <StatusPill tone={tone}>{label}</StatusPill>;
}

function ConnectionRow({ connection }: { connection: ProviderKey }) {
  const { saveKey, verifyKey, removeKey } = useByokKeys();
  const { locale } = useLocale();
  const addedAt = new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(
    new Date(connection.addedAt),
  );

  const [editing, setEditing] = React.useState(false);
  const [secret, setSecret] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [verifying, setVerifying] = React.useState(false);

  const startEditing = () => {
    setSecret("");
    setBaseUrl(connection.apiBase ?? "");
    setEditing(true);
  };

  const handleSave = async () => {
    const trimmed = secret.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      const status = await saveKey(connection.provider, trimmed, {
        apiBase: baseUrl.trim() || null,
        label: connection.label ?? null,
        params: connection.params,
      });
      setSecret("");
      setBaseUrl("");
      setEditing(false);
      // The vault verifies on entry, so a saved key can already come back
      // rejected; surface that honestly rather than a blanket "saved".
      if (status === "invalid") {
        toast.error(msg("settings.keys.invalid_toast"));
      } else {
        toast.success(msg("settings.keys.saved_toast"));
      }
    } catch {
      toast.error(msg("settings.keys.save_failed_toast"));
    } finally {
      setSaving(false);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    try {
      const status = await verifyKey(connection.provider);
      if (status === "verified") {
        toast.success(msg("settings.keys.verified_toast"));
      } else if (status === "invalid") {
        toast.error(msg("settings.keys.invalid_toast"));
      } else {
        toast.info(msg("settings.keys.unverified_toast"));
      }
    } catch {
      toast.error(msg("settings.keys.verify_failed_toast"));
    } finally {
      setVerifying(false);
    }
  };

  const handleRemove = async () => {
    try {
      await removeKey(connection.provider);
      toast.success(msg("settings.keys.removed_toast"));
    } catch {
      toast.error(msg("settings.keys.remove_failed_toast"));
    }
  };

  return (
    <div className="rounded-lg border border-border/50 px-3 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted/50 text-muted-foreground">
            <Key className="size-4" aria-hidden="true" />
          </span>
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="text-sm font-medium text-foreground">
              {connection.label?.trim() || connection.provider}
            </span>
            <span className="flex flex-wrap items-center gap-2">
              <code dir="ltr" className="font-mono text-xs text-muted-foreground">
                {formatMsg("settings.keys.connection_mask", {
                  provider: connection.provider,
                  last4: connection.last4,
                })}
              </code>
              <KeyStatusPill status={connection.status} />
            </span>
            {connection.apiBase && (
              <code
                dir="ltr"
                className="truncate font-mono text-[0.6875rem] text-muted-foreground/70"
              >
                {connection.apiBase}
              </code>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          {connection.status !== "verified" && !editing && (
            <Button variant="outline" size="sm" disabled={verifying} onClick={handleVerify}>
              {verifying ? (
                <CircleNotch
                  className="animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : (
                <Check className="size-3.5" />
              )}
              {verifying ? msg("settings.keys.verifying") : msg("settings.keys.verify")}
            </Button>
          )}
          {!editing && (
            <>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={startEditing}
                    className="text-muted-foreground hover:text-foreground"
                    aria-label={msg("settings.keys.replace")}
                  >
                    <PencilSimple className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{msg("settings.keys.replace")}</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={handleRemove}
                    className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    aria-label={msg("settings.keys.remove")}
                  >
                    <Trash className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{msg("settings.keys.remove")}</TooltipContent>
              </Tooltip>
            </>
          )}
        </div>
      </div>

      {!editing && (
        <p className="mt-1.5 text-[0.6875rem] text-muted-foreground/70">
          {formatMsg("settings.keys.added", { date: addedAt })}
        </p>
      )}

      {editing && (
        <div className="mt-2.5 flex flex-col gap-2 animate-in fade-in-0 slide-in-from-top-1">
          <Input
            dir="ltr"
            type="password"
            autoFocus
            autoComplete="new-password"
            placeholder={msg("settings.keys.secret_placeholder")}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSave();
              if (e.key === "Escape") setEditing(false);
            }}
            className={TOUCH_FIELD_SM}
          />
          <Input
            dir="ltr"
            type="url"
            autoComplete="off"
            placeholder={msg("settings.keys.base_url_placeholder")}
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSave();
              if (e.key === "Escape") setEditing(false);
            }}
            className={cn(TOUCH_FIELD_SM, "text-xs")}
          />
          <p className="text-[0.6875rem] text-muted-foreground/70">
            {msg("settings.keys.base_url_hint")}
          </p>
          <KeyFormActions
            submitLabel={msg("settings.keys.save")}
            submitIcon={<FloppyDisk className="size-4" aria-hidden="true" />}
            busy={saving}
            disabled={!secret.trim() || saving}
            onSubmit={() => void handleSave()}
            onCancel={() => setEditing(false)}
          />
        </div>
      )}
    </div>
  );
}

function NewConnectionForm({ existingProviders }: { existingProviders: Set<string> }) {
  const { saveKey } = useByokKeys();
  const providerId = React.useId();
  const labelId = React.useId();
  const secretId = React.useId();
  const baseUrlId = React.useId();
  const [open, setOpen] = React.useState(false);
  const [provider, setProvider] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [secret, setSecret] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const normalizedProvider = provider.trim().toLocaleLowerCase();
  const duplicate = existingProviders.has(normalizedProvider);

  const close = () => {
    setOpen(false);
    setProvider("");
    setLabel("");
    setSecret("");
    setBaseUrl("");
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!normalizedProvider || !secret.trim() || duplicate) return;
    setSaving(true);
    try {
      const status = await saveKey(normalizedProvider, secret.trim(), {
        label: label.trim() || null,
        apiBase: baseUrl.trim() || null,
      });
      close();
      if (status === "invalid") {
        toast.error(msg("settings.keys.invalid_toast"));
      } else {
        toast.success(msg("settings.keys.saved_toast"));
      }
    } catch {
      toast.error(msg("settings.keys.save_failed_toast"));
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <Button type="button" variant="outline" className="w-full" onClick={() => setOpen(true)}>
        <Plus className="size-4" />
        {msg("settings.keys.add_provider")}
      </Button>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border/60 bg-muted/15 p-3.5 animate-in fade-in-0 slide-in-from-top-1"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-foreground">
            {msg("settings.keys.new_connection")}
          </h4>
          <p className="mt-0.5 text-[0.6875rem] text-muted-foreground">
            {msg("settings.keys.new_connection_hint")}
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={close}
          className="text-muted-foreground hover:text-foreground"
          aria-label={msg("settings.keys.cancel")}
        >
          <X className="size-4" />
        </Button>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="flex min-w-0 flex-col gap-1.5 text-xs font-medium" htmlFor={providerId}>
          {msg("settings.keys.connection_id_label")}
          <Input
            id={providerId}
            dir="ltr"
            autoFocus
            required
            maxLength={32}
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
            placeholder={msg("settings.keys.provider_placeholder")}
            aria-invalid={duplicate}
            className={TOUCH_FIELD}
          />
          {duplicate && (
            <span className="text-[0.6875rem] font-normal text-destructive">
              {msg("settings.keys.duplicate")}
            </span>
          )}
        </label>
        <label className="flex min-w-0 flex-col gap-1.5 text-xs font-medium" htmlFor={labelId}>
          {msg("settings.keys.connection_label_label")}
          <Input
            id={labelId}
            maxLength={120}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder={msg("settings.keys.connection_label_placeholder")}
            className={TOUCH_FIELD}
          />
        </label>
        <label
          className="flex min-w-0 flex-col gap-1.5 text-xs font-medium sm:col-span-2"
          htmlFor={secretId}
        >
          {msg("settings.keys.secret_label")}
          <Input
            id={secretId}
            dir="ltr"
            type="password"
            required
            autoComplete="new-password"
            value={secret}
            onChange={(event) => setSecret(event.target.value)}
            placeholder={msg("settings.keys.secret_placeholder")}
            className={TOUCH_FIELD}
          />
        </label>
        <label
          className="flex min-w-0 flex-col gap-1.5 text-xs font-medium sm:col-span-2"
          htmlFor={baseUrlId}
        >
          {msg("settings.keys.base_url_label")}
          <Input
            id={baseUrlId}
            dir="ltr"
            type="url"
            maxLength={255}
            autoComplete="off"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder={msg("settings.keys.base_url_placeholder")}
            className={TOUCH_FIELD}
          />
        </label>
      </div>

      <p className="mt-2 text-[0.6875rem] text-muted-foreground/75">
        {msg("settings.keys.base_url_hint")}
      </p>
      <div className="mt-3 flex items-center justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={close}>
          {msg("settings.keys.cancel")}
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={!normalizedProvider || !secret.trim() || duplicate || saving}
        >
          {saving ? (
            <CircleNotch className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
          ) : (
            msg("settings.keys.save")
          )}
        </Button>
      </div>
    </form>
  );
}

/** Render provider-agnostic BYOK connection management. */
export function ByokKeysSection() {
  const { keys, loading } = useByokKeys();
  const existingProviders = React.useMemo(() => new Set(keys.map((key) => key.provider)), [keys]);

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Key className="size-4 text-muted-foreground" aria-hidden="true" />
          <span className="text-sm font-semibold text-foreground">
            {msg("settings.keys.title")}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">{msg("settings.keys.description")}</p>
      </div>

      {loading ? (
        <LoadingState className="py-8" />
      ) : keys.length > 0 ? (
        <div className="flex flex-col gap-2">
          {keys.map((connection) => (
            <ConnectionRow key={connection.provider} connection={connection} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border/60 px-4 py-6 text-center">
          <p className="text-sm font-medium text-foreground">{msg("settings.keys.empty_title")}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {msg("settings.keys.empty_description")}
          </p>
        </div>
      )}

      <NewConnectionForm existingProviders={existingProviders} />
      <ByokJsonImport />
    </div>
  );
}
