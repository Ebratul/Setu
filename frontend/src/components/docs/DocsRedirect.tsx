"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useLang, useT } from "@/i18n";

/** /docs has no content of its own: it opens the docs home in the reader's language. */
export function DocsRedirect() {
  const { lang } = useLang();
  const router = useRouter();
  const t = useT();
  useEffect(() => {
    router.replace(`/docs/${lang}`);
  }, [lang, router]);
  return (
    <main id="main" className="mx-auto w-full max-w-2xl flex-1 p-6">
      <h1 className="text-2xl font-bold text-ink">{t("docs.title")}</h1>
      <p className="mt-3">
        <Link href={`/docs/${lang}`} className="font-semibold text-brand-text underline">
          {t("docs.home")}
        </Link>
      </p>
    </main>
  );
}
