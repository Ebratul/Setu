import type { MetadataRoute } from "next";

import { listDocs } from "@/lib/docs/content";
import { DOC_LANGS } from "@/lib/docs/types";
import { siteUrl } from "@/lib/siteUrl";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${siteUrl()}/`, changeFrequency: "monthly", priority: 1 },
    { url: `${siteUrl()}/judges`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${siteUrl()}/verify`, changeFrequency: "monthly", priority: 0.6 },
    { url: `${siteUrl()}/accessibility`, changeFrequency: "yearly", priority: 0.3 },
    ...DOC_LANGS.flatMap((lang) =>
      listDocs(lang).map((d) => ({
        url: `${siteUrl()}/docs/${lang}/${d.meta.id}`,
        changeFrequency: "monthly" as const,
        priority: 0.5,
      })),
    ),
  ];
}
