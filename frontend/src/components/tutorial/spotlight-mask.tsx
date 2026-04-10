"use client";

import { motion } from "framer-motion";
import * as React from "react";

interface SpotlightMaskProps {
  targetRect: DOMRect | null;
  padding?: number;
  borderRadius?: number;
}

const spring = { type: "spring", stiffness: 400, damping: 35, mass: 0.8 } as const;

export function SpotlightMask({ targetRect, padding = 8, borderRadius = 12 }: SpotlightMaskProps) {
  if (!targetRect) {
    return (
      <svg className="absolute inset-0 w-full h-full pointer-events-auto">
        <rect x="0" y="0" width="100%" height="100%" fill="rgba(28,22,18,0.50)" />
      </svg>
    );
  }

  const x = targetRect.x - padding;
  const y = targetRect.y - padding;
  const w = targetRect.width + padding * 2;
  const h = targetRect.height + padding * 2;

  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-auto">
      <defs>
        <mask id="tutorial-spotlight-mask">
          <rect x="0" y="0" width="100%" height="100%" fill="white" />
          <motion.rect
            animate={{ x, y, width: w, height: h }}
            transition={spring}
            rx={borderRadius}
            fill="black"
          />
        </mask>
      </defs>

      <rect
        x="0" y="0" width="100%" height="100%"
        fill="rgba(28,22,18,0.50)"
        mask="url(#tutorial-spotlight-mask)"
      />

      {/* Border */}
      <motion.rect
        animate={{ x, y, width: w, height: h }}
        transition={spring}
        rx={borderRadius}
        fill="none" stroke="rgba(229,221,212,0.35)" strokeWidth="1.5"
      />

      {/* Glow */}
      <motion.rect
        animate={{ x, y, width: w, height: h, opacity: [0.3, 0.5, 0.3] }}
        transition={{
          ...spring,
          opacity: { duration: 2.5, repeat: Infinity, ease: "easeInOut" },
        }}
        rx={borderRadius}
        fill="none" stroke="rgba(229,221,212,0.2)" strokeWidth="3" filter="blur(4px)"
      />
    </svg>
  );
}
