"use client";

import { useT } from "@/i18n";
import { typeMeta } from "@/lib/privacy/segments";
import type { Segment } from "@/lib/privacy/types";

import { typeLabel } from "./privacyText";

type Props = { segments: readonly Segment[]; className?: string; mono?: boolean };

/** Renders segments; typed ones become a <mark> with colour, icon, short code and screen-reader text. */
export function SegmentText({ segments, className = "", mono = false }: Props) {
  const t = useT();
  return (
    <span
      className={`break-words whitespace-pre-wrap ${mono ? "font-mono text-[0.8125rem]" : ""} ${className}`}
    >
      {segments.map((s, i) => {
        if (s.type === null) return <span key={i}>{s.text}</span>;
        const meta = typeMeta(s.type);
        return (
          <mark
            key={i}
            data-type={s.type}
            data-token={s.token ?? undefined}
            className={meta.mark}
          >
            <span aria-hidden="true" className="mr-0.5 text-[0.7em] font-semibold">
              {meta.icon}
            </span>
            {s.text}
            <span aria-hidden="true" className="ml-0.5 align-super text-[0.6em] font-bold">
              {meta.code}
            </span>
            <span className="sr-only">
              {" "}
              ({typeLabel(t, s.type, 1)}
              {s.token ? `, ${s.token}` : ""})
            </span>
          </mark>
        );
      })}
    </span>
  );
}
