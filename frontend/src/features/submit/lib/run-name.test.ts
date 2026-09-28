import assert from "node:assert/strict";
import { test } from "node:test";

import { suggestedDspyRunName, suggestedRunName } from "./run-name.ts";

test("suggestedRunName takes the first sentence and trims punctuation", () => {
  assert.equal(suggestedRunName(""), "");
  assert.equal(
    suggestedRunName("  Short, accurate answers. Cite the source.  "),
    "Short, accurate answers",
  );
  assert.equal(suggestedRunName("Improve recall\nsecond line"), "Improve recall");
  assert.equal(suggestedRunName("תשובות קצרות ומדויקות. עם מקורות."), "תשובות קצרות ומדויקות");
});

test("suggestedRunName cuts long sentences at a word boundary", () => {
  const long =
    "Make the assistant answer customer billing questions accurately and politely every time";
  const name = suggestedRunName(long, 40);
  assert.ok(name.length <= 41, name);
  assert.equal(name, "Make the assistant answer customer…");
});

const TEMPLATE = 'class MySignature(dspy.Signature):\n    """Describe the task here."""\n';

test("suggestedDspyRunName uses the Signature docstring once it differs from the template", () => {
  const code = TEMPLATE.replace(
    "Describe the task here.",
    "Grade short answers to math questions. Be strict.",
  );
  assert.equal(suggestedDspyRunName(code, "x.json"), "Grade short answers to math questions");
});

test("suggestedDspyRunName falls back to the dataset file stem, then to blank", () => {
  assert.equal(suggestedDspyRunName(TEMPLATE, "math_questions-v2.csv"), "math questions v2");
  assert.equal(suggestedDspyRunName(TEMPLATE, null), "");
  assert.equal(suggestedDspyRunName("", null), "");
});
