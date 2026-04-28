import { auth } from "@/shared/lib/auth";

export default auth;

export const config = {
  matcher: [
    "/((?!login|api/auth|_next/static|_next/image|favicon\\.svg|skynet_logo\\.svg|robots\\.txt|sitemap\\.xml).*)",
  ],
};
