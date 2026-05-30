import { auth } from "@/shared/lib/auth";

export default auth;

export const config = {
  matcher: [
    // ``share`` is excluded so public ``/share/<token>`` pages render for
    // anonymous visitors instead of bouncing to /login (read-only share links).
    "/((?!login|api/auth|share|_next/static|_next/image|favicon\\.svg|robots\\.txt|sitemap\\.xml).*)",
  ],
};
