"use client";

import { useCallback, useState, type ReactNode } from "react";

import { usePrefersReducedMotion } from "@/components/landing/usePrefersReducedMotion";
import { useT } from "@/i18n";

import { embedUrl } from "./demoModel";
import { SpotlightOverlay } from "./SpotlightOverlay";
import { useSpotlightTarget } from "./useSpotlightTarget";

type Props = {
  url: string | null;
  frameKey: string;
  highlight: string | null | undefined;
  caption: string;
  busy: boolean;
  spotlightOn: boolean;
  /** Must be referentially stable (e.g. a state setter). */
  frameRef?: (el: HTMLIFrameElement | null) => void;
  empty: ReactNode;
};

/** The embedded real app plus the spotlight overlay. Same origin, so the highlight is looked up in the frame. */
export function Stage({ url, frameKey, highlight, caption, busy, spotlightOn, frameRef, empty }: Props) {
  const t = useT();
  const reduced = usePrefersReducedMotion();
  const [frame, setFrame] = useState<HTMLIFrameElement | null>(null);
  const setRef = useCallback(
    (el: HTMLIFrameElement | null) => {
      setFrame(el);
      frameRef?.(el);
    },
    [frameRef],
  );
  const target = useSpotlightTarget(frame, url ? highlight : null, frameKey, reduced);

  return (
    <div className="relative h-full w-full overflow-hidden bg-surface-alt" data-testid="demo-stage">
      {url ? (
        <iframe
          key={frameKey}
          ref={setRef}
          src={embedUrl(url)}
          title={t("demo.stage.frame")}
          className="absolute inset-0 h-full w-full border-0 bg-surface"
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center p-6 text-center">{empty}</div>
      )}
      {url && spotlightOn && !busy ? (
        <SpotlightOverlay rect={target.rect} missing={target.missing} size={target.size} caption={caption} reducedMotion={reduced} />
      ) : null}
      {busy ? (
        <div className="absolute inset-0 flex items-center justify-center bg-scrim" data-testid="stage-busy">
          <p role="status" className="flex items-center gap-3 rounded-xl bg-surface px-4 py-3 text-sm font-semibold text-ink shadow-card-hover">
            <span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-brand-700 border-t-transparent motion-reduce:animate-none" />
            {t("demo.stage.busy")}
          </p>
        </div>
      ) : null}
    </div>
  );
}
