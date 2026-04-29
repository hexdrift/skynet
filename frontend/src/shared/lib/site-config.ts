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
  return process.env.NEXT_PUBLIC_SITE_URL ?? FALLBACK_SITE_URL;
}
