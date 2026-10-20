import { searchRecords } from "@/lib/docs/content";
import { DOC_LANGS, isDocLang } from "@/lib/docs/types";

export function generateStaticParams() {
  return DOC_LANGS.map((lang) => ({ lang }));
}

export async function GET(_req: Request, { params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isDocLang(lang)) return new Response("Not found", { status: 404 });
  // Untranslated pages stay findable: add the English record for ids missing in this language.
  const own = searchRecords(lang);
  if (lang !== "en") {
    const have = new Set(own.map((r) => r.id));
    for (const r of searchRecords("en")) if (!have.has(r.id)) own.push({ ...r, url: `/docs/${lang}/${r.id}` });
  }
  return Response.json(own);
}
