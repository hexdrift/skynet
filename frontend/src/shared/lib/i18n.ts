import {
  I18N_MESSAGES,
  TERMS,
  type I18nMessageKey,
  type TermKey,
} from "@/shared/lib/generated/i18n-catalog";

export {
  I18N_MESSAGES,
  I18N_KEY,
  type ErrorCode,
  type I18nMessageKey,
} from "@/shared/lib/generated/i18n-catalog";

const TERM_PATTERN = /\{term\.([A-Za-z0-9_]+)\}/g;

const FSI = "⁨";
const PDI = "⁩";
const LATIN_LIKE = /[A-Za-z0-9@./:_\-+#]/;

function reportMissingKey(key: string): void {
  if (typeof console !== "undefined" && typeof console.warn === "function") {
    console.warn(`[i18n] missing translation for ${key}`);
  }
}

function isolate(value: unknown): string {
  const str = String(value);
  // Wrap Latin-script / numeric values in FSI/PDI so the BiDi algorithm
  // doesn't flip surrounding Hebrew punctuation. Pure-Hebrew payloads are
  // left alone to keep snapshot diffs noise-free.
  if (LATIN_LIKE.test(str)) return `${FSI}${str}${PDI}`;
  return str;
}

function resolveTerms(template: string): string {
  return template.replace(TERM_PATTERN, (match, key: string) => {
    const value = (TERMS as Record<string, string>)[key as TermKey];
    return value ?? match;
  });
}

function findMatchingBrace(source: string, start: number): number {
  let depth = 0;
  for (let i = start; i < source.length; i++) {
    const ch = source.charAt(i);
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function parseBranches(body: string): Record<string, string> {
  const branches: Record<string, string> = {};
  let i = 0;
  while (i < body.length) {
    while (i < body.length && /\s/.test(body.charAt(i))) i++;
    const nameStart = i;
    while (i < body.length && /[\w=]/.test(body.charAt(i))) i++;
    const name = body.slice(nameStart, i);
    while (i < body.length && /\s/.test(body.charAt(i))) i++;
    if (body.charAt(i) !== "{") break;
    const close = findMatchingBrace(body, i);
    if (close === -1) break;
    branches[name] = body.slice(i + 1, close);
    i = close + 1;
  }
  return branches;
}

function pickPluralCategory(count: number): Intl.LDMLPluralRule {
  try {
    return new Intl.PluralRules("he").select(count);
  } catch {
    return count === 1 ? "one" : "other";
  }
}

function resolveSubstitutions(
  template: string,
  params: Record<string, unknown>,
): string {
  let out = "";
  let i = 0;
  while (i < template.length) {
    const ch = template.charAt(i);
    if (ch !== "{") {
      out += ch;
      i++;
      continue;
    }
    const close = findMatchingBrace(template, i);
    if (close === -1) {
      out += ch;
      i++;
      continue;
    }
    const inner = template.slice(i + 1, close);
    const pluralMatch = /^(\w+)\s*,\s*plural\s*,\s*([\s\S]+)$/.exec(inner);
    if (pluralMatch && pluralMatch[1] && pluralMatch[2]) {
      const name = pluralMatch[1];
      const branchesStr = pluralMatch[2];
      const raw = params[name];
      const count = typeof raw === "number" ? raw : Number(raw);
      if (!Number.isFinite(count)) {
        out += template.slice(i, close + 1);
      } else {
        const branches = parseBranches(branchesStr);
        const exact = `=${count}`;
        const category = pickPluralCategory(count);
        const body =
          branches[exact] ??
          branches[category] ??
          branches.other ??
          "";
        out += resolveSubstitutions(
          body.replace(/#/g, isolate(count)),
          params,
        );
      }
    } else if (/^[A-Za-z0-9_]+$/.test(inner)) {
      if (inner in params) {
        const value = params[inner];
        out += value == null ? template.slice(i, close + 1) : isolate(value);
      } else {
        out += template.slice(i, close + 1);
      }
    } else {
      out += template.slice(i, close + 1);
    }
    i = close + 1;
  }
  return out;
}

/**
 * Render a template string with ICU plurals and BiDi-isolated interpolation.
 * Used by both ``tI18n`` and ``formatMsg`` so backend codes and frontend
 * UI strings share identical formatting semantics.
 */
export function formatTemplate(
  template: string,
  params: Record<string, unknown> | undefined,
): string {
  const resolved = resolveTerms(template);
  if (!params) return resolved;
  return resolveSubstitutions(resolved, params);
}

/**
 * Resolve a backend i18n code into Hebrew, with `{term.x}` term lookups,
 * ICU plural support (`{count, plural, one {} two {} other {}}`), and
 * BiDi isolation around every interpolated value so embedded Latin/numeric
 * values don't flip surrounding Hebrew punctuation.
 *
 * Returns the key unchanged so drift is dev-visible.
 */
export function tI18n(code: string, params?: Record<string, unknown>): string {
  const template = (I18N_MESSAGES as Record<string, string>)[code as I18nMessageKey];
  if (!template) {
    reportMissingKey(code);
    return code;
  }
  return formatTemplate(template, params);
}
