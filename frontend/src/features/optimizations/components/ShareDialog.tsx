"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Copy, Globe, Loader2, Lock, Share2, User, UserPlus, X } from "lucide-react";
import { toast } from "react-toastify";
import { Button } from "@/shared/ui/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/primitives/dialog";
import { Input } from "@/shared/ui/primitives/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/primitives/select";
import { TooltipButton } from "@/shared/ui/tooltip-button";
import { SettingsRow } from "@/shared/ui/settings-row";
import {
  addShareMember,
  getSharing,
  putSharing,
  removeShareMember,
  searchUsers,
  updateShareMember,
  type GeneralAccess,
  type ShareRole,
  type SharingState,
} from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";

const ROLE_OPTIONS: ShareRole[] = ["viewer", "editor", "owner"];

/** Localised label for a member tier role. */
function roleLabel(role: ShareRole): string {
  if (role === "editor") return msg("share.role.editor");
  if (role === "owner") return msg("share.role.owner");
  return msg("share.role.viewer");
}

/** Localised one-line description of what a member tier role grants. */
function roleDesc(role: ShareRole): string {
  if (role === "editor") return msg("share.role.editor_desc");
  if (role === "owner") return msg("share.role.owner_desc");
  return msg("share.role.viewer_desc");
}

/**
 * Drive-style sharing modal for an optimization. Shares the Settings-modal
 * design language — a bordered ``DialogHeader`` over a padded, scrollable body
 * of :func:`SettingsRow` rows — with a People section (invite by username +
 * per-member role) and a General-access section (Restricted vs Anyone-with-link),
 * plus a copy-link row. Different purpose, same components.
 */
export function ShareDialog({ optimizationId }: { optimizationId: string }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<SharingState | null>(null);
  const [savingAccess, setSavingAccess] = useState(false);

  const shareUrl =
    state?.token && typeof window !== "undefined"
      ? `${window.location.origin}/share/${state.token}`
      : null;

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next && state === null) {
      getSharing(optimizationId)
        .then(setState)
        .catch((err) => toast.error(err instanceof Error ? err.message : msg("share.error")));
    }
  };

  const handleAccessChange = async (value: GeneralAccess) => {
    setSavingAccess(true);
    try {
      setState(await putSharing(optimizationId, { general_access: value }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("share.save_failed"));
    } finally {
      setSavingAccess(false);
    }
  };

  const handleRoleChange = async (username: string, role: ShareRole) => {
    try {
      setState(await updateShareMember(optimizationId, username, { role }));
      toast.success(msg("share.member_updated"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("share.save_failed"));
    }
  };

  const handleRemove = async (username: string) => {
    try {
      setState(await removeShareMember(optimizationId, username));
      toast.success(msg("share.member_removed"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("share.save_failed"));
    }
  };

  const handleInvite = async (username: string, role: ShareRole) => {
    setState(await addShareMember(optimizationId, { username, role }));
    toast.success(msg("share.member_added"));
  };

  const handleCopy = () => {
    if (!shareUrl) return;
    navigator.clipboard
      .writeText(shareUrl)
      .then(() => toast.success(msg("share.link_copied")))
      .catch(() => toast.error(msg("clipboard.copy_failed")));
  };

  return (
    <>
      <TooltipButton tooltip={msg("share.button")}>
        <Button
          variant="ghost"
          size="icon"
          className="size-8"
          onClick={() => handleOpenChange(true)}
          aria-label={msg("share.button")}
        >
          <Share2 className="size-4" />
        </Button>
      </TooltipButton>

      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className="max-w-lg sm:max-w-lg p-0 overflow-hidden"
          aria-describedby={undefined}
        >
          <DialogHeader className="px-6 pt-6 pb-4 border-b border-border/40">
            <DialogTitle>{msg("share.dialog_title")}</DialogTitle>
          </DialogHeader>

          {state === null ? (
            <div className="flex items-center justify-center gap-2 px-6 py-10 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              {msg("share.loading")}
            </div>
          ) : (
            <div className="px-6 pb-6 pt-2 space-y-4 max-h-[60vh] overflow-y-auto">
              <InvitePeople ownerName={state.owner} onInvite={handleInvite} />

              <div>
                <p className="mb-1 text-sm font-medium text-foreground">
                  {msg("share.people_with_access")}
                </p>
                {state.owner && (
                  <SettingsRow
                    icon={User}
                    label={
                      <span dir="ltr" className="font-mono">
                        {state.owner}
                      </span>
                    }
                    description={msg("share.you")}
                  >
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {msg("share.owner_label")}
                    </span>
                  </SettingsRow>
                )}

                {state.members.map((member) => (
                  <SettingsRow
                    key={member.username}
                    icon={User}
                    label={
                      <span dir="ltr" className="font-mono">
                        {member.username}
                      </span>
                    }
                  >
                    <Select
                      value={member.role}
                      onValueChange={(next) => handleRoleChange(member.username, next as ShareRole)}
                    >
                      <SelectTrigger
                        size="sm"
                        className="min-w-[120px]"
                        aria-label={msg("share.role.change_aria")}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ROLE_OPTIONS.map((option) => (
                          <SelectItem key={option} value={option}>
                            {roleLabel(option)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <TooltipButton tooltip={msg("share.remove_member_aria")}>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="text-muted-foreground hover:text-destructive"
                        onClick={() => handleRemove(member.username)}
                        aria-label={msg("share.remove_member_aria")}
                      >
                        <X className="size-3.5" />
                      </Button>
                    </TooltipButton>
                  </SettingsRow>
                ))}
              </div>

              <SettingsRow
                icon={state.general_access === "anyone" ? Globe : Lock}
                label={msg("share.general_access")}
                description={
                  state.general_access === "anyone"
                    ? msg("share.general_access.anyone_desc")
                    : msg("share.general_access.restricted_desc")
                }
              >
                <Select
                  value={state.general_access}
                  onValueChange={(next) => handleAccessChange(next as GeneralAccess)}
                  disabled={savingAccess}
                >
                  <SelectTrigger size="sm" className="min-w-[150px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="restricted">
                      {msg("share.general_access.restricted")}
                    </SelectItem>
                    <SelectItem value="anyone">{msg("share.general_access.anyone")}</SelectItem>
                  </SelectContent>
                </Select>
              </SettingsRow>

              {shareUrl && (
                <div
                  dir="ltr"
                  className="flex items-center justify-between gap-2 rounded-md border border-border/50 px-3 py-2"
                >
                  <code className="min-w-0 flex-1 truncate font-mono text-[0.6875rem] text-muted-foreground">
                    {shareUrl}
                  </code>
                  <TooltipButton tooltip={msg("share.copy_link")}>
                    <Button
                      variant="outline"
                      size="icon-sm"
                      className="shrink-0"
                      onClick={handleCopy}
                      aria-label={msg("share.copy_link")}
                    >
                      <Copy className="size-3.5" />
                    </Button>
                  </TooltipButton>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Username autocomplete + role picker to add a new member grant. */
function InvitePeople({
  ownerName,
  onInvite,
}: {
  ownerName: string | null;
  onInvite: (username: string, role: ShareRole) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [role, setRole] = useState<ShareRole>("viewer");
  const [inviting, setInviting] = useState(false);
  const [open, setOpen] = useState(false);
  const lastQuery = useRef("");

  const runSearch = useCallback((prefix: string) => {
    lastQuery.current = prefix;
    if (prefix.trim().length === 0) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    searchUsers(prefix)
      .then((res) => {
        if (lastQuery.current !== prefix) return;
        setResults(res.usernames);
      })
      .catch(() => {
        if (lastQuery.current === prefix) setResults([]);
      })
      .finally(() => {
        if (lastQuery.current === prefix) setSearching(false);
      });
  }, []);

  useEffect(() => {
    const id = setTimeout(() => runSearch(query), 200);
    return () => clearTimeout(id);
  }, [query, runSearch]);

  const submit = async (username: string) => {
    const target = username.trim();
    if (target.length === 0 || inviting) return;
    if (ownerName && target === ownerName) {
      toast.error(msg("share.cannot_grant_self"));
      return;
    }
    setInviting(true);
    try {
      await onInvite(target, role);
      setQuery("");
      setResults([]);
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("share.save_failed"));
    } finally {
      setInviting(false);
    }
  };

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-foreground">{msg("share.invite_label")}</p>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => window.setTimeout(() => setOpen(false), 150)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void submit(query);
              } else if (e.key === "Escape") {
                setOpen(false);
              }
            }}
            placeholder={msg("share.invite_placeholder")}
            aria-label={msg("share.invite_label")}
            disabled={inviting}
            dir="ltr"
            className="h-8 text-xs"
          />
          {open && query.trim().length > 0 && (
            <div className="absolute inset-x-0 top-full z-30 mt-1 max-h-48 overflow-y-auto rounded-md border border-border/60 bg-background shadow-md">
              {searching ? (
                <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  {msg("share.searching")}
                </div>
              ) : results.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted-foreground">
                  {msg("share.no_results")}
                </div>
              ) : (
                <ul role="listbox">
                  {results.map((name) => (
                    <li key={name}>
                      <button
                        type="button"
                        dir="ltr"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          void submit(name);
                        }}
                        className="flex w-full items-center px-3 py-1.5 text-start text-xs font-mono hover:bg-accent/50"
                      >
                        {name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
        <Select value={role} onValueChange={(next) => setRole(next as ShareRole)}>
          <SelectTrigger size="sm" className="min-w-[120px]" aria-label={msg("share.role.change_aria")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ROLE_OPTIONS.map((option) => (
              <SelectItem key={option} value={option}>
                {roleLabel(option)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <TooltipButton tooltip={msg("share.invite")}>
          <Button
            variant="outline"
            size="icon-sm"
            onClick={() => void submit(query)}
            disabled={inviting || query.trim().length === 0}
            aria-label={msg("share.invite")}
          >
            {inviting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <UserPlus className="size-4" />
            )}
          </Button>
        </TooltipButton>
      </div>
      <p className="text-xs text-muted-foreground/80">{roleDesc(role)}</p>
    </div>
  );
}
