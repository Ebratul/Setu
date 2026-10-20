"use client";

import Link from "next/link";

import { useT } from "@/i18n";

import { StatusPage, statusLink } from "./StatusPage";

export function NotFoundView() {
  const t = useT();
  return (
    <StatusPage code={t("notfound.code")} title={t("notfound.title")} body={t("notfound.body")}>
      <Link href="/app" className={`${statusLink} bg-brand-700 text-white hover:bg-brand-800`}>
        {t("notfound.home")}
      </Link>
      <Link href="/app/deals" className={`${statusLink} border border-line bg-surface text-ink hover:bg-surface-alt`}>
        {t("notfound.deals")}
      </Link>
      <Link href="/" className={`${statusLink} text-brand-text underline`}>
        {t("notfound.landing")}
      </Link>
    </StatusPage>
  );
}
