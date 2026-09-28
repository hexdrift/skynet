import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DRAFT_TTL_MS,
  DraftSaver,
  draftStage,
  hasMeaningfulDraft,
  isDraftExpired,
  isMeaningfulProgramDraft,
  scrubDraftSecrets,
  stripModelSecrets,
  type DraftStore,
  type WizardDraftData,
  type WizardDraftRecord,
} from "./draft-record.ts";

function programDraft(overrides: Partial<WizardDraftData> = {}): WizardDraftData {
  return {
    stage: "goal",
    furthestStage: "goal",
    summaryTab: 0,
    summaryCodeTab: "signature",
    jobType: "run",
    isPrivate: false,
    jobName: "",
    jobDescription: "",
    moduleName: "predict",
    moduleChosen: false,
    optimizerName: "gepa",
    reactConfig: { mcpUrl: "", mcpAuthHeader: "" },
    signatureCode: "",
    metricCode: "",
    signatureManuallyEdited: false,
    metricManuallyEdited: false,
    parsedDataset: null,
    datasetFileName: null,
    columnRoles: {},
    columnKinds: {},
    modelConfig: { name: "" },
    secondModelConfig: null,
    generationModels: [],
    reflectionModels: [],
    split: { train: 0.6, val: 0.2, test: 0.2 },
    seed: undefined,
    autoLevel: "light",
    reflectionMinibatchSize: "3",
    maxFullEvals: "",
    useMerge: false,
    targetScore: "",
    shuffle: true,
    ...overrides,
  };
}

function fakeStore() {
  let stored: WizardDraftRecord | null = null;
  const log: string[] = [];
  let failWrites = false;
  const store: DraftStore = {
    read: async () => stored,
    write: async (record) => {
      if (failWrites) throw new Error("quota");
      stored = record;
      log.push(`write:${record.revision}`);
    },
    remove: async () => {
      stored = null;
      log.push("remove");
    },
  };
  return {
    store,
    log,
    get stored() {
      return stored;
    },
    setFailWrites(v: boolean) {
      failWrites = v;
    },
  };
}

function fakeTimers() {
  const queue: Array<{ fn: () => void; handle: number }> = [];
  let next = 1;
  return {
    setTimer: (fn: () => void) => {
      const handle = next++;
      queue.push({ fn, handle });
      return handle;
    },
    clearTimer: (handle: unknown) => {
      const i = queue.findIndex((q) => q.handle === handle);
      if (i >= 0) queue.splice(i, 1);
    },
    async fire() {
      const pending = queue.splice(0);
      for (const q of pending) q.fn();
      await new Promise((r) => setTimeout(r, 0));
    },
    get pending() {
      return queue.length;
    },
  };
}

function saverWith(store: DraftStore, timers: ReturnType<typeof fakeTimers>) {
  const errors: unknown[] = [];
  const saver = new DraftSaver("me@example.com", {
    store,
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
    now: () => 1000,
    newId: () => "draft-1",
    onWriteError: (e) => errors.push(e),
  });
  return { saver, errors };
}

test("stripModelSecrets drops inline credentials at any depth and keeps the rest", () => {
  const stripped = stripModelSecrets({
    name: "gpt",
    extra: {
      api_key: "sk-secret",
      region: "eu",
      headers: { Authorization: "Bearer x", "X-Trace": "1" },
      gateway_token: "g",
    },
  });
  assert.deepEqual(stripped, {
    name: "gpt",
    extra: { region: "eu", headers: { "X-Trace": "1" } },
  });
  assert.equal(
    stripModelSecrets({ name: "gpt", extra: { "api-key": "sk-secret" } }).extra,
    undefined,
  );
  const plain = { name: "gpt", extra: { region: "eu" } };
  assert.equal(stripModelSecrets(plain), plain);
});

test("scrubDraftSecrets clears every model's key and the MCP auth header", () => {
  const scrubbed = scrubDraftSecrets(
    programDraft({
      reactConfig: { mcpUrl: "http://tools", mcpAuthHeader: "Bearer secret" },
      modelConfig: { name: "a", extra: { api_key: "k1" } },
      secondModelConfig: { name: "b", extra: { password: "p" } },
      generationModels: [{ name: "c", extra: { secret: "s", temperature: 1 } }],
      reflectionModels: [{ name: "d", extra: { access_token: "t" } }],
    }),
  );
  assert.deepEqual(scrubbed.reactConfig, { mcpUrl: "http://tools", mcpAuthHeader: "" });
  assert.equal(scrubbed.modelConfig.extra, undefined);
  assert.equal(scrubbed.secondModelConfig?.extra, undefined);
  assert.deepEqual(scrubbed.generationModels[0].extra, { temperature: 1 });
  assert.equal(scrubbed.reflectionModels[0].extra, undefined);
  assert.doesNotMatch(JSON.stringify(scrubbed), /k1|"p"|"s"|"t"|secret/);
});

test("scrubbing an unchanged snapshot yields the same field objects", () => {
  const draft = programDraft({
    reactConfig: { mcpUrl: "http://tools", mcpAuthHeader: "Bearer secret" },
    modelConfig: { name: "a", extra: { api_key: "k1" } },
    generationModels: [{ name: "c" }],
  });
  const first = scrubDraftSecrets(draft);
  const second = scrubDraftSecrets({ ...draft });
  assert.equal(first.reactConfig, second.reactConfig);
  assert.equal(first.modelConfig, second.modelConfig);
  assert.equal(second.generationModels, draft.generationModels);
});

test("a draft expires a week after its last write", () => {
  assert.equal(DRAFT_TTL_MS, 7 * 24 * 60 * 60 * 1000);
  assert.equal(isDraftExpired({ updatedAt: 0 }, DRAFT_TTL_MS), false);
  assert.equal(isDraftExpired({ updatedAt: 0 }, DRAFT_TTL_MS + 1), true);
});

test("only a touched form counts as a draft worth offering", () => {
  assert.equal(isMeaningfulProgramDraft(programDraft()), false);
  assert.equal(isMeaningfulProgramDraft(programDraft({ jobName: "  " })), false);
  assert.equal(isMeaningfulProgramDraft(programDraft({ jobName: "run" })), true);
  assert.equal(isMeaningfulProgramDraft(programDraft({ moduleChosen: true })), true);
  assert.equal(isMeaningfulProgramDraft(programDraft({ datasetFileName: "a.csv" })), true);
  assert.equal(isMeaningfulProgramDraft(programDraft({ stage: "evaluation" })), true);

  const record: WizardDraftRecord = {
    version: 1,
    id: "d",
    accountId: "a",
    revision: 1,
    updatedAt: 0,
    program: { data: programDraft({ stage: "optimization" }), meaningful: true },
  };
  assert.equal(hasMeaningfulDraft(record), true);
  assert.equal(draftStage(record), "optimization");
  assert.equal(hasMeaningfulDraft({ ...record, program: null }), false);
  assert.equal(draftStage({ ...record, program: null }), null);
});

test("a held saver writes nothing; release writes once per distinct snapshot", async () => {
  const s = fakeStore();
  const timers = fakeTimers();
  const { saver } = saverWith(s.store, timers);
  const draft = programDraft({ jobName: "shorter emails" });
  saver.publish(draft, true);
  await timers.fire();
  assert.deepEqual(s.log, []);

  saver.adopt(null);
  saver.hold(false);
  await timers.fire();
  assert.deepEqual(s.log, ["write:1"]);
  assert.equal(s.stored?.id, "draft-1");
  assert.equal(s.stored?.accountId, "me@example.com");
  assert.equal(s.stored?.updatedAt, 1000);

  saver.publish({ ...draft }, true);
  assert.equal(timers.pending, 0);

  saver.publish({ ...draft, jobName: "shorter, kinder emails" }, true);
  await timers.fire();
  assert.deepEqual(s.log, ["write:1", "write:2"]);
});

test("holding again cancels a pending write until the next release", async () => {
  const s = fakeStore();
  const timers = fakeTimers();
  const { saver } = saverWith(s.store, timers);
  saver.adopt(null);
  saver.hold(false);
  saver.publish(programDraft({ jobName: "x" }), true);
  saver.hold(true);
  assert.equal(timers.pending, 0);
  await saver.flush();
  assert.deepEqual(s.log, []);
  saver.hold(false);
  await timers.fire();
  assert.deepEqual(s.log, ["write:1"]);
});

test("blanking every field removes the stored record", async () => {
  const s = fakeStore();
  const timers = fakeTimers();
  const { saver } = saverWith(s.store, timers);
  saver.adopt(null);
  saver.hold(false);
  saver.publish(programDraft({ jobName: "x" }), true);
  await timers.fire();
  const blank = programDraft();
  saver.publish(blank, false);
  await timers.fire();
  assert.deepEqual(s.log, ["write:1", "remove"]);
  assert.equal(s.stored, null);
  saver.publish(blank, false);
  assert.equal(timers.pending, 0);
});

test("reset deletes the record and a late debounced write cannot resurrect it", async () => {
  const s = fakeStore();
  const timers = fakeTimers();
  const { saver } = saverWith(s.store, timers);
  saver.adopt(null);
  saver.hold(false);
  saver.publish(programDraft({ jobName: "keep me" }), true);
  await timers.fire();
  assert.equal(s.stored?.revision, 1);

  saver.publish(programDraft({ jobName: "keep me too" }), true);
  const fire = timers.fire.bind(timers);
  await saver.reset();
  await fire();
  assert.equal(s.stored, null);
  assert.deepEqual(s.log, ["write:1", "remove"]);
  assert.equal(saver.current, null);
});

test("a failed write keeps the snapshot dirty and reports once per attempt", async () => {
  const s = fakeStore();
  const timers = fakeTimers();
  const { saver, errors } = saverWith(s.store, timers);
  saver.adopt(null);
  saver.hold(false);
  s.setFailWrites(true);
  saver.publish(programDraft({ jobName: "x" }), true);
  await timers.fire();
  assert.equal(errors.length, 1);
  assert.equal(s.stored, null);
  s.setFailWrites(false);
  await saver.flush();
  assert.equal(s.stored?.revision, 1);
});

test("detach forgets the record without touching storage", async () => {
  const s = fakeStore();
  const timers = fakeTimers();
  const { saver } = saverWith(s.store, timers);
  saver.adopt(null);
  saver.hold(false);
  saver.publish(programDraft({ jobName: "x" }), true);
  await timers.fire();
  saver.detach();
  assert.equal(saver.current, null);
  assert.equal(saver.isHeld, true);
  assert.equal(s.stored?.revision, 1);
});
