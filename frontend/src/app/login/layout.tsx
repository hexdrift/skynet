import type { Metadata } from "next";
import { msg } from "@/shared/lib/messages";

export const metadata: Metadata = {
  title: "Login",
  description: msg("auth.login.meta_description"),
  alternates: { canonical: "/login" },
  robots: { index: true, follow: true },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
