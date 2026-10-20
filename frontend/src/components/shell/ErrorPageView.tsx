"use client";

import Link from "next/link";
import { useEffect } from "react";

import { useT } from "@/i18n";

import { StatusPage, statusLink } from "./StatusPage";

type Props = { error?: Error & { digest?: string }; reset: () => void };

export function ErrorPageView({ error, reset }: Props) {
  const t = useT();
  useEffect(() => {
    if (error) console.error(error);
  }, [error]);
  return (
    <StatusPage
      code={t("errpage.code")}
      title={t("errpage.title")}
      body={t("errpage.body")}
      note={error?.digest ? t("errpage.ref", { id: error.digest }) : undefined}
    >
      <button
        type="button"
        onClick={reset}
        className={`${statusLink} bg-brand-700 text-white hover:bg-brand-800`}
      >
        {t("errpage.retry")}
      </button>
      <Link href="/app" className={`${statusLink} border border-line bg-surface text-ink hover:bg-surface-alt`}>
        {t("errpage.home")}
      </Link>
    </StatusPage>
  );
}
