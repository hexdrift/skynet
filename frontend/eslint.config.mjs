import { defineConfig, globalIgnores } from "eslint/config";
import i18next from "eslint-plugin-i18next";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const i18nLiteralBacklog = [
  "src/app/compare/page.tsx",
  "src/app/login/page.tsx",
  "src/app/not-found.tsx",
  "src/app/optimizations/*/page.tsx",
  "src/components/ui/dialog.tsx",
  "src/components/ui/sheet.tsx",
  "src/features/agent-panel/components/FirstRunHint.tsx",
  "src/features/agent-panel/components/GeneralistPanel.tsx",
  "src/features/agent-panel/components/MinimizedPill.tsx",
  "src/features/agent-panel/components/SubmitSummaryCard.tsx",
  "src/features/agent-panel/components/ToolCallRow.tsx",
  "src/features/agent-panel/components/ToolsCarousel.tsx",
  "src/features/agent-panel/components/TrustToggle.tsx",
  "src/features/dashboard/components/AnalyticsEmpty.tsx",
  "src/features/dashboard/components/AnalyticsTab.tsx",
  "src/features/dashboard/components/AnalyticsTables.tsx",
  "src/features/dashboard/components/BulkActionBar.tsx",
  "src/features/dashboard/components/DashboardHeader.tsx",
  "src/features/dashboard/components/DashboardView.tsx",
  "src/features/dashboard/components/DeleteDialogs.tsx",
  "src/features/dashboard/components/JobsTab.tsx",
  "src/features/dashboard/components/QueueStatusAlert.tsx",
  "src/features/dashboard/lib/status-badges.tsx",
  "src/features/explore/components/ExploreDetailPanel.tsx",
  "src/features/optimizations/components/CodeTab.tsx",
  "src/features/optimizations/components/ConfigTab.tsx",
  "src/features/optimizations/components/DataTab.tsx",
  "src/features/optimizations/components/DeleteJobDialog.tsx",
  "src/features/optimizations/components/ExportMenu.tsx",
  "src/features/optimizations/components/GridLiveChart.tsx",
  "src/features/optimizations/components/GridOverview.tsx",
  "src/features/optimizations/components/GridServeTab.tsx",
  "src/features/optimizations/components/LogsTab.tsx",
  "src/features/optimizations/components/OverviewTab.tsx",
  "src/features/optimizations/components/PairDetailView.tsx",
  "src/features/optimizations/components/ServeChat.tsx",
  "src/features/optimizations/components/StageInfoModal.tsx",
  "src/features/sidebar/components/Sidebar.tsx",
  "src/features/submit/components/ModelConfigModal.tsx",
  "src/features/submit/components/ModelPicker.tsx",
  "src/features/submit/components/ModelProbeDialog.tsx",
  "src/features/submit/components/SplitRecommendationCard.tsx",
  "src/features/submit/components/SubmitNav.tsx",
  "src/features/submit/components/SubmitWizard.tsx",
  "src/features/submit/components/steps/BasicsStep.tsx",
  "src/features/submit/components/steps/CodeAgentPanel.tsx",
  "src/features/submit/components/steps/CodeStep.tsx",
  "src/features/submit/components/steps/DatasetStep.tsx",
  "src/features/submit/components/steps/ModelStep.tsx",
  "src/features/submit/components/steps/ParamsStep.tsx",
  "src/features/submit/components/steps/SummaryStep.tsx",
  "src/features/tagger/components/TaggerAnnotation.tsx",
  "src/features/tagger/components/TaggerSetup.tsx",
  "src/features/tutorial/components/tutorial-menu.tsx",
  "src/features/tutorial/components/tutorial-popover.tsx",
  "src/shared/charts/dataset-vs-improvement-chart.tsx",
  "src/shared/layout/app-shell.tsx",
  "src/shared/ui/agent/thinking-section.tsx",
  "src/shared/ui/agent/user-bubble.tsx",
  "src/shared/ui/code-editor.tsx",
  "src/shared/ui/excel-filter.tsx",
  "src/shared/ui/score-chart.tsx",
];

const canonicalTermLiteralSelectors = [
  "Literal[value=/אופטימיזציה|אופטימיזציות|דאטאסט|מודל רפלקציה|מודל מג׳נרט|מודל מג'נרט|אופטימייזר|אופטימייזרים|פונקציית מדידה/u]",
  "TemplateElement[value.raw=/אופטימיזציה|אופטימיזציות|דאטאסט|מודל רפלקציה|מודל מג׳נרט|מודל מג'נרט|אופטימייזר|אופטימייזרים|פונקציית מדידה/u]",
];

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // Existing React Compiler findings predate this i18n gate. Keep the new
    // `npm run lint` script focused on the Next/TS baseline plus literal-copy
    // enforcement; tighten these separately when those components are refactored.
    rules: {
      "react-hooks/immutability": "off",
      "react-hooks/preserve-manual-memoization": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/rules-of-hooks": "warn",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/static-components": "warn",
      "@next/next/no-html-link-for-pages": "warn",
      "prefer-const": "warn",
      "react/no-unescaped-entities": "warn",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [
      "src/shared/lib/messages.ts",
      "src/shared/lib/tooltips.ts",
      "src/shared/lib/terms.ts",
      "src/features/tutorial/lib/**",
      ...i18nLiteralBacklog,
    ],
    plugins: {
      i18next,
    },
    rules: {
      "i18next/no-literal-string": [
        "error",
        {
          framework: "react",
          mode: "jsx-text-only",
          message:
            "Move user-facing JSX text into src/shared/lib/messages.ts or src/shared/lib/terms.ts",
        },
      ],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [
      "src/shared/lib/messages.ts",
      "src/shared/lib/tooltips.ts",
      "src/shared/lib/terms.ts",
      "src/shared/lib/generated/**",
      "src/shared/constants/job-status.ts",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...canonicalTermLiteralSelectors.map((selector) => ({
          selector,
          message: "Canonical Hebrew domain terms must come from TERMS in src/shared/lib/terms.ts.",
        })),
      ],
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "node_modules/**"]),
]);
