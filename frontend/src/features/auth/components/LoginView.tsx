"use client";

import { useEffect, useState } from "react";
import { signIn, getProviders } from "next-auth/react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2 } from "lucide-react";
import { Button } from "@/shared/ui/primitives/button";
import { Card, CardContent } from "@/shared/ui/primitives/card";
import { Input } from "@/shared/ui/primitives/input";
import { Label } from "@/shared/ui/primitives/label";
import { AnimatedWordmark } from "@/shared/ui/animated-wordmark";
import { msg } from "@/shared/lib/messages";
import { LoginHalo } from "./LoginHalo";

const ENTER_EASE = [0.16, 1, 0.3, 1] as const;

/**
 * Resolve where to send the user after login. next-auth's middleware appends a
 * ``callbackUrl`` query param when it bounces an unauthenticated request (e.g. a
 * ``/share/<token>`` link) to /login; honor it so the recipient lands back on
 * the page they came for. Only same-origin internal paths are accepted, so a
 * crafted ``callbackUrl`` can't turn login into an open redirect. Falls back to
 * the dashboard.
 */
function postLoginTarget(): string {
  if (typeof window === "undefined") return "/";
  const cb = new URLSearchParams(window.location.search).get("callbackUrl");
  if (!cb) return "/";
  try {
    const url = new URL(cb, window.location.origin);
    if (url.origin === window.location.origin) return url.pathname + url.search + url.hash;
  } catch {
    // Malformed callbackUrl — ignore and use the default.
  }
  return "/";
}

/**
 * Oversized SKYNET wordmark shared by every login state, so the SSO redirect
 * moment and the dev form read as the same place. It fills the column width and
 * morphs continuously as an ambient "alive" signal.
 */
function LoginHeader() {
  return (
    <div className="w-[min(90vw,520px)]">
      <AnimatedWordmark fluid autoMorph morphSpeed={250} />
    </div>
  );
}

export function LoginView() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"loading" | "sso" | "dev">("loading");

  useEffect(() => {
    // If the providers endpoint errors (network blip, mis-deployed
    // [...nextauth] route), fall back to the dev form instead of leaving the
    // page on the loading spinner forever.
    void getProviders()
      .then((providers) => {
        if (providers?.adfs) {
          setMode("sso");
          void signIn("adfs", { callbackUrl: postLoginTarget() });
        } else {
          setMode("dev");
        }
      })
      .catch((err) => {
        console.warn("LoginView: getProviders failed", err);
        setMode("dev");
      });
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) return;
    setError("");
    setLoading(true);
    const result = await signIn("credentials", {
      username: username.trim(),
      redirect: false,
    });
    setLoading(false);
    if (result?.error) {
      setError(msg("auth.login.error"));
      return;
    }
    // Soft-nav so we don't hard-reload and double-fetch the dashboard the way
    // `window.location.href = "/"` did. Honor the post-login target so a
    // recipient bounced here from a /share/<token> link lands back on it.
    router.push(postLoginTarget());
    router.refresh();
  };

  const isWorking = mode === "loading" || mode === "sso";

  return (
    <div className="relative flex min-h-dvh w-full items-center justify-center px-4 py-10">
      <LoginHalo />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-[1]"
        style={{
          background:
            "radial-gradient(58% 48% at 50% 44%, rgba(250,248,245,0.9) 0%, rgba(250,248,245,0.4) 46%, transparent 76%)",
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 18, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: ENTER_EASE }}
        className="relative z-10 w-full max-w-[420px]"
      >
        {isWorking ? (
          <div className="flex flex-col items-center">
            <LoginHeader />
            <div className="mt-9 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              <span>{msg("auth.login.loading")}</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center">
            <LoginHeader />
            <Card className="mt-9 w-full">
              <CardContent className="px-6">
                <form
                  onSubmit={handleLogin}
                  className="space-y-4"
                  aria-label={msg("auth.login.form_aria")}
                >
                  <div>
                    <Label htmlFor="login-username" className="sr-only">
                      {msg("auth.login.username")}
                    </Label>
                    <Input
                      id="login-username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder={msg("auth.login.username_placeholder")}
                      autoFocus
                      autoComplete="username"
                      dir="auto"
                      className="h-11 placeholder:text-right"
                    />
                  </div>

                  <AnimatePresence>
                    {error && (
                      <motion.p
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.2 }}
                        className="text-center text-sm text-destructive"
                        role="alert"
                      >
                        {error}
                      </motion.p>
                    )}
                  </AnimatePresence>

                  <Button
                    type="submit"
                    size="lg"
                    disabled={loading || !username.trim()}
                    className="h-11 w-full gap-2 text-[0.9375rem] font-medium"
                  >
                    {loading && <Loader2 className="size-4 animate-spin" />}
                    {msg("auth.login.submit")}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        )}
      </motion.div>
    </div>
  );
}
