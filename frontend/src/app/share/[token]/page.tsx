"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Loader2, Share2, User } from "lucide-react";

import { OptimizationDetailView } from "@/features/optimizations";
import { getSharedOptimization, type SharedOptimizationData } from "@/shared/lib/api";
import { formatMsg, msg } from "@/shared/lib/messages";

type ShareState =
  | { status: "loading" }
  | { status: "ok"; data: SharedOptimizationData }
  | { status: "error" };

/**
 * Public, login-free read-only view of a shared optimization. Resolves the
 * token via the unauthenticated ``/share/{token}`` endpoint and renders the
 * standard detail view in read-only mode (owner actions hidden, no fetches).
 */
export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const [state, setState] = useState<ShareState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    getSharedOptimization(token)
      .then((data) => {
        if (!cancelled) setState({ status: "ok", data });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (state.status === "loading") {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="size-8 animate-spin text-primary" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-3 px-6 text-center">
        <h1 className="text-lg font-semibold">{msg("share.not_found_title")}</h1>
        <p className="text-sm text-muted-foreground">{msg("share.not_found_body")}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-border/50 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        <Share2 className="size-3.5 shrink-0" aria-hidden="true" />
        <span>{msg("share.public_banner")}</span>
        <span aria-hidden="true" className="opacity-40">·</span>
        <User className="size-3.5 shrink-0" aria-hidden="true" />
        <span dir="auto">
          {state.data.owner
            ? formatMsg("share.banner_shared_by", { name: state.data.owner })
            : msg("share.banner_anonymous")}
        </span>
      </div>
      <Suspense fallback={null}>
        <OptimizationDetailView shareData={state.data} />
      </Suspense>
    </div>
  );
}
