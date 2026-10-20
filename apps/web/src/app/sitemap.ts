import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/siteUrl";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${siteUrl()}/`, changeFrequency: "monthly", priority: 1 },
    { url: `${siteUrl()}/judges`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${siteUrl()}/verify`, changeFrequency: "monthly", priority: 0.6 },
    { url: `${siteUrl()}/accessibility`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
