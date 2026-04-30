"use client";

import { SessionProvider as NextAuthSessionProvider, useSession } from "next-auth/react";
import type { ComponentProps } from "react";
import * as React from "react";
import { setApiAuthToken } from "@/shared/lib/api";

type SessionProviderProps = ComponentProps<typeof NextAuthSessionProvider>;

export function SessionProvider(props: SessionProviderProps) {
  return (
    <NextAuthSessionProvider {...props}>
      <ApiAuthTokenBridge />
      {props.children}
    </NextAuthSessionProvider>
  );
}

function ApiAuthTokenBridge() {
  const { data: session } = useSession();

  React.useEffect(() => {
    setApiAuthToken(session?.backendAccessToken);
  }, [session?.backendAccessToken]);

  return null;
}
