"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";
import { useDialog } from "@/lib/useDialog";

export const CHAT_WIDTH_KEY = "setu_chat_w";
export const MIN_W = 360;
export const MAX_W = 900;
export const DEFAULT_W = 480;
const STEP = 24;

export function clampWidth(w: number, viewport: number): number {
  const max = Math.max(MIN_W, Math.min(MAX_W, viewport - 64));
  return Math.round(Math.min(max, Math.max(MIN_W, w)));
}

type Props = { title: string; onClose: () => void; children: ReactNode };

/** Right-hand chat dialog: full width on phones, drag/keyboard resizable (and remembered) from sm up. */
export function ChatSheet({ title, onClose, children }: Props) {
  const t = useT();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(DEFAULT_W);
  useDialog(panel, onClose);

  useEffect(() => {
    const id = setTimeout(() => {
      try {
        const v = Number(localStorage.getItem(CHAT_WIDTH_KEY));
        if (Number.isFinite(v) && v > 0) setWidth(clampWidth(v, window.innerWidth));
      } catch {
        /* storage unavailable */
      }
    }, 0);
    return () => clearTimeout(id);
  }, []);

  const commit = useCallback((w: number) => {
    const next = clampWidth(w, window.innerWidth);
    setWidth(next);
    try {
      localStorage.setItem(CHAT_WIDTH_KEY, String(next));
    } catch {
      /* storage unavailable */
    }
  }, []);

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    const handle = e.currentTarget;
    handle.setPointerCapture?.(e.pointerId);
    const move = (ev: PointerEvent) => setWidth(clampWidth(window.innerWidth - ev.clientX, window.innerWidth));
    const up = (ev: PointerEvent) => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      commit(window.innerWidth - ev.clientX);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    // The panel sits on the right edge, so Left widens and Right narrows.
    if (e.key === "ArrowLeft") commit(width + STEP);
    else if (e.key === "ArrowRight") commit(width - STEP);
    else if (e.key === "Home") commit(MIN_W);
    else if (e.key === "End") commit(MAX_W);
    else return;
    e.preventDefault();
  }

  return (
    <div className="fixed inset-0 z-50 bg-scrim" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="chat-sheet"
        style={{ "--chat-w": `${width}px` } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
        className="anim-drawer absolute inset-y-0 right-0 flex w-full flex-col bg-surface shadow-pop focus:outline-none sm:w-(--chat-w)"
      >
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t("chatx.resize")}
          aria-valuemin={MIN_W}
          aria-valuemax={MAX_W}
          aria-valuenow={width}
          tabIndex={0}
          onPointerDown={onPointerDown}
          onKeyDown={onKeyDown}
          className="absolute inset-y-0 left-0 hidden w-3 -translate-x-1/2 cursor-col-resize touch-none items-center justify-center rounded-full hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none sm:flex"
        >
          <span aria-hidden="true" className="h-10 w-1 rounded-full bg-line" />
        </div>
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h2 id={titleId} className="text-lg font-bold text-ink">
            {title}
          </h2>
          <button
            type="button"
            aria-label={t("common.close")}
            onClick={onClose}
            className="flex size-11 items-center justify-center rounded-lg text-muted hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
          >
            <Icon name="x" />
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col p-4">{children}</div>
      </div>
    </div>
  );
}
