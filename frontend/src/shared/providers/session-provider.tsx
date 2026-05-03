"use client";

import { SessionProvider as NextAuthSessionProvider, useSession } from "next-auth/react";
import type { ComponentProps } from "react";
import * as React from "react";
import { setApiAuthToken } from "@/shared/lib/api";

type SessionProviderProps = ComponentProps<typeof NextAuthSessionProvider>;

export function SessionProvider(props: SessionProviderProps) {
  // Refetch every 5 min to keep ``backendAccessToken`` fresh; the backend
  // bearer JWT has a 15-min TTL (BACKEND_AUTH_TOKEN_TTL_SECONDS=900) and
  // without polling the in-memory token expires while the modal sits open.
  return (
    <NextAuthSessionProvider refetchInterval={300} refetchOnWindowFocus {...props}>
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
