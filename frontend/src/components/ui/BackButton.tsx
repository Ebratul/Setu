"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useT } from "@/i18n";

type Props = { fallbackHref?: string; href?: string; className?: string };

export function BackButton({
  fallbackHref = "/",
  href,
  className = "",
}: Props) {
  const t = useT();
  const router = useRouter();
  function goBack() {
    if (window.history.length > 1) router.back();
    else router.push(fallbackHref);
  }
  const cls = `inline-flex min-h-11 items-center gap-1 rounded-lg px-2 font-semibold text-brand-text hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${className}`;
  if (href) {
    return (
      <Link href={href} className={cls}>
        <span aria-hidden="true">←</span>
        {t("common.back")}
      </Link>
    );
  }
  return (
    <button type="button" onClick={goBack} className={cls}>
      <span aria-hidden="true">←</span>
      {t("common.back")}
    </button>
  );
}
