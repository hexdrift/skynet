"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useSession } from "next-auth/react";
import { toast } from "react-toastify";

import { LOCALE_RELOAD_EVENT } from "@/shared/lib/locale";
import { formatMsg, msg, type MessageKey } from "@/shared/lib/messages";
import { sessionIdentity } from "@/shared/lib/session-identity";

import { DraftRestoreToast, type DraftRestoreState } from "../components/DraftRestoreToast";
import {
  DraftSaver,
  draftStage,
  hasMeaningfulDraft,
  type WizardDraftData,
  type WizardDraftRecord,
} from "../lib/draft-record";
import {
  indexedDbDraftStore,
  markResumeAfterReload,
  openDraftChannel,
  takeResumeAfterReload,
} from "../lib/draft-store";

/** What the wizard hook sees: publish snapshots, read one back, and mark it consumed. */
export interface WizardDraftsApi {
  /** A discovered draft awaits the user's choice; nothing is saved meanwhile. */
  offerPending: boolean;
  /** The snapshot to hydrate from, or null while an offer is pending or none exists. */
  takeSnapshot(): WizardDraftData | null;
  publish(data: WizardDraftData, meaningful: boolean): void;
  /** Write any pending change now — stage boundaries and unmounts. */
  flush(): void;
  /** The draft turned into a submission; delete it and stop saving. */
  consumed(): void;
}

const NOOP_API: WizardDraftsApi = {
  offerPending: false,
  takeSnapshot: () => null,
  publish: () => {},
  flush: () => {},
  consumed: () => {},
};

const WizardDraftsContext = createContext<WizardDraftsApi>(NOOP_API);

export function WizardDraftsProvider({
  api,
  children,
}: {
  api: WizardDraftsApi;
  children: ReactNode;
}) {
  return <WizardDraftsContext.Provider value={api}>{children}</WizardDraftsContext.Provider>;
}

/** The draft store the enclosing `/submit` entry provides; a no-op outside it. */
export function useWizardDrafts(): WizardDraftsApi {
  return useContext(WizardDraftsContext);
}

function offerToastId(draftId: string): string {
  return `draft-restore:${draftId}`;
}

function offerSummary(record: WizardDraftRecord): string | null {
  const stage = draftStage(record);
  if (!stage) return null;
  return formatMsg("submit.draft.restore.summary", {
    stage: msg(`submit.stage.${stage}` as MessageKey),
  });
}

/**
 * Owns the durable draft for the signed-in account on `/submit`: discovers it
 * once the account is known, offers it back through one actionable toast,
 * and hands the wizard a small API for publishing snapshots. `onContinue`
 * and `onStartNew` remount the wizard; they fire only after storage has
 * confirmed the choice.
 *
 * `cloning` (a clone or share link is open) wins over a saved draft: the
 * draft is discarded without an offer and the clone becomes the new draft.
 * `suspended` (a guided tour drives the form with demo data) stops drafting
 * for the rest of this visit, so the tour's fixtures never overwrite a real
 * setup; the stored draft is offered again on the next visit.
 */
export function useWizardDraftController({
  cloning,
  suspended,
  onContinue,
  onStartNew,
}: {
  cloning: boolean;
  suspended: boolean;
  onContinue: () => void;
  onStartNew: () => void;
}) {
  const { data: session, status } = useSession();
  const accountId = status === "loading" ? null : sessionIdentity(session) || null;

  const saverRef = useRef<DraftSaver | null>(null);
  const accountRef = useRef<string | null>(null);
  useEffect(() => {
    accountRef.current = accountId;
  }, [accountId]);
  const transitions = useRef({ onContinue, onStartNew });
  useEffect(() => {
    transitions.current = { onContinue, onStartNew };
  }, [onContinue, onStartNew]);
  const cloningRef = useRef(cloning);
  useEffect(() => {
    cloningRef.current = cloning;
  }, [cloning]);
  const pausedRef = useRef(suspended);
  const channelRef = useRef<ReturnType<typeof openDraftChannel> | null>(null);

  const [offer, setOffer] = useState<WizardDraftRecord | null>(null);
  const offerRef = useRef(offer);
  useEffect(() => {
    offerRef.current = offer;
  }, [offer]);
  const offerStateRef = useRef<{ state: DraftRestoreState; failure: string | null }>({
    state: "offer",
    failure: null,
  });

  const dismissOffer = useCallback(() => {
    const current = offerRef.current;
    if (current) toast.dismiss(offerToastId(current.id));
    offerRef.current = null;
    setOffer(null);
  }, []);

  useEffect(() => {
    if (!suspended || pausedRef.current) return;
    pausedRef.current = true;
    saverRef.current?.hold(true);
    dismissOffer();
  }, [suspended, dismissOffer]);

  const startNew = useCallback(async (): Promise<boolean> => {
    const saver = saverRef.current;
    if (!saver) {
      dismissOffer();
      transitions.current.onStartNew();
      return true;
    }
    try {
      await saver.reset();
    } catch {
      toast.error(msg("submit.draft.reset_failed"));
      return false;
    }
    if (accountRef.current) {
      channelRef.current?.post({ type: "reset", accountId: accountRef.current });
    }
    dismissOffer();
    if (!pausedRef.current) saver.hold(false);
    transitions.current.onStartNew();
    return true;
  }, [dismissOffer]);

  const renderOffer = useCallback(
    (record: WizardDraftRecord, continueDraft: () => void) => (
      <DraftRestoreToast
        title={msg("submit.draft.restore.title")}
        summary={offerSummary(record)}
        state={offerStateRef.current.state}
        failureText={offerStateRef.current.failure}
        continueLabel={msg("submit.draft.restore.continue")}
        retryLabel={msg("submit.draft.restore.retry")}
        startNewLabel={msg("submit.draft.restore.start_new")}
        onContinue={continueDraft}
        onStartNew={() => void startNew()}
      />
    ),
    [startNew],
  );

  const continueDraftRef = useRef<() => void>(() => {});
  const continueDraft = () => {
    const saver = saverRef.current;
    const current = offerRef.current;
    const account = accountRef.current;
    if (!saver || !current || !account) return;
    const id = offerToastId(current.id);
    const show = (state: DraftRestoreState, failure: string | null) => {
      offerStateRef.current = { state, failure };
      toast.update(id, { render: renderOffer(current, () => continueDraftRef.current()) });
    };
    show("working", null);
    indexedDbDraftStore
      .read(account)
      .then((fresh) => {
        if (offerRef.current !== current) return;
        if (!fresh || !hasMeaningfulDraft(fresh)) {
          show("failed", msg("submit.draft.restore.gone"));
          return;
        }
        saver.adopt(fresh);
        saver.hold(false);
        dismissOffer();
        transitions.current.onContinue();
      })
      .catch(() => {
        if (offerRef.current !== current) return;
        show("failed", msg("submit.draft.restore.failed"));
      });
  };
  useEffect(() => {
    continueDraftRef.current = continueDraft;
  });

  useEffect(() => {
    if (!offer) return;
    offerStateRef.current = { state: "offer", failure: null };
    toast(
      renderOffer(offer, () => continueDraftRef.current()),
      {
        toastId: offerToastId(offer.id),
        autoClose: false,
        closeOnClick: false,
        closeButton: false,
        draggable: false,
        hideProgressBar: true,
        role: "status",
      },
    );
  }, [offer, renderOffer]);

  // Leaving `/submit` keeps the draft and drops the offer; it comes back with
  // the page, and its buttons would otherwise point at an unmounted screen.
  useEffect(() => () => dismissOffer(), [dismissOffer]);

  useEffect(() => {
    const channel = openDraftChannel((message) => {
      if (message.type === "wipe") {
        // Signed out: nothing may be written again until a new account loads.
        dismissOffer();
        saverRef.current?.detach();
        return;
      }
      if (message.type !== "reset" || message.accountId !== accountRef.current) return;
      dismissOffer();
      saverRef.current?.dropQueued();
    });
    channelRef.current = channel;
    return () => {
      channel.close();
      channelRef.current = null;
    };
  }, [dismissOffer]);

  useEffect(() => {
    dismissOffer();
    saverRef.current?.detach();
    saverRef.current = null;
    if (!accountId) return;
    const saver = new DraftSaver(accountId, {
      store: indexedDbDraftStore,
      onWritten: (record) =>
        channelRef.current?.post({
          type: "written",
          accountId,
          id: record.id,
          revision: record.revision,
        }),
    });
    saverRef.current = saver;
    const epoch = saver.epoch;
    let cancelled = false;
    const release = () => {
      if (!pausedRef.current) saver.hold(false);
    };
    indexedDbDraftStore
      .read(accountId)
      .then((record) => {
        if (cancelled || saver.epoch !== epoch) return;
        if (!record || !hasMeaningfulDraft(record) || cloningRef.current) {
          if (record) {
            void indexedDbDraftStore.remove(accountId).catch(() => {});
            if (cloningRef.current) channelRef.current?.post({ type: "reset", accountId });
          }
          saver.adopt(null);
          release();
          return;
        }
        if (takeResumeAfterReload(accountId)) {
          saver.adopt(record);
          release();
          transitions.current.onContinue();
          return;
        }
        saver.adopt(record);
        if (pausedRef.current) return;
        setOffer(record);
      })
      .catch(() => {
        if (cancelled || saver.epoch !== epoch) return;
        saver.adopt(null);
        release();
      });
    return () => {
      cancelled = true;
    };
  }, [accountId, dismissOffer]);

  useEffect(() => {
    const onLocaleReload = () => {
      const saver = saverRef.current;
      const account = accountRef.current;
      if (!saver || !account || saver.isHeld || !hasMeaningfulDraft(saver.current)) return;
      markResumeAfterReload(account);
      void saver.flush();
    };
    window.addEventListener(LOCALE_RELOAD_EVENT, onLocaleReload);
    return () => window.removeEventListener(LOCALE_RELOAD_EVENT, onLocaleReload);
  }, []);

  const offerPending = offer !== null;
  const api = useMemo<WizardDraftsApi>(
    () => ({
      offerPending,
      takeSnapshot: () => {
        const saver = saverRef.current;
        if (!saver || saver.isHeld) return null;
        return saver.current?.program?.data ?? null;
      },
      publish: (data, meaningful) => {
        if (pausedRef.current) return;
        saverRef.current?.publish(data, meaningful);
      },
      flush: () => void saverRef.current?.flush(),
      consumed: () => {
        const saver = saverRef.current;
        if (!saver || pausedRef.current) return;
        saver
          .reset()
          .then(() => {
            if (accountRef.current) {
              channelRef.current?.post({ type: "reset", accountId: accountRef.current });
            }
          })
          .catch(() => {});
      },
    }),
    [offerPending],
  );

  return { api, offerPending, startNew };
}
