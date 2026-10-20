"use client";

import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { ChatDrawer } from "@/components/chat/ChatDrawer";
import { FooterStatus } from "@/components/status/FooterStatus";
import { Skeleton } from "@/components/ui/Skeleton";
import { ToastProvider } from "@/components/ui/Toast";
import { useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { OPEN_PALETTE_EVENT } from "@/lib/shortcuts";
import { useDigits } from "@/lib/useDigits";
import { useEmbed } from "@/lib/useEmbed";
import { MeContext } from "@/lib/MeContext";
import { useApi } from "@/lib/useApi";

import { DemoPhone } from "./DemoPhone";
import { trackVisit } from "./onboarding";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

const CommandPalette = dynamic(() => import("./CommandPalette"), {
  ssr: false,
});

export function AppShell({ children }: { children: ReactNode }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const me = useApi((s) => getMe(s), "me");
  const [digits] = useDigits();
  const embed = useEmbed();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const isSupplier = me.data?.role === "SUPPLIER";
  const userId = me.data?.id;
  const role = me.data?.role;

  useEffect(() => {
    if (isSupplier) router.replace("/supplier");
  }, [isSupplier, router]);

  useEffect(() => {
    if (userId && !isSupplier) trackVisit(userId, pathname, role);
  }, [userId, isSupplier, pathname, role]);

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  useEffect(() => {
    if (isSupplier) return;
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    }
    document.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_PALETTE_EVENT, openPalette);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_PALETTE_EVENT, openPalette);
    };
  }, [isSupplier, openPalette]);

  if (embed) {
    return (
      <ToastProvider>
        <MeContext.Provider value={me.data}>
          <main id="main" className="min-h-[100dvh] min-w-0 flex-1 p-3">
            {me.loading || isSupplier ? (
              <Skeleton className="h-[60dvh]" />
            ) : (
              <div key={digits}>{children}</div>
            )}
          </main>
        </MeContext.Provider>
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <MeContext.Provider value={me.data}>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:font-semibold focus:text-brand-text focus:ring-2 focus:ring-brand-500"
        >
          {t("shell.skip")}
        </a>
        <TopBar
          showBell={Boolean(me.data) && !isSupplier}
          onSearch={openPalette}
        />
        <div className="mx-auto flex w-full max-w-7xl flex-1 gap-4 px-4 py-6 md:gap-8">
          <Sidebar />
          <main id="main" className="min-h-[100dvh] min-w-0 flex-1">
            {me.loading || isSupplier ? (
              <Skeleton className="h-[60dvh]" />
            ) : (
              <div key={digits}>{children}</div>
            )}
          </main>
        </div>
        {paletteOpen ? (
          <CommandPalette onClose={() => setPaletteOpen(false)} />
        ) : null}
        <Suspense fallback={null}>
          <ChatDrawer />
        </Suspense>
        <DemoPhone />
        <footer className="grid justify-items-center gap-2 px-4 py-6 text-center text-sm text-muted">
          <p>{t("common.footer")}</p>
          <FooterStatus />
        </footer>
      </MeContext.Provider>
    </ToastProvider>
  );
}
