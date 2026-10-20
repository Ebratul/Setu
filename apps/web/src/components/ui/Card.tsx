import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
  labelledBy?: string;
  /** Hover-lift for cards that are clickable or invite exploration. */
  interactive?: boolean;
};

export function Card({
  children,
  className = "",
  as: Tag = "div",
  labelledBy,
  interactive = false,
}: Props) {
  return (
    <Tag
      aria-labelledby={labelledBy}
      className={`rounded-card bg-surface p-5 shadow-card ${
        interactive
          ? "transition-all duration-(--duration-base) hover:-translate-y-0.5 hover:shadow-card-hover motion-reduce:transform-none"
          : ""
      } ${className}`}
    >
      {children}
    </Tag>
  );
}
