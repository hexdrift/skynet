"use client";

import { useEffect, useState } from "react";
import { signIn, getProviders } from "next-auth/react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardDescription } from "@/components/ui/card";
import { AnimatedWordmark } from "@/shared/ui/animated-wordmark";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2 } from "lucide-react";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"sso" | "dev">("dev");

  useEffect(() => {
    getProviders().then((providers) => {
      if (providers?.adfs) {
        setMode("sso");
        signIn("adfs", { callbackUrl: "/" });
      }
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
      setError("שגיאה בהתחברות");
    } else {
      window.location.href = "/";
    }
  };

  if (mode === "sso") {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <Loader2 className=" size-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">מתחבר...</p>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen px-4">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.2, 0.8, 0.2, 1] }}
        className="w-full max-w-[440px]"
      >
        <Card className="border-border/40 shadow-2xl backdrop-blur-xl bg-card/80 relative overflow-hidden">
          <CardHeader className="text-center pb-0 pt-8 relative">
            <div className="flex justify-center" data-slot="card-title">
              <AnimatedWordmark size={28} />
            </div>
            <CardDescription className="text-muted-foreground/70 mt-1 text-[13px]">
              מערכת אופטימיזציית פרומפטים
            </CardDescription>
          </CardHeader>

          <CardContent className="relative px-8 pb-8 pt-6">
            <form onSubmit={handleLogin} className="space-y-4" aria-label="טופס התחברות">
              <div className="space-y-1.5">
                <Label
                  htmlFor="login-username"
                  className="text-[13px] font-medium text-muted-foreground"
                >
                  שם משתמש
                </Label>
                <Input
                  id="login-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="הזן שם משתמש"
                  autoFocus
                  dir="rtl"
                  className="h-11 bg-background/50 border-border/60 transition-colors duration-300"
                />
              </div>
              {error && (
                <motion.p
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-sm text-red-500"
                >
                  {error}
                </motion.p>
              )}
              <Button
                type="submit"
                className="w-full h-11 text-base mt-2"
                size="lg"
                disabled={loading || !username.trim()}
              >
                {loading && <Loader2 className="size-4 animate-spin" />}
                התחבר
              </Button>
            </form>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
