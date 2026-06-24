/**
 * Single source of truth for the public site URL used in metadata, OG tags,
 * the JSON-LD payload, robots.txt, and sitemap.xml.
 *
 * The on-prem deploy is air-gapped, so the public `https://skynet.app`
 * default would otherwise leak into customer-facing canonical/OG URLs and
 * sitemap entries when `NEXT_PUBLIC_SITE_URL` is unset. Centralising the
 * lookup here keeps a future "fail-closed when unset in production" tweak
 * to one place.
 */
const FALLBACK_SITE_URL = "https://skynet.app";

export function getSiteUrl(): string {
  // An unset Docker build ARG arrives as "" (not undefined), so `??` would let
  // it through and `new URL("")` in the metadata layer throws ERR_INVALID_URL.
  // Treat empty/whitespace as unset so the build falls back instead of crashing.
  const value = process.env.NEXT_PUBLIC_SITE_URL;
  return value && value.trim() ? value : FALLBACK_SITE_URL;
}
