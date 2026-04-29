import type { Metadata, Viewport } from "next";
import Script from "next/script";
import { AppShell } from "@/shared/layout/app-shell";
import { TooltipProvider } from "@/shared/ui/primitives/tooltip";
import { Providers } from "@/shared/providers/theme-provider";
import { SessionProvider } from "@/shared/providers/session-provider";
import { ToastContainer } from "@/shared/providers/toast-container";
import { SplashScreen } from "@/shared/layout/splash-screen";
import { TutorialOverlay, TutorialMenu, TutorialProvider } from "@/features/tutorial";
import {
  UserPrefsProvider,
  SettingsModalProvider,
  SettingsModal,
} from "@/features/settings";
import { msg } from "@/shared/lib/messages";
import { getServerRuntimeEnv, serializeRuntimeEnv } from "@/shared/lib/runtime-env";
import { SentryInit } from "@/shared/observability/sentry-init";
import "@fontsource-variable/heebo/index.css";
import "@fontsource-variable/inter/index.css";
import "react-toastify/dist/ReactToastify.css";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://skynet.app";
const siteName = "Skynet";
const siteDescription = msg("app.meta.description");

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FAF8F5" },
    { media: "(prefers-color-scheme: dark)", color: "#0F0C0A" },
  ],
};

export const metadata: Metadata = {
  title: {
    default: siteName,
    template: `%s | ${siteName}`,
  },
  description: siteDescription,
  icons: {
    icon: "/favicon.svg",
    apple: "/favicon.svg",
  },
  metadataBase: new URL(siteUrl),
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    locale: "he_IL",
    siteName,
    title: siteName,
    description: siteDescription,
    url: siteUrl,
  },
  twitter: {
    card: "summary_large_image",
    title: siteName,
    description: siteDescription,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: siteName,
  description: siteDescription,
  url: siteUrl,
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Web",
  inLanguage: "he",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const runtimeEnv = getServerRuntimeEnv();
  return (
    <html lang="he" dir="rtl" suppressHydrationWarning>
      <head>
        <Script id="skynet-runtime-env" strategy="beforeInteractive">
          {serializeRuntimeEnv(runtimeEnv)}
        </Script>
        <link rel="preconnect" href="/" crossOrigin="" />
        <link rel="dns-prefetch" href={runtimeEnv.apiUrl} />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body suppressHydrationWarning>
        <SentryInit />
        <SessionProvider>
          <UserPrefsProvider>
            <Providers>
              <TooltipProvider>
                <SplashScreen />
                <TutorialProvider>
                  <SettingsModalProvider>
                    <AppShell>{children}</AppShell>
                    <SettingsModal />
                  </SettingsModalProvider>
                  <TutorialOverlay />
                  <TutorialMenu />
                </TutorialProvider>
              </TooltipProvider>
            </Providers>
          </UserPrefsProvider>
        </SessionProvider>
        <ToastContainer />
      </body>
    </html>
  );
}
