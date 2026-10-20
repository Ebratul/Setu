import type { ReactNode } from "react";

type Props = {
  id: string;
  title: string;
  lead?: string;
  children: ReactNode;
  alt?: boolean;
};

export function Section({ id, title, lead, children, alt = false }: Props) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={`scroll-mt-20 py-14 sm:py-20 ${alt ? "bg-surface-alt" : ""}`}
    >
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2 id={`${id}-title`} className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">
          {title}
        </h2>
        {lead ? <p className="mt-3 max-w-3xl text-base text-muted">{lead}</p> : null}
        <div className="mt-8">{children}</div>
      </div>
    </section>
  );
}
