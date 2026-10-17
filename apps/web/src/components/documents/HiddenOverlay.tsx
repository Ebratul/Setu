"use client";

import type { HiddenSpan } from "@/lib/api/documents";

export const A4 = { width: 595.28, height: 841.89 };

type Props = { spans: HiddenSpan[]; page?: number };

/** Best-effort red boxes over page 1 of the preview (bbox is x0, top, x1, bottom in PDF points). Decorative: the list is the accessible version. */
export function HiddenOverlay({ spans, page = 1 }: Props) {
  const boxes = spans.filter((s) => s.page === page && s.bbox.length === 4);
  return (
    <div aria-hidden="true" data-testid="hidden-overlay" className="pointer-events-none absolute inset-0">
      {boxes.map((s, i) => {
        const [x0, top, x1, bottom] = s.bbox;
        const pageSize = { width: s.page_width || A4.width, height: s.page_height || A4.height };
        const clamp = (v: number) => Math.max(0, Math.min(100, v));
        const left = clamp((x0 / pageSize.width) * 100);
        const t = clamp((top / pageSize.height) * 100);
        const w = Math.max(1.5, clamp(((x1 - x0) / pageSize.width) * 100));
        const h = Math.max(1, clamp(((bottom - top) / pageSize.height) * 100));
        return (
          <div
            key={i}
            data-testid="hidden-box"
            style={{ left: `${left}%`, top: `${t}%`, width: `${Math.min(w, 100 - left)}%`, height: `${Math.min(h, 100 - t)}%` }}
            className="absolute rounded-sm border-2 border-danger bg-danger/20"
          />
        );
      })}
    </div>
  );
}
