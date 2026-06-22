"use client";

import { memo } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { StatusBadge } from "@/shared/ui/status-badge";
import { HALO_CARDS } from "../login-samples";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;

/**
 * The scattered "product halo" behind the login panel: fake finished-run cards
 * — built from the real `StatusBadge` so they read like Skynet's own UI — each
 * just a success pill + task name, no scores. Cards settle in once, then drift
 * gently and forever, and scale up under the pointer (the layer is
 * pointer-transparent; each card re-enables hover for itself). Decorative only
 * — hidden from assistive tech — and clipped so they bleed off the edges.
 *
 * Positioning sits on a plain wrapper and rotation is animated numerically, so
 * framer-motion only ever touches transform/opacity — never the positional
 * unit-conversion path (`positionalValues[name]`) that throws on re-render. The
 * whole layer is memoized (it has no props) so typing in the form never
 * re-renders these 23 animated nodes.
 */
function LoginHaloImpl() {
  const reduce = useReducedMotion();

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      {HALO_CARDS.map((card, i) => {
        // Index-derived so the drift desyncs per card without Math.random (which
        // would break SSR hydration). Small amplitudes — a slow, quiet float.
        const amp = 4 + (i % 3) * 2;
        const xamp = i % 2 === 0 ? 3 : -3;
        const wob = i % 2 === 0 ? 0.8 : -0.8;
        const dur = 5 + (i % 6);
        const fdelay = (i % 5) * 0.5;

        return (
          <div key={i} className={card.mobile ? "absolute" : "absolute hidden md:block"} style={card.pos}>
            <motion.div
              className="pointer-events-auto cursor-default"
              initial={reduce ? { opacity: 1 } : { opacity: 0, scale: 0.9, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={
                reduce
                  ? { duration: 0 }
                  : { duration: 0.7, delay: 0.15 + i * 0.03, ease: EASE_OUT_EXPO }
              }
            >
              <motion.div
                dir="rtl"
                className="flex w-max max-w-[14rem] items-center gap-1.5 rounded-xl border border-border/50 bg-card px-3 py-2 shadow-[0_8px_24px_-14px_rgba(28,22,18,0.28)]"
                animate={
                  reduce
                    ? { rotate: card.rot }
                    : {
                        y: [0, -amp, 0],
                        x: [0, xamp, 0],
                        rotate: [card.rot, card.rot + wob, card.rot],
                      }
                }
                transition={
                  reduce
                    ? { duration: 0 }
                    : {
                        y: { duration: dur, repeat: Infinity, ease: "easeInOut", delay: fdelay },
                        x: { duration: dur * 1.5, repeat: Infinity, ease: "easeInOut", delay: fdelay * 0.6 },
                        rotate: { duration: dur * 1.25, repeat: Infinity, ease: "easeInOut", delay: fdelay },
                      }
                }
                whileHover={
                  reduce ? undefined : { scale: 1.1, transition: { duration: 0.35, ease: EASE_OUT_EXPO } }
                }
              >
                <StatusBadge status="success" compact className="px-2 py-0.5 text-[0.6rem]" />
                <span className="truncate text-[0.72rem] font-medium text-foreground/85">
                  {card.title}
                </span>
              </motion.div>
            </motion.div>
          </div>
        );
      })}
    </div>
  );
}

export const LoginHalo = memo(LoginHaloImpl);
