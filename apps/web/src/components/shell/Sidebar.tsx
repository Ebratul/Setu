"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

import { AppNav } from "./AppNav";

export const SIDEBAR_KEY = "setu_sidebar";

/** Desktop sidebar. Collapsed state is remembered per browser; mobile uses MobileNav instead. */
export function Sidebar() {
  const t = useT();
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => {
      try {
        if (localStorage.getItem(SIDEBAR_KEY) === "collapsed") setCollapsed(true);
      } catch {
        /* storage unavailable */
      }
    }, 0);
    return () => clearTimeout(id);
  }, []);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(SIDEBAR_KEY, next ? "collapsed" : "expanded");
    } catch {
      /* storage unavailable */
    }
  }

  return (
    <aside
      data-testid="sidebar"
      data-collapsed={collapsed}
      className={`hidden shrink-0 transition-[width] duration-200 md:block ${collapsed ? "w-14" : "w-56"}`}
    >
      <div className="sticky top-20 max-h-[calc(100dvh-6rem)] space-y-3 overflow-y-auto pb-4">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={t(collapsed ? "sidebar.expand" : "sidebar.collapse")}
          title={t(collapsed ? "sidebar.expand" : "sidebar.collapse")}
          className="flex size-11 items-center justify-center rounded-xl border border-line text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <Icon name="panel" className={collapsed ? "rotate-180" : ""} />
        </button>
        <AppNav collapsed={collapsed} />
      </div>
    </aside>
  );
}
