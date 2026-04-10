import { auth } from "@/lib/auth";

// NextAuth v5 returns a callable handler suitable for proxy usage.
export default auth;

export const config = {
  // Protect all routes except login, api/auth, static assets
  matcher: ["/((?!login|api/auth|_next/static|_next/image|favicon\\.svg|skynet_logo\\.svg|robots\\.txt|sitemap\\.xml).*)"],
};
