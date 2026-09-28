import type {
  ModelConfig,
  SplitFractions,
  ValidateCodeResponse,
  WorkflowSpec,
} from "@/shared/types/api";
import type { ParsedDataset } from "@/shared/lib/parse-dataset";
import type { ReactConfig, ColumnRole } from "../constants";
import type { WizardStageId } from "./wizard-steps";

/**
 * The durable draft of the new-optimization wizard.
 *
 * One record per signed-in account holds the latest snapshot of the form, so
 * a refresh, a closed tab or a later visit can pick the setup back up from
 * the toast offer. The record lives until the user submits, chooses "Start
 * new", blanks every field, signs out, or leaves it untouched for
 * `DRAFT_TTL_MS`. Secrets never enter the record: model credentials and the
 * MCP auth header are scrubbed before a snapshot is published (see
 * `scrubDraftSecrets`).
 */
export interface WizardDraftData {
  stage: WizardStageId;
  furthestStage: WizardStageId;
  summaryTab: number;
  summaryCodeTab: string;
  jobType: "run" | "grid_search";
  isPrivate: boolean;
  jobName: string;
  jobDescription: string;
  moduleName: string;
  moduleChosen: boolean;
  optimizerName: string;
  reactConfig: ReactConfig;
  workflowSpec?: WorkflowSpec | null;
  signatureCode: string;
  metricCode: string;
  signatureManuallyEdited: boolean;
  metricManuallyEdited: boolean;
  // The last server check of the code, so a restored Evaluation stage isn't
  // held for evidence the user already earned. Optional: older drafts lack it.
  signatureValidation?: ValidateCodeResponse | null;
  metricValidation?: ValidateCodeResponse | null;
  parsedDataset: ParsedDataset | null;
  datasetFileName: string | null;
  columnRoles: Record<string, ColumnRole>;
  columnKinds: Record<string, "text" | "image">;
  modelConfig: ModelConfig;
  secondModelConfig: ModelConfig | null;
  generationModels: ModelConfig[];
  reflectionModels: ModelConfig[];
  split: SplitFractions;
  // Optional: absent means the recommended split, as before the toggle moved
  // into the split section.
  splitMode?: "auto" | "manual";
  seed: number | undefined;
  autoLevel: string;
  reflectionMinibatchSize: string;
  maxFullEvals: string;
  maxMetricCalls?: string;
  useMerge: boolean;
  targetScore: string;
  pxnParents?: string;
  pxnProposals?: string;
  shuffle: boolean;
}

export interface DraftWorkflowState<T> {
  data: T;
  meaningful: boolean;
}

export const DRAFT_RECORD_VERSION = 1;

/** An untouched draft expires after a week, so a long-abandoned setup starts clean. */
export const DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export interface WizardDraftRecord {
  version: typeof DRAFT_RECORD_VERSION;
  id: string;
  accountId: string;
  revision: number;
  updatedAt: number;
  program: DraftWorkflowState<WizardDraftData> | null;
}

/** Whether the record was last written more than `DRAFT_TTL_MS` before `now`. */
export function isDraftExpired(record: Pick<WizardDraftRecord, "updatedAt">, now: number): boolean {
  return now - record.updatedAt > DRAFT_TTL_MS;
}

const CREDENTIAL_FIELD =
  /^(?:api[_-]?key|authorization|proxy[_-]?authorization|access[_-]?token|refresh[_-]?token|gateway[_-]?token|secret|password)$/i;

function stripCredentialFields(value: unknown): unknown {
  if (Array.isArray(value)) {
    let changed = false;
    const next = value.map((item) => {
      const stripped = stripCredentialFields(item);
      if (stripped !== item) changed = true;
      return stripped;
    });
    return changed ? next : value;
  }
  if (!value || typeof value !== "object") return value;
  let changed = false;
  const next: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (CREDENTIAL_FIELD.test(key)) {
      changed = true;
      continue;
    }
    const stripped = stripCredentialFields(item);
    if (stripped !== item) changed = true;
    next[key] = stripped;
  }
  return changed ? next : value;
}

/**
 * A model config without any credential it carries inline — an API key or
 * auth header at any depth of `extra`. The rest of the choice survives, and an
 * `extra` emptied by the scrub is dropped.
 */
export function stripModelSecrets(config: ModelConfig): ModelConfig {
  const stripped = stripCredentialFields(config) as ModelConfig;
  if (stripped === config) return config;
  if (stripped.extra && Object.keys(stripped.extra).length === 0) {
    return { ...stripped, extra: undefined };
  }
  return stripped;
}

// The wizard publishes on every commit and the saver skips a snapshot whose
// fields are identical, so an unchanged input must scrub to the same object.
function memoByIdentity<T extends object>(fn: (value: T) => T): (value: T) => T {
  const cache = new WeakMap<T, T>();
  return (value) => {
    let out = cache.get(value);
    if (out === undefined) {
      out = fn(value);
      cache.set(value, out);
    }
    return out;
  };
}

const scrubModel = memoByIdentity(stripModelSecrets);
const scrubModels = memoByIdentity((models: ModelConfig[]) => {
  const next = models.map(scrubModel);
  return next.every((m, i) => m === models[i]) ? models : next;
});
const scrubReactConfig = memoByIdentity((config: ReactConfig) =>
  config.mcpAuthHeader ? { ...config, mcpAuthHeader: "" } : config,
);

/** The snapshot as it may be stored: model credentials and the MCP auth header removed. */
export function scrubDraftSecrets(data: WizardDraftData): WizardDraftData {
  return {
    ...data,
    reactConfig: scrubReactConfig(data.reactConfig),
    modelConfig: scrubModel(data.modelConfig),
    secondModelConfig: data.secondModelConfig ? scrubModel(data.secondModelConfig) : null,
    generationModels: scrubModels(data.generationModels),
    reflectionModels: scrubModels(data.reflectionModels),
  };
}

/** Whether a snapshot holds anything worth offering back. */
export function isMeaningfulProgramDraft(d: WizardDraftData): boolean {
  return (
    d.stage !== "goal" ||
    d.moduleChosen ||
    d.parsedDataset !== null ||
    d.datasetFileName !== null ||
    d.jobName.trim() !== ""
  );
}

/** A record is worth keeping while its snapshot is meaningful. */
export function hasMeaningfulDraft(record: WizardDraftRecord | null): boolean {
  return Boolean(record?.program?.meaningful);
}

/** The stage the restore reopens, for the toast's supporting line. */
export function draftStage(record: WizardDraftRecord | null): WizardStageId | null {
  return hasMeaningfulDraft(record) ? (record?.program?.data.stage ?? null) : null;
}

function shallowEqual(a: object, b: object): boolean {
  const ak = Object.keys(a) as Array<keyof typeof a>;
  const bk = Object.keys(b);
  if (ak.length !== bk.length) return false;
  return ak.every((k) => Object.is(a[k], (b as Record<string, unknown>)[k as string]));
}

export interface DraftStore {
  read(accountId: string): Promise<WizardDraftRecord | null>;
  write(record: WizardDraftRecord): Promise<void>;
  remove(accountId: string): Promise<void>;
}

export interface DraftSaverOptions {
  store: DraftStore;
  debounceMs?: number;
  now?: () => number;
  newId?: () => string;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
  onWriteError?: (error: unknown) => void;
  onWritten?: (record: WizardDraftRecord) => void;
  onRemoved?: () => void;
}

/**
 * Turns the wizard's per-render snapshots into a small number of durable
 * writes, with two rules: nothing is written while `held` (a restore offer is
 * on screen, discovery has not finished, or a tour is driving the form), and
 * a reset bumps a generation so a debounced or in-flight write from before it
 * can never resurrect the record it just deleted.
 */
export class DraftSaver {
  private record: WizardDraftRecord | null = null;
  private dirty = false;
  private held = true;
  private generation = 0;
  private timer: unknown = null;
  private readonly accountId: string;
  private readonly store: DraftStore;
  private readonly debounceMs: number;
  private readonly now: () => number;
  private readonly newId: () => string;
  private readonly setTimer: (fn: () => void, ms: number) => unknown;
  private readonly clearTimer: (handle: unknown) => void;
  private readonly onWriteError?: (error: unknown) => void;
  private readonly onWritten?: (record: WizardDraftRecord) => void;
  private readonly onRemoved?: () => void;

  constructor(accountId: string, options: DraftSaverOptions) {
    this.accountId = accountId;
    this.store = options.store;
    this.debounceMs = options.debounceMs ?? 600;
    this.now = options.now ?? (() => Date.now());
    this.newId = options.newId ?? randomDraftId;
    this.setTimer = options.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
    this.clearTimer =
      options.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));
    this.onWriteError = options.onWriteError;
    this.onWritten = options.onWritten;
    this.onRemoved = options.onRemoved;
  }

  /** The record as this saver last knew it — adopted or written. */
  get current(): WizardDraftRecord | null {
    return this.record;
  }

  get isHeld(): boolean {
    return this.held;
  }

  /** Bumps on every reset or detach; a discovery that started before it is stale. */
  get epoch(): number {
    return this.generation;
  }

  /**
   * Take a discovered record (or its absence) as the base for later writes.
   * Snapshots published before discovery finished are live state, so an
   * empty discovery keeps them; a found record is offered or restored by the
   * caller, whose remount publishes afresh.
   */
  adopt(record: WizardDraftRecord | null): void {
    if (record === null && this.record !== null && this.record.revision === 0) return;
    this.record = record;
    this.dirty = false;
  }

  /** Stop or resume writing; a release with pending changes writes on the debounce. */
  hold(held: boolean): void {
    this.held = held;
    if (held) this.cancelTimer();
    else if (this.dirty) this.schedule();
  }

  /** Fold the latest snapshot into the record; an identical snapshot is ignored. */
  publish(data: WizardDraftData, meaningful: boolean): void {
    const previous = this.record?.program;
    if (previous && previous.meaningful === meaningful && shallowEqual(previous.data, data)) {
      return;
    }
    const base: WizardDraftRecord = this.record ?? {
      version: DRAFT_RECORD_VERSION,
      id: this.newId(),
      accountId: this.accountId,
      revision: 0,
      updatedAt: 0,
      program: null,
    };
    this.record = { ...base, program: { data, meaningful } };
    this.dirty = true;
    this.schedule();
  }

  /** Write any pending change now. Resolves once the store has answered. */
  async flush(): Promise<void> {
    this.cancelTimer();
    if (this.held || !this.dirty) return;
    const generation = this.generation;
    this.dirty = false;
    if (!hasMeaningfulDraft(this.record)) {
      // A blanked-out draft leaves storage but stays in memory at revision 0,
      // so the next identical snapshot is recognised instead of re-queued.
      if (this.record && this.record.revision > 0) {
        this.record = { ...this.record, revision: 0 };
        await this.removeAt(generation);
      }
      return;
    }
    const record: WizardDraftRecord = {
      ...(this.record as WizardDraftRecord),
      revision: (this.record as WizardDraftRecord).revision + 1,
      updatedAt: this.now(),
    };
    try {
      await this.store.write(record);
      if (generation !== this.generation) return;
      this.record = record;
      this.onWritten?.(record);
    } catch (error) {
      if (generation !== this.generation) return;
      this.dirty = true;
      this.onWriteError?.(error);
    }
  }

  /**
   * Delete the record and forget everything queued before this call. Rejects
   * when the store cannot commit the delete, in which case nothing was
   * dropped from memory and the caller must report the failure.
   */
  async reset(): Promise<void> {
    this.cancelTimer();
    this.generation += 1;
    const generation = this.generation;
    await this.store.remove(this.accountId);
    if (generation !== this.generation) return;
    this.record = null;
    this.dirty = false;
    this.onRemoved?.();
  }

  /** Forget the record without touching storage — the account signed out or changed. */
  detach(): void {
    this.dropQueued();
    this.held = true;
  }

  /**
   * Another tab reset this account's draft (or wiped every draft on sign-out):
   * forget the record and anything queued for it, so the next meaningful
   * snapshot here starts a new one instead of writing the deleted record back.
   */
  dropQueued(): void {
    this.cancelTimer();
    this.generation += 1;
    this.record = null;
    this.dirty = false;
  }

  private schedule(): void {
    if (this.held) return;
    this.cancelTimer();
    const generation = this.generation;
    this.timer = this.setTimer(() => {
      this.timer = null;
      if (generation !== this.generation) return;
      void this.flush();
    }, this.debounceMs);
  }

  private cancelTimer(): void {
    if (this.timer !== null) {
      this.clearTimer(this.timer);
      this.timer = null;
    }
  }

  private async removeAt(generation: number): Promise<void> {
    try {
      await this.store.remove(this.accountId);
      if (generation === this.generation) this.onRemoved?.();
    } catch (error) {
      if (generation === this.generation) this.onWriteError?.(error);
    }
  }
}

function randomDraftId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
