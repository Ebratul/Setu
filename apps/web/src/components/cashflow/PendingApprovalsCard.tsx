"use client";

import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { useT } from "@/i18n";

type Props = { count: number };

export function PendingApprovalsCard({ count }: Props) {
  const t = useT();
  return (
    <Card as="section" labelledBy="appr-h">
      <h2 id="appr-h" className="text-lg font-semibold text-ink">
        {t("dash.approvals")}
      </h2>
      <p className="mt-2 text-3xl font-bold text-ink">{count}</p>
      <Link
        href="/app/approvals"
        className="mt-2 inline-block font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        {t("dash.approvalsLink")}
      </Link>
    </Card>
  );
}
