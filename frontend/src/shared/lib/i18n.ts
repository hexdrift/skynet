import {
  I18N_MESSAGES,
  TERMS,
  type I18nMessageKey,
  type TermKey,
} from "@/shared/lib/generated/i18n-catalog";

export { I18N_MESSAGES, I18N_KEY, type I18nMessageKey } from "@/shared/lib/generated/i18n-catalog";

const TERM_PATTERN = /\{term\.([A-Za-z0-9_]+)\}/g;
const PARAM_PATTERN = /\{([A-Za-z0-9_]+)\}/g;

function resolveTerms(template: string): string {
  return template.replace(TERM_PATTERN, (match, key: string) => {
    const value = (TERMS as Record<string, string>)[key as TermKey];
    return value ?? match;
  });
}

/**
 * Resolve a backend i18n code like `"optimization.not_found"` into the
 * Hebrew user-facing string, substituting `{term.xxx}` tokens against
 * `TERMS` and `{param}` tokens against the caller-supplied params.
 *
 * Returns the key itself when missing so catalog drift surfaces as a
 * visible dev artifact.
 */
export function tI18n(code: string, params?: Record<string, unknown>): string {
  const template = (I18N_MESSAGES as Record<string, string>)[code as I18nMessageKey];
  if (!template) return code;
  const resolved = resolveTerms(template);
  if (!params) return resolved;
  return resolved.replace(PARAM_PATTERN, (match, key: string) => {
    if (!(key in params)) return match;
    const value = params[key];
    return value == null ? match : String(value);
  });
}
