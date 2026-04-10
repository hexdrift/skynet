import NextAuth from "next-auth";
import type { Provider } from "next-auth/providers";
import Credentials from "next-auth/providers/credentials";

/**
 * Admin users — comma-separated list of usernames or emails.
 * Admins can see all jobs and delete any job.
 * Set via AUTH_ADMINS env var, e.g. "gilad,admin,root"
 */
const ADMIN_LIST = new Set(
  (process.env.AUTH_ADMINS ?? "admin")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean),
);

/**
 * Auth modes (checked in order):
 *
 * 1. SSO (ADFS / Entra ID / any OIDC)
 *    Set: AUTH_SSO_ISSUER, AUTH_SSO_CLIENT_ID, AUTH_SSO_CLIENT_SECRET
 *    Optional: AUTH_SSO_SCOPE (default: "openid profile email")
 *    The user is auto-redirected to the SSO login page — no local form.
 *
 * 2. Dev login (default when SSO is not configured)
 *    Just enter a username — no password needed.
 *    Set DEV_AUTH=false to disable.
 *
 * 3. No auth
 *    When both SSO and dev auth are disabled, the app runs open.
 */

// Legacy env var names also supported for backwards compatibility
const ssoIssuer = process.env.AUTH_SSO_ISSUER ?? process.env.AUTH_ADFS_ISSUER;
const ssoClientId = process.env.AUTH_SSO_CLIENT_ID ?? process.env.AUTH_ADFS_CLIENT_ID;
const ssoClientSecret = process.env.AUTH_SSO_CLIENT_SECRET ?? process.env.AUTH_ADFS_CLIENT_SECRET;
const ssoScope = process.env.AUTH_SSO_SCOPE ?? "openid profile email";

export const ssoConfigured = !!ssoIssuer && !!ssoClientId && !!ssoClientSecret;
const devAuthEnabled = !ssoConfigured && process.env.DEV_AUTH !== "false";
export const authEnabled = ssoConfigured || devAuthEnabled;

const providers: Provider[] = [];

if (ssoConfigured) {
  providers.push({
    id: "adfs",
    name: "SSO",
    type: "oidc",
    issuer: ssoIssuer,
    clientId: ssoClientId,
    clientSecret: ssoClientSecret,
    authorization: { params: { scope: ssoScope } },
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
} else if (devAuthEnabled) {
  providers.push(
    Credentials({
      name: "Dev Login",
      credentials: {
        username: { label: "שם משתמש", type: "text" },
      },
      async authorize(credentials) {
        const username = (credentials?.username as string)?.trim();
        if (!username) return null;
        return { id: username, name: username, email: `${username}@skynet.local` };
      },
    }),
  );
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers,
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  callbacks: {
    authorized({ auth: session }) {
      if (!authEnabled) return true;
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
      (session.user as unknown as Record<string, unknown>).role = token.role ?? "user";
      return session;
    },
  },
  trustHost: true,
});
