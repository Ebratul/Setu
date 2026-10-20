import type { ReactNode } from "react";

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="mx-0.5 rounded border border-line bg-surface-alt px-1.5 py-0.5 font-mono text-[0.8125rem] font-semibold text-ink shadow-card">
      {children}
    </kbd>
  );
}
