import type { ReactNode } from "react";

export function Steps({ children }: { children: ReactNode }) {
  return <ol className="docs-steps !mt-4 space-y-6">{children}</ol>;
}

export function Step({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <li className="docs-step">
      <p className="text-lg font-semibold text-ink">{title}</p>
      {children ? <div className="docs-step-body mt-2 space-y-3">{children}</div> : null}
    </li>
  );
}
