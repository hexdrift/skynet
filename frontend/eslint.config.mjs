import { defineConfig, globalIgnores } from "eslint/config";
import i18next from "eslint-plugin-i18next";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const canonicalTermLiteralSelectors = [
  "Literal[value=/אופטימיזציה|אופטימיזציות|דאטאסט|מודל רפלקציה|מודל מג׳נרט|מודל מג'נרט|אופטימייזר|אופטימייזרים|פונקציית מדידה/u]",
  "TemplateElement[value.raw=/אופטימיזציה|אופטימיזציות|דאטאסט|מודל רפלקציה|מודל מג׳נרט|מודל מג'נרט|אופטימייזר|אופטימייזרים|פונקציית מדידה/u]",
];

const hebrewLiteralSelectors = ["Literal[value=/[א-ת]/u]", "TemplateElement[value.raw=/[א-ת]/u]"];

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/array-type": ["error", { default: "array-simple" }],
      "@typescript-eslint/consistent-indexed-object-style": ["error", "record"],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        {
          disallowTypeAnnotations: true,
          fixStyle: "separate-type-imports",
          prefer: "type-imports",
        },
      ],
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-inferrable-types": "error",
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "@/features/*/components/*",
                "@/features/*/hooks/*",
                "@/features/*/lib/*",
                "@/features/*/constants",
              ],
              message:
                "Import feature internals with relative paths inside the same feature, or import from the feature public API.",
            },
          ],
        },
      ],
      "object-shorthand": "error",
      "prefer-template": "error",
    },
  },
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
        ...hebrewLiteralSelectors.map((selector) => ({
          selector,
          message:
            "Hebrew literals must live in src/shared/lib/messages.ts, tooltips.ts, or terms.ts.",
        })),
        ...canonicalTermLiteralSelectors.map((selector) => ({
          selector,
          message: "Canonical Hebrew domain terms must come from TERMS in src/shared/lib/terms.ts.",
        })),
      ],
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "node_modules/**"]),
]);
