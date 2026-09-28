/** Device detection selects navigation chrome, never route or settings access. */
export type DeviceClass = "phone" | "desktop";

export const PHONE_MEDIA_QUERY = "(max-width: 767px)";

/**
 * First-paint device class from request headers.
 *
 * `Sec-CH-UA-Mobile` (`?1` = phone) is authoritative when present; otherwise a
 * `Mobile`/`Mobi` UA token minus iPad (tablets land at desktop widths anyway).
 * The client re-derives from `matchMedia` after mount, so this only has to be
 * right often enough to avoid a shell swap on the common phone paths.
 */
export function deviceClassFromRequest(
  userAgent: string | null,
  secChUaMobile: string | null,
): DeviceClass {
  if (secChUaMobile !== null) return secChUaMobile.trim() === "?1" ? "phone" : "desktop";
  if (!userAgent || /\biPad\b/i.test(userAgent)) return "desktop";
  return /\bMobi(le)?\b/i.test(userAgent) ? "phone" : "desktop";
}
