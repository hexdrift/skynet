# Dead-Code Audit Report

**214 candidates from a verified Skynet monorepo sweep: 204 confirmed dead and safe to auto-remove, 10 needing human review.**

| Area | Confirmed | Needs review |
|------|----------:|-------------:|
| backend | 24 | 1 |
| frontend | 109 | 2 |
| optimizations | 2 | 0 |
| compare | 1 | 0 |
| trajectory | 60 | 0 |
| sidebar | 11 | 0 |
| settings | 1 | 0 |
| tagger | 1 | 0 |
| data | 2 | 2 |
| i18n | 53 | 5 |
| **Total** | **204** | **10** |

> Areas mix the original `area` tag and the file location, so the per-area split groups by the tag attached to each item. Frontend `agent-panel`/`dashboard`/`tutorial`/etc. items carry the `frontend` tag; trajectory/sidebar/compare/etc. carry their feature tag.

---

## Confirmed dead (safe to remove)

204 items, grouped by area then kind. Each line: `file:line — symbol — kind — removal action` followed by the verifier reason.

### backend

#### unused-import
- [ ] `backend/core/api/app.py:32` — `Response` — unused-import — remove `, Response` from `from fastapi import FastAPI, HTTPException, Request, Response`.
  - _Verifier:_ fastapi.Response appears only on import line 32; no `__all__`/re-export, module exposes only `create_app`, and all other Response-suffixed names are distinct identifiers.
- [ ] `backend/core/api/routers/serve.py:20` — `Request` — unused-import — remove `, Request` from `from fastapi import APIRouter, Depends, Header, Request`.
  - _Verifier:_ fastapi.Request import is never referenced; all `Request` token hits are compound symbols (RequestUserInferenceRequest/ServeRequest/etc.) or docstring prose.

#### unused-function
- [ ] `backend/core/api/tests/mocks.py:78` — `real_run_response_dict` — unused-function — delete function (lines 78-84) and its name from the module docstring import example on line 11.
  - _Verifier:_ Only references are the def and a docstring example; every `from .mocks import` names symbols explicitly and none import it. No star-imports, `__all__`, getattr, or importlib access.
- [ ] `backend/core/api/tests/mocks.py:96` — `real_program_artifact_dict` — unused-function — delete function (lines 96-102) and its name from the docstring import example on line 13.
  - _Verifier:_ Only source hits are the def and the docstring import example; all real consumers use explicit named imports. No `__all__`, star-import, fixture decorator, or getattr dispatch.
- [ ] `backend/core/api/tests/mocks.py:105` — `real_optimization_status_dict` — unused-function — delete function (lines 105-126).
  - _Verifier:_ Only the def exists repo-wide; the lone other hit is a `.mypy_cache` symbol table, no import/`__all__`/string-literal/dynamic-dispatch reaches it.
- [ ] `backend/core/api/tests/mocks.py:515` — `fake_job_store_with_success_single` — unused-function — delete function (lines 515-546).
  - _Verifier:_ Whole-repo grep finds only the def plus stale caches; no imports, calls, `__all__`, barrel re-export, or fixture decorator. Sibling `fake_background_worker` is genuinely imported, proving real usage would surface.
- [ ] `backend/core/api/tests/mocks.py:549` — `fake_job_store_with_grid` — unused-function — delete function (lines 549-582).
  - _Verifier:_ Symbol appears only at its own def; sole other hit is a `.mypy_cache` node. conftest imports only `FakeJobStore`; no `__all__`/star-import/getattr dispatch.
- [ ] `backend/core/api/tests/mocks.py:585` — `fake_job_store_with_failed` — unused-function — delete function (lines 585-616).
  - _Verifier:_ Orphaned factory; `.mocks` is imported with explicit named imports that exclude it, no `@pytest.fixture`, no `__all__`, no wildcard import.
- [ ] `backend/core/api/tests/mocks.py:638` — `override_job_store` — unused-function — delete contextmanager (lines 638-650, including the `@contextmanager` decorator).
  - _Verifier:_ Zero call sites/imports repo-wide; word-boundary and string-literal searches return only its own def. No `__all__`, wildcard import, or dynamic getattr.
- [ ] `backend/core/api/tests/mocks.py:653` — `override_worker` — unused-function — delete contextmanager (lines 653-665, including the `@contextmanager` decorator).
  - _Verifier:_ Whole-repo search finds it only at its own def; the sole importer of `.mocks` does not import it, no `__all__`/star-import/getattr.
- [ ] `backend/core/api/tests/mocks.py:668` — `override_dspy_service` — unused-function — delete contextmanager (lines 668-681, including the `@contextmanager` decorator).
  - _Verifier:_ Only hits are its own def and a mypy cache artifact; tests that block DSPy init patch `core.api.app.DspyService` directly instead.
- [ ] `backend/core/service_gateway/embedding_pipeline/embeddings.py:144` — `reset_embedder_for_tests` — unused-function — delete function (lines 144-148).
  - _Verifier:_ Only the definition exists in source; not in `__all__`, not re-exported, no test references it (no embedding_pipeline/tests dir), no dynamic/string usage.
- [ ] `backend/core/service_gateway/tests/mocks.py:80` — `fake_optimizer` — unused-function — delete function (lines 80-82) and its mention in the docstring Usage example (line 13).
  - _Verifier:_ Found only at its def and a docstring Usage mention; `test_gateway_run.py` imports 5 other names, not this one. `patch_core_dependencies` builds its own MagicMock at line 122.
- [ ] `backend/core/registry/tests/mocks.py:33` — `fake_optimizer_class` — unused-function — delete function (lines 33-44, including the nested `_optimizer`).
  - _Verifier:_ Only references are its def plus derived caches; the sole importer `test_resolvers.py` imports `REAL_MODULE_NAME`/`fake_dspy_module`/`patch_loader` but never this. No star-import/`__all__`/getattr.

#### unused-class
- [ ] `backend/core/service_gateway/optimization/training_ground/gepa_adapter.py:596` — `TrainingGroundDspyAdapterInstance` — unused-class — delete class (lines 596-597).
  - _Verifier:_ Empty subclass; only repo hit is its own definition. Not in `__all__`; `optimize.py`/`run_react.py` use the base class. The docstring's claim about optimize.py is stale.

#### unused-variable
- [ ] `backend/core/service_gateway/tests/mocks.py:35` — `REAL_AVG_RESPONSE_TIME_MS` — unused-variable — delete assignment on line 35 and remove from the docstring Usage example (line 21).
  - _Verifier:_ Appears only at its def and a non-executable docstring list; no test imports it, no `__all__`/star-import/getattr access.
- [ ] `backend/core/service_gateway/tests/mocks.py:36` — `REAL_BASELINE_METRIC` — unused-variable — delete assignment on line 36 and remove from the docstring Usage example (line 17).
  - _Verifier:_ Appears only in mocks.py (def + docstring); all 3 real importers pull function names only, never this constant.
- [ ] `backend/core/service_gateway/tests/mocks.py:37` — `REAL_OPTIMIZED_METRIC` — unused-variable — delete assignment on line 37 and remove from the docstring Usage example (line 18).
  - _Verifier:_ Only def + docstring example; no test imports it, no `__all__`/star-import/getattr/importlib. Other hits are cache artifacts.
- [ ] `backend/core/service_gateway/tests/mocks.py:38` — `REAL_MODULE_NAME` — unused-variable — delete assignment on line 38 and remove from the docstring Usage example (line 20).
  - _Verifier:_ Only mentioned in its own file's docstring; the 3 importers pull only `fake_*` helpers + `patch_core_dependencies`. The other `REAL_MODULE_NAME` (registry/tests) is a distinct, used symbol.
- [ ] `backend/core/service_gateway/tests/mocks.py:39` — `REAL_OPTIMIZER_NAME` — unused-variable — delete assignment on line 39 and remove from the docstring Usage example (line 19).
  - _Verifier:_ Only at its def and docstring example; no importer pulls it, no `__all__`/star-import/getattr; all test `optimizer_name` hits are literal strings.
- [ ] `backend/core/registry/tests/mocks.py:15` — `REAL_OPTIMIZER_NAME` — unused-variable — delete the line `REAL_OPTIMIZER_NAME = "gepa"` (line 15).
  - _Verifier:_ Never imported; the sole importer `test_resolvers.py` imports only `REAL_MODULE_NAME`/`fake_dspy_module`/`patch_loader`, and the other repo hit is a separate symbol in service_gateway/tests/mocks.py.
- [ ] `backend/core/config.py:199` — `Settings.long_running_timeout` — unused-variable — delete the field (config.py lines 199-201) and remove `"LONG_RUNNING_TIMEOUT",` from `_SETTINGS_ENV_VARS` in `backend/tests/unit/test_config.py:36`.
  - _Verifier:_ Field read only by attribute name; whole-repo grep finds it solely at its config.py def and as a bare env-string in the test isolation tuple. No `settings.long_running_timeout` read, no getattr/model_fields iteration.
- [ ] `backend/core/config.py:202` — `Settings.subprocess_timeout` — unused-variable — delete the field (config.py line 202) and remove `"SUBPROCESS_TIMEOUT",` from `_SETTINGS_ENV_VARS` in `backend/tests/unit/test_config.py:37`.
  - _Verifier:_ No application code or test reads `settings.subprocess_timeout`; only the def and a bare env-string in the test-isolation tuple. The sibling `default_timeout` IS read, confirming the grep distinguishes live from dead.

### frontend

#### orphan-file
- [ ] `frontend/src/shared/charts/optimizer-chart.tsx:23` — `OptimizerChart` — orphan-file — delete the file (81 lines) and remove the re-export line 2 in `shared/charts/index.ts`.
  - _Verifier:_ Appears only in its def and the charts barrel re-export; no static/dynamic import, string literal, or computed access anywhere. AnalyticsTab destructures five other charts but never this one.
- [ ] `frontend/src/features/agent-panel/components/FieldPulse.tsx:24` — `FieldPulse` — orphan-file — delete the file.
  - _Verifier:_ Appears only in its own file; no imports, barrel re-export, or dynamic/string/case-insensitive reference. Its dependency `agentPulseTick`/`agentPulseKeys` no longer exists in wizard state.
- [ ] `frontend/src/features/agent-panel/components/OverrideDot.tsx:20` — `OverrideDot` — orphan-file — delete the file.
  - _Verifier:_ Exported but only referenced in its own file; no import, barrel, dynamic import, or string lookup. Only other hits are its own i18n keys consumed inside the component.

#### unused-export
- [ ] `frontend/src/shared/lib/formatters.ts:103` — `jsonPreview` — unused-export — delete function (lines 103-113).
  - _Verifier:_ No consumer references it; identifier, string-literal, and partial-form searches return zero hits. Only the def and the barrel `export *` exist.
- [ ] `frontend/src/shared/ui/skeleton.tsx:38` — `SkeletonGate` — unused-export — delete the `SkeletonGateProps` interface (lines 32-36) and the `SkeletonGate` function (lines 38-47).
  - _Verifier:_ No source reference; all 303 hits are `.next` build artifacts. The 17 importers use only Skeleton/SkeletonTheme/AppSkeletonTheme.
- [ ] `frontend/src/shared/ui/motion.tsx:98` — `HoverScale` — unused-export — delete function (lines 98-117).
  - _Verifier:_ Only hit in source is its own def; all 86 other hits are `.next` artifacts. No import, barrel re-export, `.d.ts` alias, or string-literal usage.
- [ ] `frontend/src/features/trajectory/messages.ts:142` — `TrajectoryMessageKey` — unused-export — delete the exported type alias (line 142).
  - _Verifier:_ Appears only at its definition; the trajectory barrel does not re-export it and the shared aggregator imports only the `trajectoryMessages` value.
- [ ] `frontend/src/features/tutorial/lib/steps.ts:1109` — `TUTORIAL_TRACKS` — unused-export — delete the `export const TUTORIAL_TRACKS` line (line 1109).
  - _Verifier:_ Only its own definition in source; not re-exported from tutorial/index.ts. `getTrack` stays used independently.
- [ ] `frontend/src/features/tutorial/lib/steps.ts:1111` — `getStep` — unused-export — delete function (lines 1111-1114).
  - _Verifier:_ Zero call sites, not re-exported; consumers of `../lib/steps` import `getTrack`/types, not `getStep`. No string-literal or dynamic reference.
- [ ] `frontend/src/features/tutorial/index.ts:3` — `TutorialPopover` (barrel re-export) — unused-export — remove the re-export line 3. Do NOT delete the component.
  - _Verifier:_ Barrel re-export has zero source consumers; `TutorialPopover` is imported directly from `./tutorial-popover` by tutorial-overlay.tsx:10. Other hits are only `.next` artifacts.
- [ ] `frontend/src/features/tutorial/index.ts:5` — `SpotlightMask` (barrel re-export) — unused-export — remove the re-export line 5. Do NOT delete the component.
  - _Verifier:_ No file imports `SpotlightMask` from `@/features/tutorial`; the only live use is the direct relative import in tutorial-overlay.tsx.
- [ ] `frontend/src/features/tutorial/index.ts:10` — `isTutorialNavigating` (barrel re-export) — unused-export — remove `isTutorialNavigating,` from the barrel block (line 10). Do NOT delete the function.
  - _Verifier:_ The only consumer (tutorial-overlay.tsx:12) imports it directly from `../lib/bridge`; no file imports it via the barrel.

#### unused-function
- [ ] `frontend/src/features/agent-panel/hooks/use-wizard-state.tsx:177` — `useWizardState` — unused-function — delete function (lines 177-183).
  - _Verifier:_ No source consumer imports it; the barrel re-exports only `useWizardStateOptional`, all 4 consumers use the Optional variant, and all 379 other hits are `.next` artifacts.
- [ ] `frontend/src/features/dashboard/components/AnalyticsTab.tsx:122` — `copyToClipboard` — unused-function — delete function (lines 122-127) and the now-orphaned `toast` import on line 3.
  - _Verifier:_ No call site anywhere; identifier, string-literal, and case/partial variants return only the definition. Not exported, no barrel, no dynamic import.
- [ ] `frontend/src/features/dashboard/components/AnalyticsTab.tsx:113` — `fmtPct` — unused-function — delete function (lines 113-116).
  - _Verifier:_ Module-local, non-exported, exactly one source occurrence (its def); all other hits are `.next` artifacts. No caller, barrel, or string-keyed reference.
- [ ] `frontend/src/features/dashboard/components/AnalyticsTab.tsx:118` — `toPctScale` — unused-function — delete function (lines 118-120).
  - _Verifier:_ Module-private, unexported, single source occurrence; no caller in-file or repo, no string-literal/renamed/dynamic reference.
- [ ] `frontend/src/features/explore/lib/format.ts:39` — `formatExploreDate` — unused-function — delete exported function (lines 39-44, including JSDoc lines 34-38).
  - _Verifier:_ Source-only grep finds it only at its def; the sole importer ResultsList.tsx excludes it, and the explore barrel re-exports only ExploreView/ExploreSkeleton. Only call sites are stale `.next` artifacts.
- [ ] `frontend/src/features/tutorial/lib/bridge.ts:276` — `setPendingGridDemo / consumePendingGridDemo / gridDemoSlot` — unused-function — delete the gridDemo one-shot block (lines 268-282).
  - _Verifier:_ Appear only in their own def block; not re-exported by tutorial/index.ts, never called. Grid demo uses `setJob(buildGridDemoJob())` directly; `ensureGridDemo()` only navigates by URL.

#### unused-import
- [ ] `frontend/src/features/dashboard/components/AnalyticsTab.tsx:3` — `toast` (react-toastify) — unused-import — remove `import { toast } from "react-toastify"` (line 3, only after deleting `copyToClipboard`).
  - _Verifier:_ Referenced only on line 125 inside `copyToClipboard`, which has zero callers. Removing it alongside its dead consumer is mechanically safe.

#### unused-i18n-key
- [ ] `frontend/src/shared/messages/messages.ts:341` — `auto.shared.ui.confirm.dialog.literal.1 / .2` — unused-i18n-key — delete key lines 341-342.
  - _Verifier:_ Keys appear only at their definition; no ConfirmDialog component, no `msg()`/`tip()` reference, no dynamic key construction, no cross-reference. `msg()` resolves keys via static keyof lookup.
- [ ] `frontend/src/shared/messages/messages.ts:331` — `auto.shared.charts.optimizer.chart.literal.1 / .2` — unused-i18n-key — delete key lines 331-332 together with the OptimizerChart removal.
  - _Verifier:_ Referenced only inside OptimizerChart, which is orphaned (barrel export never consumed). Removal must be coupled with OptimizerChart deletion.
- [ ] `frontend/src/shared/messages/messages.ts:108` — `shared.loading.charts` — unused-i18n-key — delete key line 108.
  - _Verifier:_ Appears only at its def; `msg()`/`formatMsg()` take a statically-typed literal with no dynamic key access, no literal/partial/template/backend/generated-catalog reference.
- [ ] `frontend/src/shared/messages/messages.ts:143` — orphaned `auto.*` keys (compare.page.14, optimizations.id.page.{2,serve_info_failed,24,25}, pairdetailview.4–.15, overviewtab.literal.{1,5}) — unused-i18n-key — delete the listed individual key lines (~21 keys; verify each first).
  - _Verifier:_ Per-key sweep reports zero references for each. Sibling keys with the same prefix ARE used, confirming individual post-refactor orphans, not a whole-namespace miss.
- [ ] `frontend/src/features/agent-panel/components/OverrideDot.tsx:166` — `auto.features.agent.panel.components.overridedot.literal.1` — unused-i18n-key — delete key line 166 in messages.ts (with dead OverrideDot.tsx).
  - _Verifier:_ Referenced only by `msg()` in OverrideDot.tsx, which is itself an orphan (barrel does not re-export it), no dynamic/string lookups.
- [ ] `frontend/src/features/agent-panel/components/OverrideDot.tsx:167` — `auto.features.agent.panel.components.overridedot.literal.2` — unused-i18n-key — delete key line 167 in messages.ts (with dead OverrideDot.tsx).
  - _Verifier:_ Consumed only by `msg()` in the orphan OverrideDot.tsx (zero imports, zero JSX usage, no barrel re-export).
- [ ] `frontend/src/features/agent-panel/messages.ts:411` — `auto.features.agent.panel.components.conversationdrawer.loading` — unused-i18n-key — delete key on line 411.
  - _Verifier:_ Repo-wide grep finds only the definition; ConversationDrawer uses all sibling keys via static `msg()` but never `.loading` (its loading branch renders a skeleton).
- [ ] `frontend/src/features/agent-panel/messages.ts:14` — `auto.features.agent.panel.components.datasetuploadcard.browse` — unused-i18n-key — delete key on line 14.
  - _Verifier:_ Only the def; DatasetUploadCard references every sibling key via literal `msg()` but never `.browse`. No dynamic construction.
- [ ] `frontend/src/features/agent-panel/messages.ts:12` — `auto.features.agent.panel.components.datasetuploadcard.default_prompt` — unused-i18n-key — delete key on line 12.
  - _Verifier:_ Only the def; DatasetUploadCard uses 14 sibling keys but never this one; no dynamic/template-literal key construction.
- [ ] `frontend/src/features/agent-panel/messages.ts:21` — `auto.features.agent.panel.components.datasetuploadcard.remove` — unused-i18n-key — delete key on line 21.
  - _Verifier:_ Only occurrence is its definition; DatasetUploadCard uses `.replace` (not `.remove`), and `msg()` resolves keys by direct dict lookup.
- [ ] `frontend/src/features/agent-panel/messages.ts:9` — `auto.features.agent.panel.components.generalistpanel.5` — unused-i18n-key — delete key on line 9.
  - _Verifier:_ Only at its def; GeneralistPanel skips the `.5` slot. Build-artifact hits are the bundled catalog, not references.
- [ ] `frontend/src/features/agent-panel/messages.ts:189` — `auto.features.agent.panel.components.generalistpanel.literal.3` — unused-i18n-key — delete key on line 189.
  - _Verifier:_ GeneralistPanel uses generalistpanel.literal.{1,2,4,5,6,7,8} but never literal.3; only non-source hits are `.next` artifacts.
- [ ] `frontend/src/features/agent-panel/messages.ts:282` — `auto.features.agent.panel.components.inferenceformcard.literal.1` — unused-i18n-key — delete key on line 282.
  - _Verifier:_ Defined only at messages.ts:282; the live InferenceFormCard uses literal.{2,6,7,8}, never .1.
- [ ] `frontend/src/features/agent-panel/messages.ts:284` — `auto.features.agent.panel.components.inferenceformcard.literal.3` — unused-i18n-key — delete key on line 284.
  - _Verifier:_ No `msg()` reference; InferenceFormCard uses only literal.{2,6,7,8}; sole source match is the def.
- [ ] `frontend/src/features/agent-panel/messages.ts:285` — `auto.features.agent.panel.components.inferenceformcard.literal.4` — unused-i18n-key — delete key on line 285.
  - _Verifier:_ The running state shows a spinner icon with no text; component uses literal.{2,6,7,8}. No dynamic key build.
- [ ] `frontend/src/features/agent-panel/messages.ts:286` — `auto.features.agent.panel.components.inferenceformcard.literal.5` — unused-i18n-key — delete key on line 286.
  - _Verifier:_ Component uses only literals 2,6,7,8 + meta.70 and renders result via SVG, not this text key.
- [ ] `frontend/src/features/agent-panel/messages.ts:290` — `auto.features.agent.panel.components.inferenceformcard.template.1` — unused-i18n-key — delete key on line 290.
  - _Verifier:_ Defined only at messages.ts:290; InferenceFormCard uses 5 other keys but never this one. Only other hits are bundled artifacts.
- [ ] `frontend/src/features/agent-panel/messages.ts:309` — `auto.features.agent.panel.components.toolscarousel.template.5` — unused-i18n-key — delete key on line 309.
  - _Verifier:_ ToolsCarousel references templates .1-.4,.6-.8 but skips .5; only other hits are stale `.next` artifacts.
- [ ] `frontend/src/features/agent-panel/messages.ts:317` — `auto.features.agent.panel.components.toolscarousel.template.9` — unused-i18n-key — delete key on line 317.
  - _Verifier:_ Defined only here; siblings .1-4,.6-8,.11 are used but 9 is not. No codegen or dynamic construction, no backend/locale reference.
- [ ] `frontend/src/features/agent-panel/messages.ts:214` — `auto.features.agent.panel.lib.tool.meta.literal.13` — unused-i18n-key — delete key on line 214.
  - _Verifier:_ Appears only at messages.ts:214; tool-meta.ts skips 13 (and 14/37/38), no dynamic/computed keys.
- [ ] `frontend/src/features/agent-panel/messages.ts:215` — `auto.features.agent.panel.lib.tool.meta.literal.14` — unused-i18n-key — delete key on line 215.
  - _Verifier:_ Defined only at messages.ts:215; tool-meta.ts references meta keys 1,2,6-12,18+ but skips 13-17. All 84 other hits are gitignored `.next` artifacts.
- [ ] `frontend/src/features/agent-panel/messages.ts:236` — `auto.features.agent.panel.lib.tool.meta.literal.37` — unused-i18n-key — delete key on line 236.
  - _Verifier:_ Consumed only via static-literal `msg()`; tool-meta.ts jumps from literal.36 to literal.46, never referencing .37.
- [ ] `frontend/src/features/agent-panel/messages.ts:238` — `auto.features.agent.panel.lib.tool.meta.literal.38` — unused-i18n-key — delete key on line 238.
  - _Verifier:_ tool-meta.ts references literals 1,2,6-12,18-26,30-36,46-78 but skips 37 and 38; `msg()` is a static dict lookup.
- [ ] `frontend/src/features/agent-panel/messages.ts:239` — `auto.features.agent.panel.lib.tool.meta.literal.45` — unused-i18n-key — delete key on line 239.
  - _Verifier:_ tool-meta.ts uses static `msg("literal-N")` and never references .45; no dynamic/interpolated keys exist.
- [ ] `frontend/src/features/agent-panel/messages.ts:345` — `auto.features.agent.panel.lib.tool.meta.template.13` — unused-i18n-key — delete key on line 345.
  - _Verifier:_ Appears only in messages.ts + generated artifacts; tool-meta.ts references templates 1-12 and 14-31 but skips 13. Other .13 hits are different namespaces.
- [ ] `frontend/src/features/agent-panel/messages.ts:358` — `auto.features.agent.panel.lib.tool.meta.template.22` — unused-i18n-key — delete key on line 358.
  - _Verifier:_ tool-meta.ts uses templates 1-12,14-21,25-31 but never .22 (gap of 13,22,23,24). No dynamic/interpolated key construction.
- [ ] `frontend/src/features/agent-panel/messages.ts:359` — `auto.features.agent.panel.lib.tool.meta.template.23` — unused-i18n-key — delete key on line 359.
  - _Verifier:_ Defined only in messages.ts; tool-meta.ts references templates by explicit literal with no computed access, and neither .23 nor .24 appears anywhere.
- [ ] `frontend/src/features/agent-panel/messages.ts:360` — `auto.features.agent.panel.lib.tool.meta.template.24` — unused-i18n-key — delete key on line 360.
  - _Verifier:_ Defined only at messages.ts:360 and referenced nowhere; neighbor 25 is used but 23 and 24 are orphaned. No dynamic lookup.
- [ ] `frontend/src/features/agent-panel/messages.ts:104` — `auto.features.agent.panel.lib.tool.renderers.literal.11` — unused-i18n-key — delete key on line 104.
  - _Verifier:_ Whole-repo grep finds only the def; tool-renderers.tsx has no archive logic; the archive cluster (literal.11-15) is orphaned.
- [ ] `frontend/src/features/agent-panel/messages.ts:105` — `auto.features.agent.panel.lib.tool.renderers.literal.12` — unused-i18n-key — delete key on line 105.
  - _Verifier:_ Only at its def; the archive-status sibling group (11-15,17) is unreferenced — only literal.16 survives.
- [ ] `frontend/src/features/agent-panel/messages.ts:106` — `auto.features.agent.panel.lib.tool.renderers.literal.13` — unused-i18n-key — delete key on line 106.
  - _Verifier:_ Referenced only by its own def; the only '13' in source is the distinct `template.13` namespace. All other hits are `.next` artifacts.
- [ ] `frontend/src/features/agent-panel/messages.ts:107` — `auto.features.agent.panel.lib.tool.renderers.literal.14` — unused-i18n-key — delete key on line 107.
  - _Verifier:_ tool-renderers.tsx uses 41 sibling literal keys but not .14; no dynamic key construction or backend/i18n reference.
- [ ] `frontend/src/features/agent-panel/messages.ts:108` — `auto.features.agent.panel.lib.tool.renderers.literal.15` — unused-i18n-key — delete key on line 108.
  - _Verifier:_ tool-renderers.tsx references literals {1-10,16,18+} but never 15 (archive-toggle handler removed); no computed/dynamic key.
- [ ] `frontend/src/features/agent-panel/messages.ts:110` — `auto.features.agent.panel.lib.tool.renderers.literal.17` — unused-i18n-key — delete key on line 110.
  - _Verifier:_ tool-renderers.tsx references literal.16 and literal.18 but skips 17; `msg()` uses exact string literals. Other hits are `.next` artifacts.
- [ ] `frontend/src/features/agent-panel/messages.ts:137` — `auto.features.agent.panel.lib.tool.renderers.literal.56` — unused-i18n-key — delete key on line 137.
  - _Verifier:_ tool-renderers.tsx `msg()` calls jump from literal.55 to literal.57; no .56 reference, no dynamic key, no backend/locale cross-ref.
- [ ] `frontend/src/features/agent-panel/messages.ts:385` — `auto.features.agent.panel.lib.tool.renderers.template.16` — unused-i18n-key — delete key on line 385.
  - _Verifier:_ tool-renderers.tsx uses template 2-15,20-40 but never 16-19 (the archive group); no dynamic construction.
- [ ] `frontend/src/features/agent-panel/messages.ts:386` — `auto.features.agent.panel.lib.tool.renderers.template.17` — unused-i18n-key — delete key on line 386.
  - _Verifier:_ Defined only at messages.ts:386; consumer references template.2-15 and 20-40 but skips 16-19. The lone `.next` hit is the compiled copy.
- [ ] `frontend/src/features/agent-panel/messages.ts:387` — `auto.features.agent.panel.lib.tool.renderers.template.18` — unused-i18n-key — delete key on line 387.
  - _Verifier:_ Defined only here; consumer references template numbers [2-15,20-40] but never 18 (the archive family 16-19 has no renderer).
- [ ] `frontend/src/features/agent-panel/messages.ts:388` — `auto.features.agent.panel.lib.tool.renderers.template.19` — unused-i18n-key — delete key on line 388.
  - _Verifier:_ Found only in messages.ts:388 plus derived copies; consumers use exact literals with no computed-suffix dispatch, and .19 appears in zero call sites.
- [ ] `frontend/src/features/agent-panel/messages.ts:405` — `auto.features.agent.panel.lib.tool.renderers.template.37` — unused-i18n-key — delete key on line 405.
  - _Verifier:_ Consumed set jumps 36→39; no computed/interpolated key path, no backend/data/i18n ref. Tutorial template.37 is a different namespace.
- [ ] `frontend/src/features/agent-panel/messages.ts:406` — `auto.features.agent.panel.lib.tool.renderers.template.38` — unused-i18n-key — delete key on line 406.
  - _Verifier:_ `msg()`/`formatMsg()` call sites reference neighbors (.30-.36, .39) but never .38; all other hits are `.next` artifacts.

### optimizations

#### unused-i18n-key
- [ ] `frontend/src/features/optimizations/messages.ts:24` — `optimizations.react.api_desc` — unused-i18n-key — delete the entry (lines 24-25).
  - _Verifier:_ Only defined, never consumed; its companion `api_title` IS used in ReactServeApi.tsx:198 while the description slot uses other keys. Only other hits are compiled artifacts.

#### unused-export
- [ ] `frontend/src/features/optimizations/index.ts:2` — `OptimizationDetailView` (barrel re-export) — unused-export — remove the barrel re-export line 2.
  - _Verifier:_ Barrel re-export never imported via `@/features/optimizations`; the only consumer (OptimizationDetailGate.tsx:17) uses the relative path. Component stays live via the Gate.

### compare

#### unused-i18n-key
- [ ] `frontend/src/features/compare/messages.ts:10` — `compare.includes_siblings` — unused-i18n-key — delete the entry (lines 10-11).
  - _Verifier:_ The consuming `formatMsg(...{p1: autoAddedSiblings})` call no longer exists in `/frontend/src`; only references live in regenerable `.next` artifacts.

### trajectory

#### unused-i18n-key
- [ ] `frontend/src/features/trajectory/messages.ts:8` — `trajectory.empty.pre_first_iteration` — unused-i18n-key — delete entry (line 8).
  - _Verifier:_ Appears only at messages.ts:8; no `msg()` call, no computed `MESSAGES[]` key; sibling `no_candidates` is equally orphaned.
- [ ] `frontend/src/features/trajectory/messages.ts:9` — `trajectory.empty.no_candidates` — unused-i18n-key — delete entry (line 9).
  - _Verifier:_ Components resolve all strings via hardcoded keys; no `ln`/`msg` call references it. Other hits are build artifacts.
- [ ] `frontend/src/features/trajectory/messages.ts:13` — `trajectory.node.seed_label` — unused-i18n-key — delete entry (line 13).
  - _Verifier:_ No consumer; sibling `winning_label` is rendered via WinnerBadge, but no seed badge exists despite an `isSeed` flag.
- [ ] `frontend/src/features/trajectory/messages.ts:15` — `trajectory.node.generation_label` — unused-i18n-key — delete entry (line 15).
  - _Verifier:_ Only its definition; superseded by the near-duplicate live key `trajectory.scrubber.generation_value` (same Hebrew "דור {gen}").
- [ ] `frontend/src/features/trajectory/messages.ts:17` — `trajectory.detail.per_example_title` — unused-i18n-key — delete entry (line 17).
  - _Verifier:_ Defined once and never looked up; TrajectoryDrawer uses other `trajectory.detail.*` keys. `node.per_example` hits are an unrelated data field.
- [ ] `frontend/src/features/trajectory/messages.ts:20` — `trajectory.detail.pareto_hint` — unused-i18n-key — delete entry (line 20).
  - _Verifier:_ Appears only at its def; TrajectoryDrawer references every sibling pareto key by literal but never `pareto_hint`. Other hits are stale build cache.
- [ ] `frontend/src/features/trajectory/messages.ts:23` — `trajectory.detail.diff_title` — unused-i18n-key — delete entry (line 23).
  - _Verifier:_ No `msg("trajectory.detail.diff_title")` call or dynamic interpolation; only hits are compiled `.next` artifacts and node_modules.
- [ ] `frontend/src/features/trajectory/messages.ts:24` — `trajectory.detail.diff_show` — unused-i18n-key — delete entry (line 24).
  - _Verifier:_ This key (and `diff_hide`) has zero `msg()`/`formatMsg()` usage and no computed key construction; only hits are `.next` artifacts.
- [ ] `frontend/src/features/trajectory/messages.ts:25` — `trajectory.detail.diff_hide` — unused-i18n-key — delete entry (line 25).
  - _Verifier:_ The diff toggle UI uses a different key family (`trajectory.drawer.toggle.*`); only sibling `diff_unchanged` is consumed.
- [ ] `frontend/src/features/trajectory/messages.ts:27` — `trajectory.detail.diff_no_parent` — unused-i18n-key — delete entry (line 27).
  - _Verifier:_ Only at its def; no `msg()`/`tip()` call, no dynamic key. PromptDiff has no no-parent branch.
- [ ] `frontend/src/features/trajectory/messages.ts:29` — `trajectory.drawer.score_line` — unused-i18n-key — delete entry (line 29).
  - _Verifier:_ No `msg()`/`formatMsg()` call site or any string-literal reference; only the def plus echoed `.next` artifacts.
- [ ] `frontend/src/features/trajectory/messages.ts:30` — `trajectory.drawer.section.scores` — unused-i18n-key — delete entry (line 30).
  - _Verifier:_ The drawer renders only the minibatch section (TrajectoryDrawer.tsx:323); the scores section was superseded by a rename.
- [ ] `frontend/src/features/trajectory/messages.ts:31` — `trajectory.drawer.section.scores.explain` — unused-i18n-key — delete entry (line 31).
  - _Verifier:_ The drawer renders only the minibatch/prompt sections; all `.explain` keys are referenced as full literals with no dynamic `${}.explain` concatenation.
- [ ] `frontend/src/features/trajectory/messages.ts:34` — `trajectory.drawer.parent.link` — unused-i18n-key — delete entry (line 34).
  - _Verifier:_ Appears only at its def; no caller, no partial/interpolated/renamed form. Other matches are stale build-cache artifacts.
- [ ] `frontend/src/features/trajectory/messages.ts:38` — `trajectory.drawer.rejected.subsample` — unused-i18n-key — delete entry (line 38).
  - _Verifier:_ `msg()` lookups are fully static; the subsample count renders via a different key (`trajectory.node.header.sub.examples`).
- [ ] `frontend/src/features/trajectory/messages.ts:39` — `trajectory.drawer.rejected.parent_score` — unused-i18n-key — delete entry (line 39).
  - _Verifier:_ Zero references repo-wide; only its `.explain` sibling appears in a generated audit report, and `msg()` consumers use different keys.
- [ ] `frontend/src/features/trajectory/messages.ts:40` — `trajectory.drawer.rejected.parent_score.explain` — unused-i18n-key — delete entry (line 40).
  - _Verifier:_ TrajectoryDrawer uses prompt_title/.explain/prompt_unavailable only; no dynamic `.explain` interpolation. Other hits are `.next` artifacts and a non-imported audit report.
- [ ] `frontend/src/features/trajectory/messages.ts:41` — `trajectory.drawer.rejected.proposal_score` — unused-i18n-key — delete entry (line 41).
  - _Verifier:_ Only 3 of 12 `drawer.rejected.*` keys are used; no dynamic key construction. Other `proposal_score` hits are an unrelated data field/doc.
- [ ] `frontend/src/features/trajectory/messages.ts:42` — `trajectory.drawer.rejected.proposal_score.explain` — unused-i18n-key — delete entry (line 42).
  - _Verifier:_ No computed `.explain` key construction; the drawer renders rejected scores via `node.header.label.parent_score` and `ghost.proposal_score` data, never this key.
- [ ] `frontend/src/features/trajectory/messages.ts:46` — `trajectory.drawer.rejected.peers_title` — unused-i18n-key — delete entry (line 46).
  - _Verifier:_ The entire 'peers' sub-feature is defined-but-unwired; only hit outside the def is a static markdown audit report citing the `.explain` sibling.
- [ ] `frontend/src/features/trajectory/messages.ts:47` — `trajectory.drawer.rejected.peers_title.explain` — unused-i18n-key — delete entry (line 47).
  - _Verifier:_ The whole `peers_title` cluster (lines 46-49) is unconsumed; `msg()` requires statically-typed literal keys.
- [ ] `frontend/src/features/trajectory/messages.ts:48` — `trajectory.drawer.rejected.no_peers` — unused-i18n-key — delete entry (line 48).
  - _Verifier:_ No `msg("...no_peers")` consumer; the whole peers sibling group is unwired. Other matches are `.next` artifacts.
- [ ] `frontend/src/features/trajectory/messages.ts:49` — `trajectory.drawer.rejected.peer_score` — unused-i18n-key — delete entry (line 49).
  - _Verifier:_ The entire peers sub-section (peers_title/no_peers/peer_score) is never rendered; only hits are the def and compiled copies.
- [ ] `frontend/src/features/trajectory/messages.ts:62` — `trajectory.minibatch.entry_label` — unused-i18n-key — delete entry (line 62).
  - _Verifier:_ Full-repo sweep finds `entry_label` only at its def; every component-used minibatch key is a different sibling.
- [ ] `frontend/src/features/trajectory/messages.ts:74` — `trajectory.ghost.title` — unused-i18n-key — delete entry (line 74).
  - _Verifier:_ Ghost UI uses `trajectory.ghost.legend`, not `.title`; only the def and a generated audit `.md` mention it.
- [ ] `frontend/src/features/trajectory/messages.ts:75` — `trajectory.ghost.title.explain` — unused-i18n-key — delete entry (line 75).
  - _Verifier:_ Zero references outside its def; `msg()` resolves by exact literal with no computed `.explain` derivation. Only other hit is a non-code audit report.
- [ ] `frontend/src/features/trajectory/messages.ts:76` — `trajectory.ghost.iteration` — unused-i18n-key — delete entry (line 76).
  - _Verifier:_ Appears only at its def; ghost iteration is rendered via `trajectory.node.header.*` keys instead.
- [ ] `frontend/src/features/trajectory/messages.ts:77` — `trajectory.ghost.score_line` — unused-i18n-key — delete entry (line 77).
  - _Verifier:_ Only at its def; sibling `trajectory.ghost.legend` IS consumed via direct literal at TrajectoryTree.tsx:579, confirming keys resolve by literal lookup only.
- [ ] `frontend/src/features/trajectory/messages.ts:82` — `trajectory.node.header.iteration` — unused-i18n-key — delete entry (line 82).
  - _Verifier:_ The sole consumer uses the distinct `.label.iteration` variant; no dynamic/concatenated key construction.
- [ ] `frontend/src/features/trajectory/messages.ts:83` — `trajectory.node.header.score_valset` — unused-i18n-key — delete entry (line 83).
  - _Verifier:_ TrajectoryDrawer uses the `.label.score_valset` variant instead; only stale build artifacts contain the literal.
- [ ] `frontend/src/features/trajectory/messages.ts:84` — `trajectory.node.header.score_minibatch` — unused-i18n-key — delete entry (line 84).
  - _Verifier:_ Drawer renders the minibatch score via `.label.score_minibatch` + `.sub.examples`, not this superseded full-sentence template.
- [ ] `frontend/src/features/trajectory/messages.ts:85` — `trajectory.node.header.parent_minibatch` — unused-i18n-key — delete entry (line 85).
  - _Verifier:_ No consumer; sibling keys are used via `msg()` but this one is not, and no computed key could reach it.
- [ ] `frontend/src/features/trajectory/messages.ts:92` — `trajectory.node.section.children` — unused-i18n-key — delete entry (line 92).
  - _Verifier:_ `msg()` does no derived lookup; TrajectoryDrawer consumes only section.prompt/.prompt.explain/.score_detail.valset.
- [ ] `frontend/src/features/trajectory/messages.ts:93` — `trajectory.node.section.children.explain` — unused-i18n-key — delete entry (line 93).
  - _Verifier:_ No `msg()` call references it and no computed `${base}.explain` pattern exists; all live `.explain` keys are passed as full literals.
- [ ] `frontend/src/features/trajectory/messages.ts:94` — `trajectory.node.section.no_children` — unused-i18n-key — delete entry (line 94).
  - _Verifier:_ Siblings `no_rejected_from_here`/`no_adopted_from_parent` are likewise unwired; other hits are `.next` bundles plus unrelated PyTorch code.
- [ ] `frontend/src/features/trajectory/messages.ts:95` — `trajectory.node.section.rejected_from_here` — unused-i18n-key — delete entry (line 95).
  - _Verifier:_ `msg()` resolves keys via literal `MESSAGES[key]` lookup with no dynamic construction; no consumer references it.
- [ ] `frontend/src/features/trajectory/messages.ts:96` — `trajectory.node.section.rejected_from_here.explain` — unused-i18n-key — delete entry (line 96).
  - _Verifier:_ The whole section is unwired (base + `no_` sibling also unconsumed); only hits are its def plus build/audit artifacts.
- [ ] `frontend/src/features/trajectory/messages.ts:97` — `trajectory.node.section.no_rejected_from_here` — unused-i18n-key — delete entry (line 97).
  - _Verifier:_ Spread into MESSAGES but never read; all trajectory `msg()` calls use static literals. Only `.next` build-cache matches.
- [ ] `frontend/src/features/trajectory/messages.ts:98` — `trajectory.node.section.adopted_from_parent` — unused-i18n-key — delete entry (line 98).
  - _Verifier:_ No `msg()` call, no dynamic/template key build; the spread only adds it to the type union, not a consumption.
- [ ] `frontend/src/features/trajectory/messages.ts:99` — `trajectory.node.section.adopted_from_parent.explain` — unused-i18n-key — delete entry (line 99).
  - _Verifier:_ Only in def, generated artifacts, and a markdown audit; no literal or dynamic reference. Sibling section keys are likewise unused.
- [ ] `frontend/src/features/trajectory/messages.ts:100` — `trajectory.node.section.no_adopted_from_parent` — unused-i18n-key — delete entry (line 100).
  - _Verifier:_ Only appears in its def; the consuming TrajectoryDrawer references only prompt/score_detail section keys. Git shows it was never consumed even at introduction.
- [ ] `frontend/src/features/trajectory/messages.ts:103` — `trajectory.prompt.react.instructions` — unused-i18n-key — delete entry (line 103).
  - _Verifier:_ ReactOverlayView renders `overlay.instructions` as raw text with no `msg()` label; sibling `tools.*` keys ARE used.
- [ ] `frontend/src/features/trajectory/messages.ts:104` — `trajectory.prompt.react.instructions.explain` — unused-i18n-key — delete entry (line 104).
  - _Verifier:_ No `msg()`/`formatMsg()` call site; the entire 'instructions' sub-family is orphaned. The audit `.md` mention is non-executable inventory.
- [ ] `frontend/src/features/trajectory/messages.ts:119` — `trajectory.node.kind.accepted` — unused-i18n-key — delete entry (line 119).
  - _Verifier:_ The `view.kind==="accepted"` branches select unrelated keys; no `msg()`/computed-key reference.
- [ ] `frontend/src/features/trajectory/messages.ts:120` — `trajectory.node.kind.rejected` — unused-i18n-key — delete entry (line 120).
  - _Verifier:_ Rendering discriminates on `view.kind` but uses different keys (accepted_title/rejected_title) + a tone prop. Sibling `accepted` key is equally orphaned.
- [ ] `frontend/src/features/trajectory/messages.ts:122` — `trajectory.explainer.generation` — unused-i18n-key — delete entry (line 122).
  - _Verifier:_ Only sibling `.trajectory` is used (TrajectoryPanel.tsx:184); no backend/i18n/test references.
- [ ] `frontend/src/features/trajectory/messages.ts:124` — `trajectory.explainer.score` — unused-i18n-key — delete entry (line 124).
  - _Verifier:_ Only literal sibling consumed is `.trajectory`; no dynamic/template lookups, no backend/i18n/data references.
- [ ] `frontend/src/features/trajectory/messages.ts:129` — `trajectory.controls.fit` — unused-i18n-key — delete entry (line 129).
  - _Verifier:_ Sibling controls keys are consumed via hardcoded literals in TrajectoryTree.tsx but `fit` is not; no computed key construction.
- [ ] `frontend/src/features/trajectory/messages.ts:139` — `trajectory.a11y.live_region` — unused-i18n-key — delete entry (line 139).
  - _Verifier:_ Sibling a11y keys are consumed but `live_region` has no call and no computed lookup. All other hits are `.next` artifacts.

### sidebar

#### unused-function
- [ ] `frontend/src/features/sidebar/lib/group-jobs.ts:19` — `matchesJobSearch` — unused-function — delete function (lines 16-30, with docstring) and remove `matchesJobSearch,` from `sidebar/index.ts` line 1.
  - _Verifier:_ Only two source hits: the def and the barrel re-export; barrel consumers import `groupJobsByRecency`/`Sidebar`, and Sidebar.tsx filters jobs inline.

#### unused-export
- [ ] `frontend/src/features/sidebar/index.ts:1` — `matchesJobSearch` — unused-export — remove `matchesJobSearch,` from the export on line 1.
  - _Verifier:_ Zero importers/string-literal hits; the barrel's only consumers pull Sidebar and groupJobsByRecency, and Sidebar.tsx does no search/filter.
- [ ] `frontend/src/features/sidebar/index.ts:1` — `JobGroup` — unused-export — remove `type JobGroup` from the export on line 1 (keep the interface in group-jobs.ts).
  - _Verifier:_ Used only internally within group-jobs.ts; the barrel's consumer imports `groupJobsByRecency` only. No external import of the type.

#### unused-i18n-key
- [ ] `frontend/src/features/sidebar/messages.ts:27` — `auto.features.sidebar.lib.group.jobs.literal.3` — unused-i18n-key — delete line 27.
  - _Verifier:_ "היום"/Today; group-jobs.ts now buckets by concrete dates and emits only .1/.2/.6. No dynamic `msg()` key. `.next` matches are compiled copies.
- [ ] `frontend/src/features/sidebar/messages.ts:28` — `auto.features.sidebar.lib.group.jobs.literal.4` — unused-i18n-key — delete line 28.
  - _Verifier:_ "אתמול"/Yesterday; group-jobs.ts references only .1/.2/.6 and uses `DATE_FORMATTER` for concrete dates. No interpolated/computed key access.
- [ ] `frontend/src/features/sidebar/messages.ts:29` — `auto.features.sidebar.lib.group.jobs.literal.5` — unused-i18n-key — delete line 29.
  - _Verifier:_ "השבוע"/This week; dead remnant of old relative-recency grouping. All other hits are `.next` artifacts.
- [ ] `frontend/src/features/sidebar/messages.ts:39` — `auto.features.sidebar.components.sidebar.literal.4` — unused-i18n-key — delete line 39.
  - _Verifier:_ "פתיחת סרגל צד"/Open sidebar; Sidebar.tsx uses .1/.2/.7/.10-.15 but never .4. No backend/data/i18n reference.
- [ ] `frontend/src/features/sidebar/messages.ts:41` — `auto.features.sidebar.components.sidebar.literal.6` — unused-i18n-key — delete line 41.
  - _Verifier:_ "כיווץ סרגל צד"/Collapse sidebar; Sidebar uses 1,2,7,10-15 but never 6. Duplicate of the also-unused literal.5.
- [ ] `frontend/src/features/sidebar/messages.ts:43` — `auto.features.sidebar.components.sidebar.literal.8` — unused-i18n-key — delete line 43.
  - _Verifier:_ "חיפוש…"/Search…; the sidebar has no search input. No caller, no dynamic/interpolated key construction.
- [ ] `frontend/src/features/sidebar/messages.ts:51` — `auto.features.sidebar.components.sidebar.template.1` — unused-i18n-key — delete line 51.
  - _Verifier:_ "חיפוש {p1}"/Search {p1}; Sidebar uses only template.2 (L718) and template.3 (L776). Search UI removed. Only `.next` binaries match.

### settings

#### unused-function
- [ ] `frontend/src/features/settings/lib/shortcuts.ts:35` — `matchShortcut` — unused-function — delete function (lines 35-41) and remove `matchShortcut,` from `settings/index.ts` line 13.
  - _Verifier:_ No call site; only hits are its def, an unused barrel re-export, and a comment explaining it is intentionally not used (agent-panel uses local `matchPanelShortcut`).

#### unused-export
- [ ] `frontend/src/features/settings/index.ts:13` — `matchShortcut` — unused-export — remove `matchShortcut` from the export statement on line 13.
  - _Verifier:_ Only 3 source refs: definition, barrel re-export, and a comment that says it is intentionally NOT used. No importer, no string-literal/dynamic/test reference.

### tagger

#### unused-variable
- [ ] `frontend/src/features/tagger/hooks/use-tagger.ts:68` — `annotate` — unused-variable — delete the `annotate` useCallback (lines 68-78) and remove `annotate,` from the returned object (line 137).
  - _Verifier:_ Appears only at its def and in the returned object; the sole consumer TaggerView.tsx enumerates props and never passes `annotate`; no spread, computed access, or `onAnnotate` prop exists.

### data

#### dead-data-file
- [ ] `data/generalist_agent_trajectories.json.pre-bugfix-cleanup.bak` — `generalist_agent_trajectories.json.pre-bugfix-cleanup.bak` — dead-data-file — delete file.
  - _Verifier:_ No reference anywhere; gitignored local backup snapshot, distinct from the live tracked JSON. Path ends in `.bak`.
- [ ] `data/generalist_agent_trajectories.json.pre-profile-cleanup.bak` — `generalist_agent_trajectories.json.pre-profile-cleanup.bak` — dead-data-file — delete file.
  - _Verifier:_ No reference to the `.bak` filename or base symbol; datasets load by explicit literal filenames with no `data/` glob/scandir, so nothing dynamically sweeps in this untracked 1.6M snapshot.

### i18n

#### unused-i18n-key
- [ ] `i18n/locales/he.json:191` — `notifier.label.model` — unused-i18n-key — remove the key (line 191), re-run `scripts/generate_i18n.py`, and remove the English template in `backend/core/i18n_en.py:68`.
  - _Verifier:_ Key/enum appears only in generated catalog/definition files and stale `.next` bundles; notifier.py renders only `notifier.label.score` and `.error`, no dynamic iteration over `notifier.label.*`.
- [ ] `i18n/locales/he.json:189` — `notifier.label.module` — unused-i18n-key — remove the key (line 189), regenerate, and delete the English template in `backend/core/i18n_en.py:69`.
  - _Verifier:_ Zero consumers; notifier.py renders only score/error by literal with no `f"notifier.label.{...}"` loop; enum `NOTIFIER_LABEL_MODULE` unreferenced.
- [ ] `i18n/locales/he.json:190` — `notifier.label.optimizer` — unused-i18n-key — remove the key (line 190), regenerate, and delete `backend/core/i18n_en.py:70`.
  - _Verifier:_ notifier.py renders only `.score` and `.error`; optimizer/user/type/module/model never referenced by literal, enum, or computed key. All hits are generated catalog files.
- [ ] `i18n/locales/he.json:187` — `notifier.label.user` — unused-i18n-key — remove the key (line 187), regenerate, and delete `backend/core/i18n_en.py:73`.
  - _Verifier:_ notifier.py line 223 comment confirms the 'user' line was intentionally removed; enum `NOTIFIER_LABEL_USER` unreferenced, `t()` uses explicit keys with no catalog iteration.
- [ ] `i18n/locales/he.json:144` — `wizard.metric_code_no_callable` — unused-i18n-key — remove the key (line 144), regenerate, and delete the English template in `backend/core/i18n_en.py:151-153`.
  - _Verifier:_ No live consumer: code_validation.py surfaces raw English exception strings, wizard.py emits only optimizer_unknown/module_unknown. All hits are the source key plus generated/build artifacts.
- [ ] `i18n/locales/he.json:143` — `wizard.metric_code_syntax_error` — unused-i18n-key — remove the key (line 143), regenerate, and delete `backend/core/i18n_en.py:150`.
  - _Verifier:_ The real metric syntax-error path in `safe_exec` uses free-text `_error_payload`, not this key; the enum constant has zero consumers, no frontend `msg()` literal.
- [ ] `i18n/locales/he.json:142` — `wizard.signature_code_syntax_error` — unused-i18n-key — remove the key (line 142), regenerate, and delete `backend/core/i18n_en.py:143-146`.
  - _Verifier:_ The real signature-code syntax validation in `service_gateway/optimization/data.py:264-265` raises a hardcoded English `ServiceError`; no string-literal, enum-member, or dynamic-key reference in any handler/router/test.
- [ ] `i18n/locales/he.json:67` — `generation` (term) — unused-i18n-key — remove the term (line 67) and re-run `scripts/generate_i18n.py`.
  - _Verifier:_ Zero consumers: no `TERMS.generation`/`TermKey.GENERATION` in frontend, no `term('generation')` in backend, no `{term.generation}` interpolation. All copies are generated artifacts.
- [ ] `i18n/locales/he.json:66` — `parent` (term) — unused-i18n-key — remove the term (line 66) and regenerate.
  - _Verifier:_ No `TERMS.parent`/`TermKey.PARENT`/`term('parent')` or `{term.parent}` interpolation; only generated echoes derived from this source key. Absent from `i18n/schema.json`.
- [ ] `i18n/locales/he.json:70` — `reflection` (term) — unused-i18n-key — remove the term (line 70) and regenerate.
  - _Verifier:_ Bare `terms.reflection` has zero consumers; all live hits are `reflectionModel`/`REFLECTION_MODEL`/`reflection_minibatch` or separate namespaces (`lmActivity.reflection`, `lm_activity.column.reflection`).
- [ ] `i18n/locales/he.json:68` — `trajectory` (term) — unused-i18n-key — remove the term (line 68) and regenerate.
  - _Verifier:_ No `TERMS.trajectory`/`TermKey.TRAJECTORY` (the enum is never imported) and no `{term.trajectory}` interpolation; the feature dir and `r.trajectory` hits are unrelated message-key/data-field uses.
- [ ] `i18n/locales/he.json:39` — `winningModel` (term) — unused-i18n-key — remove the term (line 39) and regenerate.
  - _Verifier:_ Zero `TERMS.winningModel` access (sibling `winningCandidate` IS used); the snake_case `winning_model` DB/API field is a separate live concept.
- [ ] `i18n/locales/he.json:213` — `gridSearchLabel` — unused-i18n-key — remove from `backend.constants` (line 213), remove the `GRID_SEARCH_LABEL` entry from `_CONSTANT_KEYS` in `backend/core/i18n.py:60`, and regenerate.
  - _Verifier:_ Appears only at the mapping + two he.json locales; no import/getattr/dynamic key resolves it, while sibling `CLONE_NAME_PREFIX` has clear importers.
- [ ] `i18n/locales/he.json:214` — `gridSearchLabelDefinite` — unused-i18n-key — remove from `backend.constants` (line 214), remove the entry from `_CONSTANT_KEYS` in `backend/core/i18n.py:61`, and regenerate.
  - _Verifier:_ Exists only in the two he.json copies and the mapping; no `i18n.GRID_SEARCH_LABEL_DEFINITE`/getattr access (even its sibling is unused).
- [ ] `i18n/locales/he.json:215` — `runLabel` — unused-i18n-key — remove from `backend.constants` (line 215), remove the entry from `_CONSTANT_KEYS` in `backend/core/i18n.py:62`, and regenerate.
  - _Verifier:_ Only the mapping line and he.json; no importer. The frontend `runLabel` is an unrelated React prop in code-editor.tsx.
- [ ] `backend/core/i18n_en.py:116` — `share.forbidden` — unused-i18n-key — delete the entry on line 116.
  - _Verifier:_ Exists only in i18n_en.py:116 plus caches; absent from he.json/i18n_keys.py/frontend, never raised — share.py's deny path raises `optimization.not_found` (404), so this 403 template has no consumer.
- [ ] `frontend/src/shared/messages/messages.ts:14` — `share.create` — unused-i18n-key — delete line 14.
  - _Verifier:_ Appears only at its def; ShareDialog uses the newer Drive-style key set. No `msg()` lookup, dynamic key, or key iteration.
- [ ] `frontend/src/shared/messages/messages.ts:15` — `share.creating` — unused-i18n-key — delete line 15.
  - _Verifier:_ Only at its def; ShareDialog uses `share.searching`/`share.loading`. No literal/interpolated `share.${...}` reference anywhere.
- [ ] `frontend/src/shared/messages/messages.ts:16` — `share.copy` — unused-i18n-key — delete line 16.
  - _Verifier:_ Only at its def; ShareDialog uses `share.copy_link`. `msg()` uses a strict literal-string union with no dynamic `share.*` lookups.
- [ ] `frontend/src/shared/messages/messages.ts:17` — `share.revoke` — unused-i18n-key — delete line 17.
  - _Verifier:_ Only its def; no `msg()` call in source (only `.next` artifacts replicate the catalog). Other 'revoke' hits are unrelated keys/APIs.
- [ ] `frontend/src/shared/messages/messages.ts:18` — `share.created` — unused-i18n-key — delete line 18.
  - _Verifier:_ No `msg("share.created")` in any source; only stale `.next` build chunks/sourcemaps derived from messages.ts.
- [ ] `frontend/src/shared/messages/messages.ts:19` — `share.revoked` — unused-i18n-key — delete line 19.
  - _Verifier:_ No `msg("share.revoked")` call or dynamic `share.${...}` construction; only the def and generated `.next` artifacts.
- [ ] `frontend/src/shared/messages/messages.ts:32` — `share.done` — unused-i18n-key — delete line 32.
  - _Verifier:_ Defined only at messages.ts:32 (plus codedb.snapshot indexes); ShareDialog uses 44 other `share.*` keys but not this one.
- [ ] `frontend/src/shared/messages/messages.ts:33` — `share.close` — unused-i18n-key — delete line 33.
  - _Verifier:_ Only source occurrence is its def; no `msg()` call, computed/interpolated key, or backend i18n reference.
- [ ] `frontend/src/shared/messages/messages.ts:38` — `share.people` — unused-i18n-key — delete line 38.
  - _Verifier:_ Only at its def; only the sibling `share.people_with_access` is consumed (ShareDialog.tsx:239).
- [ ] `frontend/src/shared/messages/messages.ts:43` — `share.inviting` — unused-i18n-key — delete line 43.
  - _Verifier:_ ShareDialog renders a Loader2 spinner (not `msg("share.inviting")`) for its inviting boolean; no static/dynamic `msg()` call references the key.
- [ ] `frontend/src/shared/messages/messages.ts:54` — `share.remove` — unused-i18n-key — delete line 54.
  - _Verifier:_ ShareDialog consumes `share.remove_member_aria`/`member_removed`; no dynamic/computed `share.`-prefixed lookups.
- [ ] `frontend/src/shared/messages/messages.ts:70` — `share.read_only` — unused-i18n-key — delete line 70.
  - _Verifier:_ No `msg()`/`formatMsg()` call references it; lookup is via typed literal MessageKey (no interpolated `share.*` keys).
- [ ] `frontend/src/shared/messages/messages.ts:76` — `share.cloning` — unused-i18n-key — delete line 76.
  - _Verifier:_ The clone button uses synchronous `router.push()` with no in-flight state; siblings `share.clone`/`clone_tooltip` are consumed but `share.cloning` is not.
- [ ] `frontend/src/shared/messages/messages.ts:77` — `share.run_inference` — unused-i18n-key — delete line 77.
  - _Verifier:_ No consumer repo-wide; only occurrence is the def at line 77 (uncommitted WIP added with other unused sibling clone keys).
- [ ] `frontend/src/shared/messages/messages.ts:78` — `share.playground` — unused-i18n-key — delete line 78.
  - _Verifier:_ Appears only at its def; no `msg()`/`formatMsg()` call, no locale JSON or backend i18n entry.
- [ ] `frontend/src/shared/messages/messages.ts:79` — `share.inference_forbidden` (frontend `sharedMessages` entry) — unused-i18n-key — delete line 79.
  - _Verifier:_ No component calls `msg("share.inference_forbidden")`; the backend DomainError at share.py:1253 resolves via the generated catalog (built from he.json, which lacks this key), never through `sharedMessages`. **Note:** the broader batch of share.* keys is flagged separately for review because of this backend code — see Needs human review.
- [ ] `frontend/src/shared/messages/messages.ts:108` — `shared.loading.charts` — unused-i18n-key — delete line 108.
  - _Verifier:_ Appears only at its def; no `msg()`/`tip()` call, partial form, or computed/template-literal key. (Duplicate listing of the shared-messages-section entry.)
- [ ] `frontend/src/shared/messages/messages.ts:156` — `auto.app.compare.page.14` — unused-i18n-key — delete line 156.
  - _Verifier:_ Compare feature calls keys 1-13 and 15-24 via static-literal `msg()`, skipping 14; no dynamic key path. Only build-artifact occurrences exist.
- [ ] `frontend/src/shared/messages/messages.ts:168` — `auto.app.optimizations.id.page.2` — unused-i18n-key — delete line 168.
  - _Verifier:_ Appears only at its def; no `msg()`/`formatMsg()` literal and no dynamic/template key construction over `auto.app.*` keys.
- [ ] `frontend/src/shared/messages/messages.ts:187` — `auto.app.optimizations.id.page.serve_info_failed` — unused-i18n-key — delete line 187.
  - _Verifier:_ The serve-info failure path in OptimizationDetailView.tsx:530-534 uses a different key (`...page.template.1`); this key is superseded. Other matches are generated artifacts.
- [ ] `frontend/src/shared/messages/messages.ts:192` — `auto.app.optimizations.id.page.24` — unused-i18n-key — delete line 192.
  - _Verifier:_ "POST " value has no reference; neighboring serve-label keys were inlined. The `page.24` cross-file hits are the unrelated `auto.app.compare.page.24` namespace.
- [ ] `frontend/src/shared/messages/messages.ts:193` — `auto.app.optimizations.id.page.25` — unused-i18n-key — delete line 193.
  - _Verifier:_ Siblings id.page.23 and id.page.26 ARE used in ReactServeApi.tsx (proving the absence is real); the `/serve/` value is built as a code template literal, not from this key.
- [ ] `frontend/src/shared/messages/messages.ts:288` — `auto.features.optimizations.components.pairdetailview.4` — unused-i18n-key — delete line 288.
  - _Verifier:_ Occurs only at its def; sibling keys (.1,.2,.3,.16,.17) are actively consumed via literal `msg()`, but .4 is orphaned.
- [ ] `frontend/src/shared/messages/messages.ts:289` — `auto.features.optimizations.components.pairdetailview.5` — unused-i18n-key — delete line 289.
  - _Verifier:_ Only at its def; siblings in the same namespace are referenced while .5 is an orphaned tab label.
- [ ] `frontend/src/shared/messages/messages.ts:290` — `auto.features.optimizations.components.pairdetailview.6` — unused-i18n-key — delete line 290.
  - _Verifier:_ Labels .4-.15 are orphaned leftovers; live tabs use `auto.app.optimizations.id.page.*` keys instead.
- [ ] `frontend/src/shared/messages/messages.ts:291` — `auto.features.optimizations.components.pairdetailview.7` — unused-i18n-key — delete line 291.
  - _Verifier:_ Only in source messages.ts + gitignored `.next` artifacts; MessageKey is a strict union with no template-literal/computed lookups.
- [ ] `frontend/src/shared/messages/messages.ts:292` — `auto.features.optimizations.components.pairdetailview.8` — unused-i18n-key — delete line 292.
  - _Verifier:_ The PairDetailView component does not exist anywhere (orphaned key); `msg()` is only ever called with static literals.
- [ ] `frontend/src/shared/messages/messages.ts:293` — `auto.features.optimizations.components.pairdetailview.9` — unused-i18n-key — delete line 293.
  - _Verifier:_ Visible tab labels use a different namespace (`auto.app.optimizations.id.page.N`); only the def and compiled artifacts.
- [ ] `frontend/src/shared/messages/messages.ts:294` — `auto.features.optimizations.components.pairdetailview.10` — unused-i18n-key — delete line 294.
  - _Verifier:_ "זמן ריצה" appears only at messages.ts:294; no string-literal or dynamic/computed key access anywhere.
- [ ] `frontend/src/shared/messages/messages.ts:295` — `auto.features.optimizations.components.pairdetailview.11` — unused-i18n-key — delete line 295.
  - _Verifier:_ Sibling .1/.2/.3/.16/.17 are consumed but .10-.15 ("קריאות למודל") have zero component references; no dynamic indexing.
- [ ] `frontend/src/shared/messages/messages.ts:296` — `auto.features.optimizations.components.pairdetailview.12` — unused-i18n-key — delete line 296.
  - _Verifier:_ "זמן תגובה ממוצע" appears only at the def; no computed/interpolated key. Sibling keys ARE used via exact literals, confirming keys aren't dynamically dispatched.
- [ ] `frontend/src/shared/messages/messages.ts:297` — `auto.features.optimizations.components.pairdetailview.13` — unused-i18n-key — delete line 297.
  - _Verifier:_ Exhaustive search finds it only at its def; `msg()` does static keyof lookup, and the only referenced pairdetailview keys are .1/.2/.3/.16/.17/.literal.*.
- [ ] `frontend/src/shared/messages/messages.ts:298` — `auto.features.optimizations.components.pairdetailview.14` — unused-i18n-key — delete line 298.
  - _Verifier:_ Only at messages.ts:298; siblings .4-.15 are all orphaned (no PairDetailView component), while only .1,.2,.3,.16,.17,.literal.1-3 are consumed.
- [ ] `frontend/src/shared/messages/messages.ts:299` — `auto.features.optimizations.components.pairdetailview.15` — unused-i18n-key — delete line 299.
  - _Verifier:_ Only the def and stale `.next` chunks; consumers reference only keys 1,2,3,16,17 and `.literal.*` — never .15.
- [ ] `frontend/src/shared/messages/messages.ts:341` — `auto.shared.ui.confirm.dialog.literal.1` — unused-i18n-key — delete line 341.
  - _Verifier:_ Only defined and echoed in stale `.next` artifacts; sibling literal.2 also orphaned, and no ConfirmDialog component exists.
- [ ] `frontend/src/shared/messages/messages.ts:342` — `auto.shared.ui.confirm.dialog.literal.2` — unused-i18n-key — delete line 342.
  - _Verifier:_ Appears only at its def; the source confirm-dialog.tsx component was deleted in commit fc17c40, leaving this and literal.1 orphaned.
- [ ] `frontend/src/shared/messages/messages.ts:449` — `auto.features.optimizations.components.overviewtab.literal.1` — unused-i18n-key — delete line 449.
  - _Verifier:_ OverviewTab.tsx uses `msg()` for literal.2/3/4 only; no `literal.${n}` interpolation. Sole other matches are stale `.next` cache.
- [ ] `frontend/src/shared/messages/messages.ts:453` — `auto.features.optimizations.components.overviewtab.literal.5` — unused-i18n-key — delete line 453.
  - _Verifier:_ OverviewTab uses only literal.2/3/4; `msg()` resolves keys by exact literal with no dynamic access.

---

## Needs human review

10 items. Each is dead by the primary sweep but NOT safe to auto-remove — either a verifier surfaced a refuting reference, the removal has cross-file/codegen blast radius, or it is a deliberately-retained API/glossary surface. Same line shape, with the reason it is held back.

### backend

- [ ] `backend/core/service_gateway/optimization/optimizers.py:355` — `default_model` — unused-variable — delete the parameter from `instantiate_optimizer` and its docstring entry (lines 376-377); update 3 call sites (core.py:383, core.py:699 positional; models.py:624 keyword) and tests in test_optimizers.py.
  - **Why not auto-safe:** Genuinely dead inside the body (never read), but it is passed by all callers, so removal touches 2 production files + tests including positional `core.py` call sites. Mechanically non-trivial. _Refuting reference:_ passed at models.py:624, core.py:384/700 (positional), and test_optimizers.py:355/381/403/426/451.

### frontend

- [ ] `frontend/src/shared/messages/messages.ts:14` — `share.*` legacy public-link keys (16: share.create, .creating, .copy, .revoke, .created, .revoked, .done, .close, .people, .inviting, .remove, .read_only, .cloning, .run_inference, .playground, .inference_forbidden) — unused-i18n-key — delete the 16 listed lines (verify each individually).
  - **Why not auto-safe (REFUTABLE):** `share.inference_forbidden` is emitted live by the backend (share.py:1253 `raise DomainError("share.inference_forbidden")`, also i18n_en.py:117) and is absent from `i18n/locales/he.json` — making the messages.ts Hebrew entry a plausible intended translation home. The batch as a whole is not safe to auto-remove. (Note: the 15 non-`inference_forbidden` keys are individually confirmed-dead above; only the batch verdict is held for review.)
- [ ] `frontend/src/shared/ui/primitives/card.tsx:81` — `CardFooter, CardAction` — unused-export — optionally remove CardAction (lines 81-88) and CardFooter (lines 95-103) and drop them from the export list (line 105).
  - **Why not auto-safe:** Genuinely unused (no live reference anywhere), but they are shadcn/ui design-system primitive API surface intentionally kept for completeness. Removing breaks the standard primitive contract. (CardHeader's `has-data-[slot=card-action]` selector targets the attribute as a CSS string, not a functional reference.)
- [ ] `frontend/src/shared/ui/primitives/table.tsx:42` — `TableFooter, TableCaption` — unused-export — optionally remove TableFooter (lines 42-50) and TableCaption (lines 99-107) and drop them from the export list (line 109).
  - **Why not auto-safe:** No live reference anywhere, but kept as deliberate shadcn primitive API surface. The `<tfoot>` hits elsewhere are raw HTML, not the component.

### data

- [ ] `data/generalist_agent_trajectories.json` — `generalist_agent_trajectories.json` — orphan-file — delete file.
  - **Why not auto-safe:** No reference repo-wide and no generator, but it is a non-`.bak`, real (1.5MB) data file. The other 6 `data/*.json` load via explicit filename strings while this has neither a generator nor a loader — owner confirmation required before deleting real data.
- [ ] `data/math_problems.he.json` — `math_problems.he.json` — orphan-file — delete file (and optionally its generator `scripts/data/generate_math_problems_he.py`) — verify with owner first.
  - **Why not auto-safe:** Only refs are its own generator's OUTPUT path/docstrings; no consumer loads it. But it is a deliberately generated Hebrew/RTL companion dataset (non-`.bak`), so it needs owner confirmation rather than auto-deletion.

### i18n

- [ ] `i18n/locales/he.json:141` — `wizard.signature_code_no_class` — unused-i18n-key — remove the key (line 141), regenerate, and delete `backend/core/i18n_en.py:147-149`.
  - **Why not auto-safe:** The real 'no class' validator (`load_signature_from_code` in optimization/data.py:272) raises a hardcoded string, not this key — so it is dead, but it lives in a codegen catalog. Removal requires editing he.json AND rerunning `scripts/generate_i18n.py`, not a single-line delete.
- [ ] `i18n/locales/he.json:69` — `paretoFront` (term) — unused-i18n-key — remove the term (line 69) and regenerate.
  - **Why not auto-safe (REFUTABLE):** No runtime consumer, but it is the generated source of truth for the backend `TermKey.PARETO_FRONT` enum (i18n_keys.py:191) and the frontend TERMS catalog, and is documented as an intentional glossary term in trajectory/messages.ts:4. Regenerating alters a typed i18n contract surface.
- [ ] `i18n/locales/he.json:71` — `prompt` (term) — unused-i18n-key — remove the term (line 71) and regenerate.
  - **Why not auto-safe:** Genuinely unused (no `TERMS.prompt` access, no `{term.prompt}` interpolation, no `term('prompt')`/`TermKey.PROMPT` call), but it propagates into 3 generated files; a naive line-delete without rerunning `generate_i18n.py` would desync them and fail the CI guard (`generate_i18n.py --check`).
- [ ] `i18n/locales/he.json:72` — `seedCandidate` (term) — unused-i18n-key — remove the term (line 72) and regenerate.
  - **Why not auto-safe (REFUTABLE):** he.json is the generator SOURCE: `seedCandidate` is curated glossary vocab (glossary.yml:130) emitted into `TERMS.SEED_CANDIDATE` and `TermKey.SEED_CANDIDATE`, resolvable via dynamic `term('seedCandidate')`. Removing it without regenerating breaks the CI drift `--check`.

---

## How to apply

To delete the **confirmed-safe** set (204 items), re-run this workflow with `{mode:"apply"}`. The apply pass operates on a fresh branch and lands behind the typecheck/test gate — the deletions are committed only if the suite stays green. The 10 **Needs human review** items are excluded from the automatic apply set and require a human decision (and, for the i18n/codegen cases, a `scripts/generate_i18n.py` regeneration step) before removal.
