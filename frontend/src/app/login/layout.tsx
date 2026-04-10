import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Login",
  description: "התחבר למערכת Skynet לאופטימיזציית פרומפטים",
  alternates: { canonical: "/login" },
  robots: { index: true, follow: true },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
