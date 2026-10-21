"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Drawer } from "@/components/ui/Drawer";
import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

import { AppNav } from "./AppNav";

/** Menu button plus slide-in navigation for screens below md. */
export function MobileNav() {
  const t = useT();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setOpen(false), 0);
    return () => clearTimeout(id);
  }, [pathname]);
  return (
    <div className="md:hidden">
      <button
        type="button"
        data-testid="mobile-menu"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t("topbar.menu")}
        onClick={() => setOpen(true)}
        className="flex size-11 items-center justify-center rounded-xl border border-line text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <Icon name="menu" />
      </button>
      {open ? (
        <Drawer title={t("topbar.menuTitle")} side="left" onClose={() => setOpen(false)}>
          <AppNav onNavigate={() => setOpen(false)} />
        </Drawer>
      ) : null}
    </div>
  );
}
