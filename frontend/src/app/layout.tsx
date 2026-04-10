import type { Metadata, Viewport } from "next";
import { AppShell } from "@/components/app-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Providers } from "@/components/theme-provider";
import { SessionProvider } from "@/components/session-provider";
import { ToastContainer } from "@/components/toast-container";
import { SplashScreen } from "@/components/splash-screen";
import { TutorialOverlay, TutorialMenu } from "@/components/tutorial";
import { TutorialProvider } from "@/components/tutorial/tutorial-provider";
import "@fontsource-variable/heebo/index.css";
import "@fontsource-variable/inter/index.css";
import "react-toastify/dist/ReactToastify.css";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://skynet.app";
const siteName = "Skynet";
const siteDescription =
 "מערכת אופטימיזציית פרומפטים מבוססת DSPy — שפרו ביצועי מודלי שפה באופן אוטומטי";

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

/* JSON-LD structured data */
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
 return (
 <html lang="he" dir="rtl" suppressHydrationWarning>
 <head>
 <link rel="preconnect" href="/" crossOrigin="" />
 {process.env.NEXT_PUBLIC_API_URL && (
 <link rel="dns-prefetch" href={process.env.NEXT_PUBLIC_API_URL} />
 )}
 <script
 type="application/ld+json"
 dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
 />
 </head>
 <body suppressHydrationWarning>
 <SessionProvider>
 <Providers>
 <TooltipProvider>
 <SplashScreen />
 <TutorialProvider>
 <AppShell>{children}</AppShell>
 <TutorialOverlay />
 <TutorialMenu />
 </TutorialProvider>
 </TooltipProvider>
 </Providers>
 </SessionProvider>
 <ToastContainer />
 </body>
 </html>
 );
}
