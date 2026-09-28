"use client";

import { EmptyState } from "@/shared/ui/empty-state";
import { cn } from "@/shared/lib/utils";
import { TOUCH_FIELD_SM } from "@/shared/ui/touch";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { CircleNotch, User, UserPlus, Users, X } from "@/shared/ui/icons";
import { toast } from "react-toastify";
import { Button } from "@/shared/ui/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/primitives/dialog";
import { DialogTitleRow } from "@/shared/ui/dialog-title-row";
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
  addDatasetShareMember,
  getDatasetSharing,
  removeDatasetShareMember,
  searchUsers,
  transferDatasetOwnership,
  updateDatasetShareMember,
  type DatasetSharingState,
  type MemberRole,
  type ShareRole,
} from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";
import { track, TelemetryEvent } from "@/shared/lib/telemetry";
import { sessionIdentity } from "@/shared/lib/session-identity";
import { Label } from "@/shared/ui/primitives/label";

const ROLE_OPTIONS: MemberRole[] = ["viewer", "editor"];

// Sentinel value for the per-member role dropdown's "transfer ownership" item
// (not a real role — selecting it opens the transfer confirmation instead).
const TRANSFER_VALUE = "__transfer__";

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
  return "";
}

/**
 * Drive-style sharing modal for a library dataset. Mirrors the optimization
 * :func:`ShareDialog` — a People section (invite by username + per-member role)
 * over a General-access section (Restricted vs Anyone-with-link) plus a copy-link
 * row — minus the optimization-only Explore visibility axis. The copy link points
 * at ``/datasets/share/{token}``, redeemed by :mod:`app/datasets/share/[token]`.
 */
export function DatasetShareDialog({
  datasetId,
  open: controlledOpen,
  onOpenChange,
  hideTrigger = false,
}: {
  datasetId: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
}) {
  const { data: session } = useSession();
  const me = sessionIdentity(session);
  // Uncontrolled by default (the built-in trigger drives it); the library's
  // selection bar drives it instead with ``hideTrigger``.
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;
  const setOpen = (next: boolean) => {
    if (!isControlled) setInternalOpen(next);
    onOpenChange?.(next);
  };
  const [state, setState] = useState<DatasetSharingState | null>(null);
  const [transferTarget, setTransferTarget] = useState<string | null>(null);
  const [transferring, setTransferring] = useState(false);
  // Split the confirm copy around the {name} token so the target username can
  // render emphasized below in an isolated <bdi>, matching the optimization dialog.
  // Resolved per-render (not at module scope) so it can't capture a raw key before
  // the message shim has loaded.
  const [transferBodyBefore, transferBodyAfter] = msg("share.transfer.confirm_body").split(
    "{name}",
  );

  const isOwner = !!state?.owner && state.owner.toLowerCase() === me;

  const accessCount = state ? (state.owner ? 1 : 0) + state.members.length : 0;

  // Fetch on open rather than in the trigger's handler so a parent-driven open
  // loads the sharing state too.
  useEffect(() => {
    if (!open || state !== null) return;
    getDatasetSharing(datasetId)
      .then(setState)
      .catch((err) => toast.error(err instanceof Error ? err.message : msg("share.error")));
  }, [open, state, datasetId]);

  const handleOpenChange = (next: boolean) => setOpen(next);

  const handleRoleChange = async (username: string, role: MemberRole) => {
    try {
      setState(await updateDatasetShareMember(datasetId, username, { role }));
      toast.success(msg("share.member_updated"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("share.save_failed"));
    }
  };

  // Transfer demotes the caller to editor server-side; once it lands they can no
  // longer manage — close the dialog and drop cached state so a re-open refetches.
  const handleTransfer = async () => {
    if (!transferTarget) return;
    setTransferring(true);
    try {
      // Invite-as-owner: when the target isn't a grantee yet (picked straight
      // from the invite row), add them first — the backend only hands ownership
      // to an existing member.
      const alreadyMember = state?.members.some(
        (m) => m.username.toLowerCase() === transferTarget.toLowerCase(),
      );
      if (!alreadyMember) {
        await addDatasetShareMember(datasetId, { username: transferTarget, role: "editor" });
      }
      await transferDatasetOwnership(datasetId, transferTarget);
      toast.success(msg("share.transfer.success", { name: transferTarget }));
      setTransferTarget(null);
      setOpen(false);
      setState(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("share.save_failed"));
    } finally {
      setTransferring(false);
    }
  };

  const handleRemove = async (username: string) => {
    try {
      setState(await removeDatasetShareMember(datasetId, username));
      toast.success(msg("share.member_removed"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("share.save_failed"));
    }
  };

  const handleInvite = async (username: string, role: MemberRole) => {
    setState(await addDatasetShareMember(datasetId, { username, role }));
    track(TelemetryEvent.ShareCreated, { kind: "dataset", mode: "member", role });
    toast.success(msg("share.member_added"));
  };

  return (
    <>
      {!hideTrigger && (
        <TooltipButton tooltip={msg("share.button")}>
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => handleOpenChange(true)}
            aria-label={msg("share.button")}
          >
            <Users className="size-4" />
          </Button>
        </TooltipButton>
      )}

      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className="w-[min(32rem,92vw)] max-w-[min(32rem,92vw)] overflow-hidden p-0 sm:max-w-lg"
          aria-describedby={undefined}
        >
          <div className="flex max-h-[85vh] flex-col">
            <DialogHeader className="shrink-0 border-b border-border/40 px-4 pb-4 pt-6 sm:px-6">
              <DialogTitle>{msg("share.dialog_title")}</DialogTitle>
            </DialogHeader>

            {state === null ? (
              <div className="flex items-center justify-center gap-2 px-6 py-10 text-sm text-muted-foreground">
                <CircleNotch className="size-4 animate-spin" />
                {msg("share.loading")}
              </div>
            ) : (
              <>
                <div className="shrink-0 border-b border-border/40 px-4 py-4 sm:px-6">
                  <InvitePeople
                    ownerName={state.owner}
                    onInvite={handleInvite}
                    canTransfer={isOwner}
                    onTransfer={setTransferTarget}
                  />
                </div>

                <div className="shrink-0 px-4 pb-1 pt-3 sm:px-6">
                  <p className="text-sm font-medium text-foreground">
                    {msg("share.people_with_access")}
                    <span className="ms-1.5 text-xs font-normal tabular-nums text-muted-foreground">
                      {accessCount}
                    </span>
                  </p>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-4 sm:px-6">
                  {state.owner && (
                    <SettingsRow
                      icon={User}
                      label={
                        <span
                          dir="ltr"
                          title={state.owner}
                          className="inline-block max-w-[200px] truncate align-bottom font-mono"
                        >
                          {state.owner}
                        </span>
                      }
                      description={state.owner.toLowerCase() === me ? msg("share.you") : undefined}
                    >
                      <span className="text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground">
                        {msg("share.owner_label")}
                      </span>
                    </SettingsRow>
                  )}

                  {state.members.map((member) =>
                    member.username === me ? (
                      <SettingsRow
                        key={member.username}
                        icon={User}
                        label={
                          <span
                            dir="ltr"
                            title={member.username}
                            className="inline-block max-w-[200px] truncate align-bottom font-semibold text-foreground"
                          >
                            {member.username}
                          </span>
                        }
                        description={msg("share.you")}
                      >
                        <span className="text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground">
                          {roleLabel(member.role)}
                        </span>
                      </SettingsRow>
                    ) : (
                      <SettingsRow
                        key={member.username}
                        icon={User}
                        label={
                          <span
                            dir="ltr"
                            title={member.username}
                            className="inline-block max-w-[200px] truncate align-bottom font-semibold text-foreground"
                          >
                            {member.username}
                          </span>
                        }
                      >
                        <Select
                          value={member.role}
                          onValueChange={(next) => {
                            if (next === TRANSFER_VALUE) {
                              setTransferTarget(member.username);
                            } else {
                              void handleRoleChange(member.username, next as MemberRole);
                            }
                          }}
                        >
                          <SelectTrigger
                            size="sm"
                            className={cn(TOUCH_FIELD_SM, "min-w-[120px]")}
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
                            {isOwner && (
                              <SelectItem value={TRANSFER_VALUE}>
                                {msg("share.transfer.action")}
                              </SelectItem>
                            )}
                          </SelectContent>
                        </Select>
                        <TooltipButton tooltip={msg("share.remove_member_aria")}>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                            onClick={() => handleRemove(member.username)}
                            aria-label={msg("share.remove_member_aria")}
                          >
                            <X className="size-3.5" />
                          </Button>
                        </TooltipButton>
                      </SettingsRow>
                    ),
                  )}
                </div>

              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={transferTarget !== null}
        onOpenChange={(next) => {
          if (!next) setTransferTarget(null);
        }}
      >
        <DialogContent className="w-[min(28rem,92vw)] max-w-[min(28rem,92vw)] sm:max-w-md">
          <DialogTitleRow
            title={msg("share.transfer.confirm_title")}
            description={
              <>
                {transferBodyBefore}
                <bdi className="font-mono font-medium text-foreground">{transferTarget}</bdi>
                {transferBodyAfter}
              </>
            }
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setTransferTarget(null)}
              disabled={transferring}
            >
              {msg("share.transfer.cancel")}
            </Button>
            <Button onClick={handleTransfer} disabled={transferring}>
              {transferring ? (
                <CircleNotch
                  className="animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : (
                msg("share.transfer.confirm_cta")
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Username autocomplete + role picker to add a new member grant. */
function InvitePeople({
  ownerName,
  onInvite,
  canTransfer,
  onTransfer,
}: {
  ownerName: string | null;
  onInvite: (username: string, role: MemberRole) => Promise<void>;
  canTransfer: boolean;
  onTransfer: (username: string) => void;
}) {
  const inviteId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [role, setRole] = useState<MemberRole | typeof TRANSFER_VALUE>("viewer");
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
    if (role === TRANSFER_VALUE) {
      // Hand ownership off straight from the invite row; the parent confirms,
      // then (if needed) adds the user before transferring.
      onTransfer(target);
      setQuery("");
      setResults([]);
      setOpen(false);
      setRole("viewer");
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
      <Label htmlFor={inviteId}>{msg("share.invite_label")}</Label>
      <div className="relative">
        <div className="flex items-center gap-1 rounded-xl border border-input/90 bg-background/75 ps-3 pe-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.72),0_12px_26px_-24px_rgba(15,23,42,0.45)] backdrop-blur-sm transition-[color,box-shadow,border-color] duration-120 ease-[cubic-bezier(0.2,0.8,0.2,1)] focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
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
            id={inviteId}
            aria-label={msg("share.invite_label")}
            disabled={inviting}
            dir="ltr"
            className={cn(
              TOUCH_FIELD_SM,
              "flex-1 rounded-none border-0 bg-transparent px-0 text-xs shadow-none backdrop-blur-none focus-visible:border-transparent focus-visible:ring-0",
            )}
          />
          <div aria-hidden className="h-5 w-px shrink-0 bg-border/70" />
          <Select
            value={role}
            onValueChange={(next) => setRole(next as MemberRole | typeof TRANSFER_VALUE)}
          >
            <SelectTrigger
              size="sm"
              className={cn(
                TOUCH_FIELD_SM,
                "gap-1 rounded-md border-0 bg-transparent px-2 text-xs shadow-none hover:border-transparent hover:bg-accent/55 hover:shadow-none focus-visible:border-transparent focus-visible:bg-accent/55 focus-visible:ring-0 data-[state=open]:border-transparent data-[state=open]:bg-accent/60 data-[state=open]:shadow-none",
              )}
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
              {canTransfer && (
                <SelectItem value={TRANSFER_VALUE}>{msg("share.transfer.action")}</SelectItem>
              )}
            </SelectContent>
          </Select>
          <TooltipButton tooltip={msg("share.invite")}>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={() => void submit(query)}
              disabled={inviting || query.trim().length === 0}
              aria-label={msg("share.invite")}
              className="shrink-0 text-muted-foreground hover:text-foreground focus-visible:bg-accent focus-visible:text-foreground focus-visible:ring-0"
            >
              {inviting ? (
                <CircleNotch
                  className="animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : (
                <UserPlus className="size-4" />
              )}
            </Button>
          </TooltipButton>
        </div>
        {open && query.trim().length > 0 && (
          <div className="absolute inset-x-0 top-full z-30 mt-2 max-h-48 overflow-y-auto rounded-md border border-border/70 bg-popover shadow-lg">
            {searching ? (
              <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
                <CircleNotch className="size-3.5 animate-spin" />
                {msg("share.searching")}
              </div>
            ) : results.length === 0 ? (
              <EmptyState
                variant="compact"
                title={msg("share.no_results")}
                className="gap-1 px-3 py-3"
              />
            ) : (
              <ul role="listbox" className="py-1">
                {results.map((name) => (
                  <li key={name}>
                    <button
                      type="button"
                      dir="ltr"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        void submit(name);
                      }}
                      className="flex w-full items-center px-3 py-1.5 text-start font-mono text-xs hover:bg-accent/60"
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
      {role !== TRANSFER_VALUE && roleDesc(role) ? (
        <p className="text-xs text-muted-foreground/80">{roleDesc(role)}</p>
      ) : null}
    </div>
  );
}
