import type { ReactNode } from "react";

export function FAQ({ children }: { children: ReactNode }) {
  return <div className="not-prose my-4 divide-y divide-line rounded-card border border-line bg-surface">{children}</div>;
}

export function FAQItem({ q, children }: { q: string; children: ReactNode }) {
  return (
    <details className="group p-4">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 font-semibold text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
        {q}
        <span aria-hidden="true" className="text-brand-text transition-transform group-open:rotate-90">
          ›
        </span>
      </summary>
      <div className="mt-2 space-y-2 text-ink">{children}</div>
    </details>
  );
}
