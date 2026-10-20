import type { IconName } from "@/components/ui/Icon";

export type NavItem = {
  href: string;
  key: string;
  icon: IconName;
  exact?: boolean;
  /** Prefix that marks the item current when it differs from href. */
  match?: string;
};

export const MAIN_ITEMS: readonly NavItem[] = [
  { href: "/app", key: "nav.dashboard", icon: "home", exact: true },
  { href: "/app/deals", key: "nav.orders", icon: "box" },
  { href: "/app/cashflow", key: "nav.cashflow", icon: "trend" },
  { href: "/app/financing", key: "nav.financing", icon: "coins" },
  { href: "/app/suppliers", key: "nav.suppliers", icon: "users" },
  { href: "/app/analysis", key: "nav.analysis", icon: "chart" },
  // No cross-deal documents index exists in the API, so documents live on each deal.
  { href: "/app/deals", key: "sidebar.documents", icon: "file", match: "/app/documents" },
  { href: "/app/approvals", key: "nav.approvals", icon: "shield" },
  { href: "/app/inbox/email-check", key: "nav.emailCheck", icon: "mail" },
  { href: "/app/chat", key: "nav.chat", icon: "chat" },
];

export const TEAM: NavItem = { href: "/app/team", key: "nav.team", icon: "users" };

/** Only ADMIN reviews new companies (JUDGE has read access elsewhere but cannot decide). */
export const ADMIN_ONLY_ITEMS: readonly NavItem[] = [
  {
    href: "/app/admin/verifications",
    key: "nav.verifications",
    icon: "shield",
  },
];

export const SIMULATOR: NavItem = { href: "/demo/scam-simulator", key: "nav.simulator", icon: "play" };

export const ADMIN_ITEMS: readonly NavItem[] = [
  { href: "/app/admin/registry", key: "nav.registry", icon: "lock" },
  { href: "/app/admin/risk", key: "nav.risk", icon: "scale" },
  { href: "/demo/risk-playground", key: "nav.playground", icon: "sparkle" },
  { href: "/app/admin/privacy", key: "nav.privacy", icon: "eye" },
  { href: "/demo/privacy-playground", key: "nav.privacyPlayground", icon: "eye" },
  { href: "/app/admin/security", key: "nav.security", icon: "gear" },
  { href: "/demo/attack-console", key: "nav.attackConsole", icon: "ban" },
  { href: "/app/admin/audit", key: "nav.audit", icon: "file" },
  { href: "/demo/audit", key: "nav.auditDemo", icon: "swap" },
  SIMULATOR,
];

export type NavGroup = { id: "main" | "tools" | "admin"; labelKey: string; items: readonly NavItem[] };

/** Nav sections for a role. Staff (ADMIN/JUDGE) get the admin section; buyers also get the scam simulator. */
export function navGroups(role: string | undefined): NavGroup[] {
  const staff = role === "ADMIN" || role === "JUDGE";
  const main = role === "BUYER" ? [...MAIN_ITEMS, TEAM] : MAIN_ITEMS;
  const groups: NavGroup[] = [{ id: "main", labelKey: "sidebar.main", items: main }];
  if (staff) {
    const items = role === "ADMIN" ? [...ADMIN_ONLY_ITEMS, ...ADMIN_ITEMS] : ADMIN_ITEMS;
    groups.push({ id: "admin", labelKey: "sidebar.admin", items });
  }
  else if (role === "BUYER") groups.push({ id: "tools", labelKey: "sidebar.tools", items: [SIMULATOR] });
  return groups;
}

export function isCurrent(item: NavItem, pathname: string): boolean {
  if (item.match) return pathname.startsWith(item.match);
  if (item.exact) return pathname === item.href;
  return pathname.startsWith(item.href);
}
