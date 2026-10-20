"use client";

import { computeSpotlight, type Rect, type Size } from "./spotlight";

type Props = {
  rect: Rect | null;
  missing: boolean;
  size: Size | null;
  caption: string;
  /** Bubble is a visual duplicate of the live caption in the narration panel. */
  reducedMotion: boolean;
};

const BUBBLE_MAX = 340;

function estimateBubble(stage: Size, caption: string): Size {
  const width = Math.max(120, Math.min(BUBBLE_MAX, stage.width - 16));
  const perLine = Math.max(10, Math.floor((width - 28) / 7.5));
  const lines = Math.max(1, Math.ceil(caption.length / perLine));
  return { width, height: 28 + lines * 22 };
}

/** Dimmed page with a rounded cut-out and a caption bubble; never intercepts pointer events. */
export function SpotlightOverlay({ rect, missing, size, caption, reducedMotion }: Props) {
  if (!size || size.width === 0 || (!rect && !missing)) return null;
  const spot = computeSpotlight(rect, size, estimateBubble(size, caption));
  const move = reducedMotion ? "" : "transition-[left,top,width,height] duration-300 ease-out";
  const b = spot.bubble;
  return (
    <div aria-hidden="true" data-testid="spotlight" data-mode={spot.mode} className="pointer-events-none absolute inset-0 overflow-hidden">
      {spot.mode === "cutout" ? (
        <div
          data-testid="spotlight-hole"
          className={`absolute rounded-xl ring-2 ring-accent-400 shadow-[0_0_0_9999px_var(--color-scrim)] ${move}`}
          style={{ left: spot.hole.left, top: spot.hole.top, width: spot.hole.width, height: spot.hole.height }}
        />
      ) : (
        <div className="absolute inset-0 bg-scrim" />
      )}
      {caption ? (
        <p
          data-testid="spotlight-bubble"
          className={`absolute rounded-xl border border-line bg-surface p-3 text-sm leading-snug font-semibold text-ink shadow-card-hover ${move}`}
          style={{ left: b.left, top: b.top, width: b.width }}
        >
          {caption}
        </p>
      ) : null}
    </div>
  );
}
