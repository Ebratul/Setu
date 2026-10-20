"use client";

import Link from "next/link";

import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

type Props = { href: string; label?: string };

export function TryItButton({ href, label }: Props) {
  const t = useT();
  return (
    <Link
      href={href}
      data-testid="try-it"
      className="!no-underline inline-flex min-h-11 items-center gap-2 rounded-xl bg-brand-700 px-4 py-2 font-semibold !text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <Icon name="play" size={16} />
      {label ?? t("docs.tryIt")}
    </Link>
  );
}
