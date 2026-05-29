/**
 * Returns true when the generalist agent panel should mount. The flag
 * is read from `NEXT_PUBLIC_FEATURE_GENERALIST_AGENT` with values
 * `"1" | "true" | "on"` to enable, `"0" | "false" | "off" | "no"` to
 * disable. When unset the default is ON in both dev and prod so the
 * panel ships enabled.
 *
 * Intentionally kept as `NEXT_PUBLIC_*` (not promoted to the runtime-env
 * shim): this flag is a build-time decision about which features ship in
 * a given image, not a runtime knob to flip per pod. Backend-pointing
 * config like `API_URL` lives in `@/shared/lib/runtime-env` instead.
 */
export function isGeneralistAgentEnabled(): boolean {
  const raw = process.env.NEXT_PUBLIC_FEATURE_GENERALIST_AGENT;
  if (raw === undefined || raw === "") return true;
  const v = raw.toLowerCase().trim();
  return v === "1" || v === "true" || v === "on" || v === "yes";
}
