import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
  labelledBy?: string;
};

export function Card({
  children,
  className = "",
  as: Tag = "div",
  labelledBy,
}: Props) {
  return (
    <Tag
      aria-labelledby={labelledBy}
      className={`rounded-card bg-surface p-5 shadow-card ${className}`}
    >
      {children}
    </Tag>
  );
}
