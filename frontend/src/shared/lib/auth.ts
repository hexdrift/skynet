import NextAuth from "next-auth";
import type { Provider } from "next-auth/providers";
import Credentials from "next-auth/providers/credentials";
import { msg } from "@/shared/lib/messages";

/**
 * Authentication configuration.
 *
 * Production (ADFS / any OIDC):
 *   Set AUTH_SSO_ISSUER, AUTH_SSO_CLIENT_ID, AUTH_SSO_CLIENT_SECRET.
 *   Users are auto-redirected to ADFS — no local form.
 *
 * Development (default when ADFS is not configured):
 *   Simple username login — no password.
 *
 * Optional env vars:
 *   AUTH_SSO_SCOPE        — OIDC scopes (default: "openid profile email")
 *   AUTH_ADMINS           — comma-separated admin usernames (default: "admin")
 *   NODE_EXTRA_CA_CERTS   — path to CA bundle .pem for self-signed certs
 */

const ADMIN_LIST = new Set(
  (process.env.AUTH_ADMINS ?? "admin")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean),
);

const issuer = process.env.AUTH_SSO_ISSUER;
const clientId = process.env.AUTH_SSO_CLIENT_ID;
const clientSecret = process.env.AUTH_SSO_CLIENT_SECRET;
const scope = process.env.AUTH_SSO_SCOPE ?? "openid profile email";

const adfsConfigured = !!issuer && !!clientId && !!clientSecret;

const providers: Provider[] = [];

if (adfsConfigured) {
  providers.push({
    id: "adfs",
    name: "ADFS",
    type: "oidc",
    issuer,
    clientId,
    clientSecret,
    authorization: { params: { scope } },
    profile(profile) {
      return {
        id: profile.sub,
        name:
          profile.name ??
          profile.unique_name ??
          profile.upn ??
          profile.preferred_username ??
          profile.sub,
        email: profile.email ?? profile.upn ?? profile.preferred_username,
      };
    },
  });
} else {
  providers.push(
    Credentials({
      name: "Dev Login",
      credentials: {
        username: { label: msg("auto.auth.literal.1"), type: "text" },
      },
      async authorize(credentials) {
        const username = (credentials?.username as string)?.trim();
        if (!username) return null;
        return { id: username, name: username, email: `${username}@skynet.local` };
      },
    }),
  );
}

export const { handlers, auth } = NextAuth({
  providers,
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  callbacks: {
    authorized({ auth: session }) {
      return !!session?.user;
    },
    jwt({ token, user }) {
      if (user) {
        token.name = user.name ?? token.name;
        token.email = user.email ?? token.email;
        const identifier = (user.name ?? user.email ?? "").toLowerCase();
        token.role = ADMIN_LIST.has(identifier) ? "admin" : "user";
      }
      return token;
    },
    session({ session, token }) {
      if (typeof token.name === "string") session.user.name = token.name;
      if (typeof token.email === "string") session.user.email = token.email;
      session.user.role = token.role ?? "user";
      return session;
    },
  },
  trustHost: true,
});
