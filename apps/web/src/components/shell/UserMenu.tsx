"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { getMe, logout } from "@/lib/api/auth";
import { useApi } from "@/lib/useApi";

export function UserMenu() {
  const t = useT();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const { data: user } = useApi((s) => getMe(s), "me");

  async function onLogout() {
    setBusy(true);
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {user ? (
        <span className="font-semibold text-ink">
          {user.display_name}
          <span className="ml-1 font-normal text-muted">
            ({t(`role.${user.role}`)})
          </span>
        </span>
      ) : null}
      <Link
        href="/login"
        className="rounded-md px-2 py-1 font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        {t("shell.switchUser")}
      </Link>
      <Button variant="secondary" onClick={onLogout} disabled={busy}>
        {t("shell.logout")}
      </Button>
    </div>
  );
}
