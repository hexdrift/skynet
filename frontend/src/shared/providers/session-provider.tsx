"use client";

import { SessionProvider as NextAuthSessionProvider } from "next-auth/react";
import type { ComponentProps } from "react";

type SessionProviderProps = ComponentProps<typeof NextAuthSessionProvider>;

export function SessionProvider(props: SessionProviderProps) {
  return <NextAuthSessionProvider {...props} />;
}
