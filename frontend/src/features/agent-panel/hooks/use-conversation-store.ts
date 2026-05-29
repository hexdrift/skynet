"use client";

// Conversation-store hook backing the agent panel's history drawer.
//
// Owns the *index* of conversations (summaries shown in the drawer) plus the
// currently-active conversation id. Loading the full message history is left
// to the panel: when a row is opened, the panel calls ``getConversation``
// directly and seeds its useGeneralistAgent messages from the result.
//
// Mutations (rename / pin / delete) refresh the active list optimistically and
// reconcile against the server response. A failed mutation reverts the
// optimistic edit and surfaces no error toast — the drawer just shows the
// original row again on the next list refetch.
//
// Unread tracking: a localStorage-backed map of conversation_id → last-seen
// ISO timestamp. A row is "unread" when its server ``updated_at`` is newer
// than the local last-seen value (or no last-seen exists). Caller marks a
// conversation seen on pick + on every conversation_meta for the active row.

import * as React from "react";

import {
  deleteConversation,
  listConversations,
  patchConversation,
  type ConversationPatch,
  type ConversationSummary,
  type ListConversationsParams,
} from "../lib/conversation-api";

const LAST_SEEN_STORAGE_KEY = "skynet.agent.conversations.lastSeen";

type LastSeenMap = Record<string, string>;

function readLastSeen(): LastSeenMap {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(LAST_SEEN_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const out: LastSeenMap = {};
      for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
        if (typeof v === "string") out[k] = v;
      }
      return out;
    }
  } catch {
    /* corrupted JSON — fall back to empty */
  }
  return {};
}

function writeLastSeen(map: LastSeenMap): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LAST_SEEN_STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* storage quota / disabled — silent no-op */
  }
}

export interface ConversationStoreState {
  conversations: ConversationSummary[];
  loading: boolean;
  activeId: string | null;
  unreadIds: ReadonlySet<string>;
  setActiveId: (id: string | null) => void;
  refresh: (params?: ListConversationsParams) => Promise<void>;
  rename: (id: string, title: string) => Promise<void>;
  togglePin: (id: string, pinned: boolean) => Promise<void>;
  remove: (id: string) => Promise<void>;
  upsertFromMeta: (id: string, title: string) => void;
  markSeen: (id: string) => void;
}

export interface UseConversationStoreArgs {
  enabled: boolean;
}

export function useConversationStore(args: UseConversationStoreArgs): ConversationStoreState {
  const { enabled } = args;
  const [conversations, setConversations] = React.useState<ConversationSummary[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [lastSeen, setLastSeen] = React.useState<LastSeenMap>(() => readLastSeen());

  const refresh = React.useCallback(
    async (params?: ListConversationsParams) => {
      if (!enabled) return;
      setLoading(true);
      const rows = await listConversations(params);
      setLoading(false);
      if (rows !== null) setConversations(rows);
    },
    [enabled],
  );

  React.useEffect(() => {
    if (!enabled) return;
    void refresh();
  }, [enabled, refresh]);

  const applyPatch = React.useCallback((updated: ConversationSummary) => {
    setConversations((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
  }, []);

  const rename = React.useCallback(
    async (id: string, title: string) => {
      const trimmed = title.trim();
      if (!trimmed) return;
      const prevRows = conversations;
      setConversations((rows) =>
        rows.map((row) => (row.id === id ? { ...row, title: trimmed } : row)),
      );
      const patch: ConversationPatch = { title: trimmed };
      const updated = await patchConversation(id, patch);
      if (updated) {
        applyPatch(updated);
      } else {
        setConversations(prevRows);
      }
    },
    [conversations, applyPatch],
  );

  const togglePin = React.useCallback(
    async (id: string, pinned: boolean) => {
      const prevRows = conversations;
      setConversations((rows) =>
        rows.map((row) => (row.id === id ? { ...row, pinned } : row)),
      );
      const updated = await patchConversation(id, { pinned });
      if (updated) {
        applyPatch(updated);
      } else {
        setConversations(prevRows);
      }
    },
    [conversations, applyPatch],
  );

  const remove = React.useCallback(
    async (id: string) => {
      const prevRows = conversations;
      setConversations((rows) => rows.filter((row) => row.id !== id));
      const ok = await deleteConversation(id);
      if (!ok) setConversations(prevRows);
    },
    [conversations],
  );

  const upsertFromMeta = React.useCallback((id: string, title: string) => {
    setConversations((prev) => {
      const existing = prev.find((row) => row.id === id);
      const now = new Date().toISOString();
      if (existing) {
        // Conversation already in the index — just bump updated_at so it
        // floats to the top after the next sort.
        return prev.map((row) => (row.id === id ? { ...row, updatedAt: now, title } : row));
      }
      const stub: ConversationSummary = {
        id,
        title,
        pinned: false,
        archivedAt: null,
        createdAt: now,
        updatedAt: now,
        preview: null,
      };
      return [stub, ...prev];
    });
  }, []);

  const markSeen = React.useCallback((id: string) => {
    setLastSeen((prev) => {
      const next = { ...prev, [id]: new Date().toISOString() };
      writeLastSeen(next);
      return next;
    });
  }, []);

  const unreadIds = React.useMemo(() => {
    const out = new Set<string>();
    for (const row of conversations) {
      const seen = lastSeen[row.id];
      if (!seen || new Date(row.updatedAt).getTime() > new Date(seen).getTime()) {
        out.add(row.id);
      }
    }
    return out;
  }, [conversations, lastSeen]);

  return {
    conversations,
    loading,
    activeId,
    unreadIds,
    setActiveId,
    refresh,
    rename,
    togglePin,
    remove,
    upsertFromMeta,
    markSeen,
  };
}
