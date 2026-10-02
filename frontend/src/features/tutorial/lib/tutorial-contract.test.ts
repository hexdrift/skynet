/** Guard tutorial routes, targets, tracks, and localized copy against product drift. */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { TUTORIAL_DEMO_RUN_MS, TUTORIAL_SUBMIT_SPLASH_MS } from "./tutorial-timing.ts";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const STEPS_PATH = join(HERE, "steps.ts");
const MENU_PATH = join(HERE, "../components/tutorial-menu.tsx");
const DEMO_DATA_PATH = join(HERE, "demo-data.ts");
const DETAIL_VIEW_PATH = join(HERE, "../../optimizations/components/OptimizationDetailView.tsx");
const SUBMIT_WIZARD_PATH = join(HERE, "../../submit/hooks/use-submit-wizard.ts");
const SRC_PATH = fileURLToPath(new URL("../../../", import.meta.url));
const HE_PATH = fileURLToPath(new URL("../../../../../i18n/locales/ui/he.json", import.meta.url));

/** Each step's id and guides, resolved through the track constants in steps.ts. */
function readStepTracks(): Array<{ id: string; tracks: string[] }> {
  const steps = readFileSync(STEPS_PATH, "utf8");
  const constants = new Map(
    [...steps.matchAll(/const (\w+): readonly TutorialTrack\[\] = \[([^\]]*)\]/g)].map((match) => [
      match[1]!,
      [...match[2]!.matchAll(/"(\w+)"/g)].map((track) => track[1]!),
    ]),
  );
  return [...steps.matchAll(/id: "(dd-[^"]+)"[\s\S]*?tracks: (\w+)/g)].map((match) => {
    const tracks = constants.get(match[2]!);
    assert.ok(tracks, `Unknown track constant: ${match[2]}`);
    return { id: match[1]!, tracks };
  });
}

function idsIn(track: string): string[] {
  return readStepTracks()
    .filter((step) => step.tracks.includes(track))
    .map((step) => step.id);
}

function readSourceTree(directory: string): string {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) return readSourceTree(path);
      if (![".ts", ".tsx"].includes(extname(entry.name)) || path === STEPS_PATH) return [];
      return [readFileSync(path, "utf8")];
    })
    .join("\n");
}

test("every tutorial spotlight target is still declared by the application", () => {
  const steps = readFileSync(STEPS_PATH, "utf8");
  const appSource = readSourceTree(SRC_PATH);
  const targets = [...steps.matchAll(/target: "\[data-tutorial='([^']+)'\]"/g)].map(
    (match) => match[1],
  );

  assert.ok(targets.length > 0);
  for (const target of targets) {
    assert.ok(
      appSource.includes(`"${target}"`) || appSource.includes(`'${target}'`),
      `Missing application target for tutorial step: ${target}`,
    );
  }
});

test("tutorial workflow tracks stay synchronized with the chooser", () => {
  const steps = readFileSync(STEPS_PATH, "utf8");
  const menu = readFileSync(MENU_PATH, "utf8");
  const tracks = ["quick", "data", "results", "workspace", "advanced"];

  for (const track of tracks) {
    assert.match(steps, new RegExp(`\\b${track}: \\{`));
    assert.ok(menu.includes(`id: "${track}"`));
  }
  assert.doesNotMatch(menu, /id: "build"/);
  assert.doesNotMatch(steps, /\| "build"/);
  assert.doesNotMatch(steps, /deep-dive/);
  assert.doesNotMatch(menu, /deep-dive/);
});

test("each short guide stays at eight steps or fewer", () => {
  const counts = Object.fromEntries(
    ["quick", "data", "results", "workspace", "advanced"].map((track) => [
      track,
      idsIn(track).length,
    ]),
  );

  assert.deepEqual(counts, { quick: 8, data: 5, results: 8, workspace: 5, advanced: 13 });
  for (const track of ["quick", "data", "results", "workspace"]) {
    assert.ok(counts[track]! <= 8, `${track} guide has ${counts[track]} steps`);
  }
});

test("the demo result includes the source code highlighted by the guide", () => {
  const demo = readFileSync(DEMO_DATA_PATH, "utf8");
  const detail = readFileSync(DETAIL_VIEW_PATH, "utf8");

  assert.match(demo, /signature_code: DEMO_SIGNATURE_CODE/);
  assert.match(demo, /metric_code: DEMO_METRIC_CODE/);
  assert.match(detail, /setPayload\(buildDemoOptimizationPayload\(\)\)/);
});

test("the quick-start guide keeps demo code deterministic and cost-free", () => {
  const steps = readFileSync(STEPS_PATH, "utf8");
  const wizard = readFileSync(SUBMIT_WIZARD_PATH, "utf8");

  assert.match(steps, /callTutorialHook\("setCodeAssistMode", "auto"\)/);
  assert.match(wizard, /setSignatureManuallyEdited\(true\)/);
  assert.match(wizard, /setMetricManuallyEdited\(true\)/);
});

test("the quick-start demo run stays live long enough to watch", () => {
  assert.ok(TUTORIAL_SUBMIT_SPLASH_MS <= 500);
  assert.ok(TUTORIAL_DEMO_RUN_MS >= 8_000 && TUTORIAL_DEMO_RUN_MS <= 12_000);
});

test("tutorial-owned message keys exist in the Hebrew catalog", () => {
  const steps = readFileSync(STEPS_PATH, "utf8");
  const menu = readFileSync(MENU_PATH, "utf8");
  const he = JSON.parse(readFileSync(HE_PATH, "utf8")) as Record<string, string>;
  const keys = new Set(
    [...`${steps}\n${menu}`.matchAll(/"(tutorial\.[^"]+)"/g)].map((match) => match[1]),
  );

  for (const key of keys) {
    assert.ok(key in he, `Missing Hebrew tutorial message: ${key}`);
  }
});

test("the quick start tags data, optimizes, watches the run live, and stops at the score", () => {
  assert.deepEqual(idsIn("quick"), [
    "dd-tagger-setup",
    "dd-tagger-modes",
    "dd-data-upload",
    "dd-code-setup",
    "dd-models",
    "dd-review",
    "dd-live-run",
    "dd-scores",
  ]);
});

test("the data guide ends on the labeling screen, not on wizard settings", () => {
  assert.deepEqual(idsIn("data"), [
    "dd-dataset-add",
    "dd-dataset-actions",
    "dd-tagger-setup",
    "dd-tagger-modes",
    "dd-tagging-live",
  ]);
});

test("the advanced guide is the quick start at full length", () => {
  const advanced = idsIn("advanced");
  const quick = idsIn("quick");

  assert.deepEqual(
    advanced.filter((id) => quick.includes(id)),
    quick,
  );
  for (const id of [
    "dd-tagging-live",
    "dd-data-splits",
    "dd-search-depth",
    "dd-score-chart",
    "dd-trajectory",
  ]) {
    assert.ok(advanced.includes(id), `advanced guide skips ${id}`);
  }
});

test("outside the advanced guide, only the tagger steps are shared", () => {
  const shared = readStepTracks()
    .filter((step) => step.tracks.filter((track) => track !== "advanced").length > 1)
    .map((step) => step.id);

  assert.deepEqual(shared, ["dd-tagger-setup", "dd-tagger-modes"]);
});
