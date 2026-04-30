import NextAuth from "next-auth";
import type { Provider } from "next-auth/providers";
import Credentials from "next-auth/providers/credentials";
import { createHmac, randomUUID } from "crypto";
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
 *   AUTH_SSO_SCOPE        — OIDC scopes (default: "openid profile email groups")
 *   AUTH_ADMIN_GROUPS     — comma-separated IdP groups that grant admin access
 *   AUTH_ADMINS           — break-glass comma-separated admin usernames
 *   AUTH_GROUP_CLAIM      — profile claim containing groups (default: "groups")
 *   BACKEND_AUTH_SECRET   — shared secret for backend API bearer tokens
 *   NODE_EXTRA_CA_CERTS   — path to CA bundle .pem for self-signed certs
 */

const issuer = process.env.AUTH_SSO_ISSUER;
const clientId = process.env.AUTH_SSO_CLIENT_ID;
const clientSecret = process.env.AUTH_SSO_CLIENT_SECRET;
const adfsConfigured = !!issuer && !!clientId && !!clientSecret;
const devAdminFallback = adfsConfigured ? "" : "admin";

const ADMIN_LIST = new Set(
  (process.env.AUTH_ADMINS ?? devAdminFallback)
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean),
);
const ADMIN_GROUPS = new Set(
  (process.env.AUTH_ADMIN_GROUPS ?? "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean),
);

const scope = process.env.AUTH_SSO_SCOPE ?? "openid profile email groups";
const groupClaim = process.env.AUTH_GROUP_CLAIM ?? "groups";
const backendAuthSecret = process.env.BACKEND_AUTH_SECRET ?? process.env.AUTH_SECRET;
const backendTokenTtlSeconds = Number.parseInt(process.env.BACKEND_AUTH_TOKEN_TTL_SECONDS ?? "900", 10);

const providers: Provider[] = [];

function readClaim(profile: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => {
    if (!acc || typeof acc !== "object" || Array.isArray(acc)) return undefined;
    return (acc as Record<string, unknown>)[part];
  }, profile);
}

function normalizeStringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).map((s) => s.trim()).filter(Boolean);
  if (typeof value === "string") {
    return value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  return [];
}

function profileGroups(profile: Record<string, unknown>): string[] {
  return normalizeStringList(readClaim(profile, groupClaim));
}

function isAdmin(identifier: string, groups: string[]) {
  if (ADMIN_LIST.has(identifier.toLowerCase())) return true;
  return groups.some((group) => ADMIN_GROUPS.has(group.toLowerCase()));
}

function base64url(value: Buffer | string) {
  return Buffer.from(value).toString("base64url");
}

function signBackendToken(token: { name?: unknown; email?: unknown; role?: unknown; groups?: unknown }) {
  if (!backendAuthSecret) return undefined;
  const name = typeof token.name === "string" ? token.name : undefined;
  const email = typeof token.email === "string" ? token.email : undefined;
  const subject = name || email;
  if (!subject) return undefined;
  const now = Math.floor(Date.now() / 1000);
  const groups = normalizeStringList(token.groups);
  const header = { alg: "HS256", typ: "JWT" };
  const payload = {
    aud: "skynet-backend",
    iss: "skynet-frontend",
    sub: subject,
    name,
    email,
    role: typeof token.role === "string" ? token.role : "user",
    groups,
    iat: now,
    exp: now + Math.max(60, backendTokenTtlSeconds || 900),
    jti: randomUUID(),
  };
  const encodedHeader = base64url(JSON.stringify(header));
  const encodedPayload = base64url(JSON.stringify(payload));
  const signature = createHmac("sha256", backendAuthSecret)
    .update(`${encodedHeader}.${encodedPayload}`)
    .digest("base64url");
  return `${encodedHeader}.${encodedPayload}.${signature}`;
}

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
      const groups = profileGroups(profile as Record<string, unknown>);
      const identifier = String(
        profile.name ??
          profile.unique_name ??
          profile.upn ??
          profile.preferred_username ??
          profile.email ??
          profile.sub ??
          "",
      ).toLowerCase();
      return {
        id: profile.sub,
        name:
          profile.name ??
          profile.unique_name ??
          profile.upn ??
          profile.preferred_username ??
          profile.sub,
        email: profile.email ?? profile.upn ?? profile.preferred_username,
        groups,
        role: isAdmin(identifier, groups) ? "admin" : "user",
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
        return {
          id: username,
          name: username,
          email: `${username}@skynet.local`,
          groups: [],
          role: isAdmin(username, []) ? "admin" : "user",
        };
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
        token.groups = user.groups ?? [];
        token.role = user.role ?? "user";
      }
      return token;
    },
    session({ session, token }) {
      if (typeof token.name === "string") session.user.name = token.name;
      if (typeof token.email === "string") session.user.email = token.email;
      session.user.role = token.role ?? "user";
      session.user.groups = normalizeStringList(token.groups);
      session.backendAccessToken = signBackendToken(token);
      return session;
    },
  },
  trustHost: true,
});
