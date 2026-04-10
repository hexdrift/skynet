"use client";

import { useEffect, useRef, useCallback } from "react";

/**
 * Subtle particle animation for the login page hero background.
 * Warm-palette floating nodes with connecting lines on desktop.
 * Respects prefers-reduced-motion and pauses when tab is hidden.
 */

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  color: string;
  alpha: number;
}

const COLORS = [
  "200, 168, 130", // #C8A882
  "166, 139, 107", // #A68B6B
  "124, 99, 80",   // #7C6350
  "139, 117, 96",  // #8B7560
];

const DPR_CAP = 2;

function drawStaticDots(canvas: HTMLCanvasElement, particles: Particle[]) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const dpr = Math.min(window.devicePixelRatio, DPR_CAP);
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  particles.forEach((p) => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${p.color}, ${p.alpha})`;
    ctx.fill();
  });
}

export function ParticleHero({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef(0);
  const particlesRef = useRef<Particle[]>([]);
  const pausedRef = useRef(false);

  const initParticles = useCallback((w: number, h: number) => {
    const isMobile = w < 768;
    const count = isMobile ? 15 : 35;
    const particles: Particle[] = [];

    for (let i = 0; i < count; i++) {
      const speed = isMobile ? 0.15 : 0.25;
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * speed,
        vy: (Math.random() - 0.5) * speed,
        radius: Math.random() * 2 + 1,
        color: COLORS[Math.floor(Math.random() * COLORS.length)]!,
        alpha: Math.random() * 0.3 + 0.15,
      });
    }
    particlesRef.current = particles;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");

    // Reduced-motion: static dots with resize support
    if (mql.matches) {
      const rect = canvas.getBoundingClientRect();
      initParticles(rect.width, rect.height);
      drawStaticDots(canvas, particlesRef.current);

      const ro = new ResizeObserver(() => {
        const r = canvas.getBoundingClientRect();
        initParticles(r.width, r.height);
        drawStaticDots(canvas, particlesRef.current);
      });
      ro.observe(canvas);
      return () => ro.disconnect();
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w = 0;
    let h = 0;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio, DPR_CAP);
      w = rect.width;
      h = rect.height;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      // Reset transform before applying new scale to prevent accumulation
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (particlesRef.current.length === 0) {
        initParticles(w, h);
      }
    };

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();

    const isMobile = window.innerWidth < 768;
    const maxLineDistance = isMobile ? 0 : 120;

    const draw = () => {
      if (pausedRef.current) {
        animRef.current = requestAnimationFrame(draw);
        return;
      }

      ctx.clearRect(0, 0, w, h);
      const particles = particlesRef.current;

      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -10) p.x = w + 10;
        if (p.x > w + 10) p.x = -10;
        if (p.y < -10) p.y = h + 10;
        if (p.y > h + 10) p.y = -10;
      }

      if (maxLineDistance > 0) {
        for (let i = 0; i < particles.length; i++) {
          const pi = particles[i]!;
          for (let j = i + 1; j < particles.length; j++) {
            const pj = particles[j]!;
            const dx = pi.x - pj.x;
            const dy = pi.y - pj.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < maxLineDistance) {
              const alpha = (1 - dist / maxLineDistance) * 0.08;
              ctx.beginPath();
              ctx.moveTo(pi.x, pi.y);
              ctx.lineTo(pj.x, pj.y);
              ctx.strokeStyle = `rgba(200, 168, 130, ${alpha})`;
              ctx.lineWidth = 0.5;
              ctx.stroke();
            }
          }
        }
      }

      for (const p of particles) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${p.color}, ${p.alpha})`;
        ctx.fill();
      }

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);

    const handleVisibility = () => {
      pausedRef.current = document.hidden;
    };
    document.addEventListener("visibilitychange", handleVisibility);

    // Stop animation and draw static dots if reduced-motion changes
    const handleMotionChange = (e: MediaQueryListEvent) => {
      if (e.matches) {
        cancelAnimationFrame(animRef.current);
        drawStaticDots(canvas, particlesRef.current);
      }
    };
    mql.addEventListener("change", handleMotionChange);

    return () => {
      cancelAnimationFrame(animRef.current);
      ro.disconnect();
      document.removeEventListener("visibilitychange", handleVisibility);
      mql.removeEventListener("change", handleMotionChange);
    };
  }, [initParticles]);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 size-full ${className ?? ""}`}
      aria-hidden="true"
      style={{ pointerEvents: "none" }}
    />
  );
}
