"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { useT } from "@/i18n";

import { PublicFooter } from "./PublicFooter";
import { PublicHeader } from "./PublicHeader";

const CHECKED = ["c1", "c2", "c3", "c4", "c5"] as const;
const PENDING = ["p1", "p2", "p3", "p4"] as const;
const KEYS = [
  { id: "palette", keys: "Ctrl / ⌘ + K", ready: true },
  { id: "chat", keys: "/", ready: true },
  { id: "esc", keys: "Esc", ready: true },
  { id: "arrows", keys: "← → ↑ ↓ Home End", ready: true },
  { id: "tab", keys: "Tab / Shift + Tab", ready: true },
] as const;
const LIMITS = ["l1", "l2", "l3", "l4"] as const;

const h2 = "mt-10 text-xl font-bold text-ink";

export function AccessibilityStatement() {
  const t = useT();
  return (
    <>
      <PublicHeader />
      <main id="main" className="mx-auto w-full max-w-3xl flex-1 px-4 py-12 sm:px-6">
        <h1 className="text-3xl font-extrabold tracking-tight text-ink">{t("a11y.title")}</h1>
        <p className="mt-4 text-base text-ink">{t("a11y.intro")}</p>
        <p className="mt-3 text-sm text-muted">{t("a11y.updated")}</p>

        <h2 className={h2}>{t("a11y.status.title")}</h2>
        <p className="mt-3 text-base text-ink">{t("a11y.status.body")}</p>

        <h2 className={h2}>{t("a11y.checked.title")}</h2>
        <ul className="mt-3 list-disc space-y-2 ps-6 text-base text-ink">
          {CHECKED.map((c) => (
            <li key={c}>{t(`a11y.checked.${c}`)}</li>
          ))}
        </ul>

        <h2 className={h2}>{t("a11y.pending.title")}</h2>
        <ul className="mt-3 list-disc space-y-2 ps-6 text-base text-ink">
          {PENDING.map((c) => (
            <li key={c}>{t(`a11y.pending.${c}`)}</li>
          ))}
        </ul>

        <h2 className={h2}>{t("a11y.keys.title")}</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-80 border-collapse text-start text-sm">
            <caption className="sr-only">{t("a11y.keys.title")}</caption>
            <thead>
              <tr className="border-b border-line">
                <th scope="col" className="py-2 pe-4 text-start font-semibold text-ink">{t("a11y.keys.key")}</th>
                <th scope="col" className="py-2 pe-4 text-start font-semibold text-ink">{t("a11y.keys.action")}</th>
                <th scope="col" className="py-2 text-start font-semibold text-ink">{t("a11y.keys.state")}</th>
              </tr>
            </thead>
            <tbody>
              {KEYS.map((k) => (
                <tr key={k.id} className="border-b border-line align-top">
                  <th scope="row" className="py-2 pe-4 text-start font-mono font-semibold text-ink">{k.keys}</th>
                  <td className="py-2 pe-4 text-ink">{t(`a11y.keys.${k.id}`)}</td>
                  <td className="py-2">
                    <Badge tone={k.ready ? "success" : "warning"}>
                      {k.ready ? t("a11y.keys.ready") : t("a11y.keys.planned")}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2 className={h2}>{t("a11y.limits.title")}</h2>
        <ul className="mt-3 list-disc space-y-2 ps-6 text-base text-ink">
          {LIMITS.map((c) => (
            <li key={c}>{t(`a11y.limits.${c}`)}</li>
          ))}
        </ul>

        <h2 className={h2}>{t("a11y.contact.title")}</h2>
        <p className="mt-3 text-base text-ink">{t("a11y.contact.body")}</p>

        <Link
          href="/"
          className="mt-10 inline-flex min-h-11 items-center rounded-lg font-semibold text-brand-text hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {t("a11y.back")}
        </Link>
      </main>
      <PublicFooter />
    </>
  );
}
