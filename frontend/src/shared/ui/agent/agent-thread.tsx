"use client";

import * as React from "react";

import { cn } from "@/shared/lib/utils";

interface AgentThreadProps {
  children: React.ReactNode;
  scrollDeps?: readonly unknown[];
  emptyState?: React.ReactNode;
  isEmpty?: boolean;
  className?: string;
}

export function AgentThread({
  children,
  scrollDeps = [],
  emptyState,
  isEmpty,
  className,
}: AgentThreadProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    // deps intentionally dynamic — the caller owns the trigger set
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, scrollDeps);

  return (
    <div
      ref={scrollRef}
      className={cn("flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-5", className)}
    >
      {isEmpty && emptyState}
      {children}
    </div>
  );
}
