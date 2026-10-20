"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { useToast } from "@/components/ui/Toast";
import { useT } from "@/i18n";
import { ACCOUNT_BLOCK_EVENT, NOT_VERIFIED_EVENT } from "@/lib/api/client";

/** One friendly toast for any 403 ACCOUNT_NOT_VERIFIED; routes suspended/rejected accounts and admins without TOTP. */
export function NotVerifiedListener() {
  const t = useT();
  const toast = useToast();
  const last = useRef(0);
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    function onBlock(e: Event) {
      if (pathname.startsWith("/onboarding") || pathname.startsWith("/account-status")) return;
      const code = (e as CustomEvent<string>).detail;
      if (code === "MFA_REQUIRED") router.replace("/onboarding?step=security");
      else router.replace(`/account-status?reason=${code === "ACCOUNT_REJECTED" ? "rejected" : "suspended"}`);
    }
    window.addEventListener(ACCOUNT_BLOCK_EVENT, onBlock);
    return () => window.removeEventListener(ACCOUNT_BLOCK_EVENT, onBlock);
  }, [router, pathname]);
  useEffect(() => {
    function onEvent() {
      const now = Date.now();
      if (now - last.current < 4000) return;
      last.current = now;
      toast(t("vb.toast"), "danger");
    }
    window.addEventListener(NOT_VERIFIED_EVENT, onEvent);
    return () => window.removeEventListener(NOT_VERIFIED_EVENT, onEvent);
  }, [t, toast]);
  return null;
}
