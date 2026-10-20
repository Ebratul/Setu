import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/siteUrl";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/$", "/verify", "/accessibility", "/judges", "/docs"],
        disallow: ["/app", "/supplier", "/demo", "/login", "/onboarding", "/api"],
      },
    ],
    sitemap: `${siteUrl()}/sitemap.xml`,
  };
}
