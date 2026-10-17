"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useT } from "@/i18n";

const ITEMS = [
  { href: "/app", key: "nav.dashboard", exact: true },
  { href: "/app/deals", key: "nav.orders", exact: false },
  { href: "/app/cashflow", key: "nav.cashflow", exact: false },
  { href: "/app/financing", key: "nav.financing", exact: false },
  { href: "/app/suppliers", key: "nav.suppliers", exact: false },
  { href: "/app/analysis", key: "nav.analysis", exact: false },
  { href: "/app/chat", key: "nav.chat", exact: false },
] as const;

export function AppNav() {
  const t = useT();
  const pathname = usePathname();
  return (
    <nav aria-label={t("nav.label")}>
      <ul className="flex flex-wrap gap-1 md:flex-col">
        {ITEMS.map((item) => {
          const current = item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={`block rounded-xl px-4 py-2 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
                  current
                    ? "bg-brand-700 text-white"
                    : "text-ink hover:bg-brand-50"
                }`}
              >
                {t(item.key)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
