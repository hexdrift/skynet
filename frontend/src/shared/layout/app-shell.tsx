"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Menu, LogOut, GraduationCap, BookOpen } from "lucide-react";
import { useSession, signOut } from "next-auth/react";
import { AnimatedWordmark } from "@/shared/ui/animated-wordmark";
import { useTutorialContext } from "@/features/tutorial";
import { useUserPrefs } from "@/features/settings";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import { ParticleHero } from "@/shared/ui/particle-hero";
import {
  GeneralistPanel,
  GeneralistPanelProvider,
  WizardStateProvider,
  isGeneralistAgentEnabled,
} from "@/features/agent-panel";

const Sidebar = dynamic(() => import("@/features/sidebar").then((m) => m.Sidebar), { ssr: false });

const HEADER_HEIGHT_PX = 53;
const SIDEBAR_ID = "app-sidebar";
const DESKTOP_BP = "(min-width: 768px)";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login") {
    return (
      <div className="flex min-h-screen flex-col relative">
        <ParticleHero />
        <main className="flex-1 relative z-[1]" dir="rtl">
          {children}
        </main>
      </div>
    );
  }

  return <ShellChrome>{children}</ShellChrome>;
}

function ShellChrome({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [isDesktop, setIsDesktop] = React.useState(false);
  const { data: session } = useSession();
  const pathname = usePathname();
  const { startDeepDive } = useTutorialContext();
  const { prefs } = useUserPrefs();
  const generalistEnabled = isGeneralistAgentEnabled();
  const scalarDocsUrl = React.useMemo(() => `${getRuntimeEnv().apiUrl}/scalar`, []);
  const progressRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSidebarOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  React.useEffect(() => {
    const mq = window.matchMedia(DESKTOP_BP);
    const update = () => setIsDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  React.useEffect(() => {
    const el = progressRef.current;
    if (!el) return;
    const onScroll = () => {
      const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      const scrollHeight =
        document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const progress = scrollHeight > 0 ? scrollTop / scrollHeight : 0;
      el.style.setProperty("--scroll-progress", String(Math.min(progress, 1)));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const sidebarHidden = !isDesktop && !sidebarOpen;

  const shell = (
    <div
      className="flex min-h-screen flex-col"
      style={{ ["--header-height" as string]: `${HEADER_HEIGHT_PX}px` }}
    >
      <div ref={progressRef} className="scroll-progress" aria-hidden="true" />

      <div className="ambient-bg" aria-hidden="true">
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div className="orb orb-3" />
        <div className="orb orb-4" />
      </div>

      <motion.header
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="sticky top-0 z-30 flex items-center justify-between bg-background/60 backdrop-blur-2xl backdrop-saturate-[1.8] px-4 py-2.5 border-b border-border/40 shadow-[0_1px_3px_rgba(0,0,0,0.04),0_4px_12px_rgba(0,0,0,0.03)]"
        dir="ltr"
        style={{
          borderImage:
            "linear-gradient(to right, transparent, var(--border) 20%, var(--border) 80%, transparent) 1",
        }}
      >
        <div className="flex items-center gap-1.5 cursor-default">
          <div className="hidden sm:block">
            <AnimatedWordmark size={16} />
          </div>
          <span
            className="sm:hidden text-sm font-bold tracking-[0.14em] uppercase text-foreground cursor-default"
            style={{ fontFamily: '"Inter Variable", system-ui, sans-serif' }}
          >
            SKYNET
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={startDeepDive}
                className="rounded-lg p-1.5 hover:bg-accent/80 active:scale-95 transition-all duration-200 cursor-pointer text-muted-foreground hover:text-foreground inline-flex items-center justify-center"
                aria-label={msg("app.shell.tour_aria")}
              >
                <GraduationCap className="size-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" dir="rtl">
              {msg("app.shell.tour_tooltip")}
            </TooltipContent>
          </Tooltip>
          {prefs.advancedMode && (
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href={scalarDocsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-lg p-1.5 hover:bg-accent/80 active:scale-95 transition-all duration-200 cursor-pointer text-muted-foreground hover:text-foreground inline-flex items-center justify-center"
                  aria-label={msg("app.shell.api_docs_aria")}
                >
                  <BookOpen className="size-4" />
                </a>
              </TooltipTrigger>
              <TooltipContent side="bottom" dir="rtl">
                {msg("app.shell.api_docs_tooltip")}
              </TooltipContent>
            </Tooltip>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {session?.user && (
            <>
              <span className="hidden sm:inline text-xs text-muted-foreground">
                {session.user.name ?? session.user.email}
              </span>
              <button
                type="button"
                onClick={() => signOut({ callbackUrl: "/login" })}
                className="rounded-lg p-2 hover:bg-accent/80 active:scale-95 transition-all duration-200 cursor-pointer hidden sm:block"
                aria-label={msg("app.shell.logout")}
                title={msg("app.shell.logout")}
              >
                <LogOut className="size-4" />
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-2 hover:bg-accent/80 active:scale-95 transition-all duration-200 md:hidden"
            aria-label={msg("app.shell.menu")}
            aria-expanded={sidebarOpen}
            aria-controls={SIDEBAR_ID}
          >
            <Menu className="size-5" />
          </button>
        </div>
      </motion.header>

      <div className="flex flex-1" dir="ltr">
        <button
          type="button"
          aria-label={msg("app.shell.menu_close")}
          onClick={() => setSidebarOpen(false)}
          className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden transition-all duration-300 ease-out ${sidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none"}`}
          tabIndex={sidebarOpen ? 0 : -1}
          aria-hidden={!sidebarOpen}
        />

        <main className="flex-1 overflow-auto min-w-0 page-gradient grid-pattern" dir="rtl">
          <div
            className="relative z-[1] mx-auto max-w-7xl py-6 md:py-8"
            style={{ paddingInline: "clamp(1rem, 5vw - 0.5rem, 2rem)" }}
          >
            {children}
          </div>
        </main>

        <div
          id={SIDEBAR_ID}
          className={`fixed inset-y-0 right-0 z-50 transform transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] md:sticky md:inset-auto md:top-[var(--header-height)] md:self-start md:h-[calc(100dvh-var(--header-height))] md:z-10 md:translate-x-0 md:shadow-none ${sidebarOpen ? "translate-x-0" : "translate-x-full"}`}
          aria-hidden={sidebarHidden ? true : undefined}
        >
          <Sidebar />
        </div>
      </div>
    </div>
  );

  if (!generalistEnabled) return shell;

  return (
    <WizardStateProvider>
      <GeneralistPanelProvider>
        {shell}
        <GeneralistPanel />
      </GeneralistPanelProvider>
    </WizardStateProvider>
  );
}
