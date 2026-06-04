import { auth } from "@/shared/lib/auth";

export default auth;

export const config = {
  matcher: [
    // Every app surface requires login — including ``/share/<token>``. A
    // recipient must authenticate so the backend resolves them to the role the
    // link grants (e.g. editor); a logged-out visitor bounces to /login and
    // returns via callbackUrl.
    "/((?!login|api/auth|_next/static|_next/image|favicon\\.svg|robots\\.txt|sitemap\\.xml).*)",
  ],
};
