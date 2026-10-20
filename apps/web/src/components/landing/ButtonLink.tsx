import Link from "next/link";
import type { ReactNode } from "react";

type Props = {
  href: string;
  variant?: "primary" | "accent" | "secondary" | "ghost";
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
};

const variants = {
  primary: "bg-brand-700 text-white hover:bg-brand-800",
  accent: "bg-accent-500 text-slate-900 hover:bg-accent-400",
  secondary: "border border-line bg-surface text-ink hover:bg-surface-alt",
  ghost: "text-brand-text hover:bg-brand-50",
};

/** A real link styled like Button, so we never nest a button inside an anchor. */
export function ButtonLink({ href, variant = "primary", children, className = "", ariaLabel }: Props) {
  return (
    <Link
      href={href}
      aria-label={ariaLabel}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2 text-center text-sm font-semibold transition-colors duration-(--duration-fast) focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${variants[variant]} ${className}`}
    >
      {children}
    </Link>
  );
}
