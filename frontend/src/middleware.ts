export { auth as middleware } from "@/lib/auth";

export const config = {
  // Protect all routes except login, api/auth, static assets
  matcher: ["/((?!login|api/auth|_next/static|_next/image|favicon\\.svg|skynet_logo\\.svg|robots\\.txt|sitemap\\.xml).*)"],
};
