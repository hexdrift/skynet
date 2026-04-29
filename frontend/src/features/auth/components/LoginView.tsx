"use client";

import { useEffect, useState } from "react";
import { signIn, getProviders } from "next-auth/react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/shared/ui/primitives/button";
import { Card, CardContent, CardHeader, CardDescription } from "@/shared/ui/primitives/card";
import { AnimatedWordmark } from "@/shared/ui/animated-wordmark";
import { Input } from "@/shared/ui/primitives/input";
import { Label } from "@/shared/ui/primitives/label";
import { Loader2 } from "lucide-react";
import { msg } from "@/shared/lib/messages";

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
          void signIn("adfs", { callbackUrl: "/" });
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
    // `window.location.href = "/"` did.
    router.push("/");
    router.refresh();
  };

  if (mode === "loading" || mode === "sso") {
    return (
      <div className="flex flex-col items-center justify-center min-h-dvh gap-4">
        <Loader2 className="size-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">{msg("auth.login.loading")}</p>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-dvh px-4">
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-[420px]"
      >
        <Card className="border-border/30 shadow-2xl shadow-black/8 backdrop-blur-xl bg-card/90 overflow-hidden">
          <CardHeader className="text-center pb-0 pt-10">
            <div className="flex justify-center" data-slot="card-title">
              <AnimatedWordmark size={32} />
            </div>
            <CardDescription className="text-muted-foreground/60 mt-2 text-[0.8125rem] tracking-wide">
              {msg("auth.login.tagline")}
            </CardDescription>
          </CardHeader>

          <CardContent className="px-6 sm:px-8 pb-5 pt-0">
            <form
              onSubmit={handleLogin}
              className="space-y-5"
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
                  className="h-11 bg-background/60 border-border/50 focus:border-primary/40 focus:ring-primary/20 transition-all duration-200 placeholder:text-muted-foreground/40 placeholder:text-right"
                />
              </div>

              <AnimatePresence>
                {error && (
                  <motion.p
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="text-sm text-destructive text-center"
                    role="alert"
                  >
                    {error}
                  </motion.p>
                )}
              </AnimatePresence>

              <Button
                type="submit"
                className="w-full h-11 text-[0.9375rem] font-medium gap-2 transition-all duration-200"
                size="lg"
                disabled={loading || !username.trim()}
              >
                {loading && <Loader2 className="size-4 animate-spin" />}
                {msg("auth.login.submit")}
              </Button>
            </form>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
