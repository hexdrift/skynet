import type { MetadataRoute } from "next";
import { getSiteUrl } from "@/shared/lib/site-config";

const siteUrl = getSiteUrl();

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/api/", "/login"],
    },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
