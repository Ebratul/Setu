export type Rect = { left: number; top: number; width: number; height: number };
export type Size = { width: number; height: number };

export type Spotlight =
  | { mode: "center"; bubble: Rect }
  | { mode: "cutout"; hole: Rect; bubble: Rect; placement: "below" | "above" | "right" | "left" | "inside" };

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), Math.max(lo, hi));

/**
 * Pure geometry for the tour overlay. `target` is the element rect in stage coordinates (null when the
 * selector was not found). Returns a padded cut-out clipped to the stage and a caption bubble placed
 * below, above, beside or inside it, always fully inside the stage.
 */
export function computeSpotlight(
  target: Rect | null,
  stage: Size,
  bubbleSize: Size,
  pad = 8,
  gap = 12,
  margin = 8,
): Spotlight {
  const bw = Math.min(bubbleSize.width, Math.max(0, stage.width - margin * 2));
  const bh = Math.min(bubbleSize.height, Math.max(0, stage.height - margin * 2));
  if (!target || target.width <= 0 || target.height <= 0) {
    return {
      mode: "center",
      bubble: { left: (stage.width - bw) / 2, top: (stage.height - bh) / 2, width: bw, height: bh },
    };
  }
  const left = clamp(target.left - pad, 0, stage.width);
  const top = clamp(target.top - pad, 0, stage.height);
  const right = clamp(target.left + target.width + pad, 0, stage.width);
  const bottom = clamp(target.top + target.height + pad, 0, stage.height);
  const hole: Rect = { left, top, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
  if (hole.width === 0 || hole.height === 0) {
    return {
      mode: "center",
      bubble: { left: (stage.width - bw) / 2, top: (stage.height - bh) / 2, width: bw, height: bh },
    };
  }
  const cx = clamp(hole.left + hole.width / 2 - bw / 2, margin, stage.width - bw - margin);
  const cy = clamp(hole.top + hole.height / 2 - bh / 2, margin, stage.height - bh - margin);
  const below = stage.height - (hole.top + hole.height) - gap - margin;
  const above = hole.top - gap - margin;
  const rightRoom = stage.width - (hole.left + hole.width) - gap - margin;
  const leftRoom = hole.left - gap - margin;
  if (below >= bh) {
    return { mode: "cutout", hole, placement: "below", bubble: { left: cx, top: hole.top + hole.height + gap, width: bw, height: bh } };
  }
  if (above >= bh) {
    return { mode: "cutout", hole, placement: "above", bubble: { left: cx, top: hole.top - gap - bh, width: bw, height: bh } };
  }
  if (rightRoom >= bw) {
    return { mode: "cutout", hole, placement: "right", bubble: { left: hole.left + hole.width + gap, top: cy, width: bw, height: bh } };
  }
  if (leftRoom >= bw) {
    return { mode: "cutout", hole, placement: "left", bubble: { left: hole.left - gap - bw, top: cy, width: bw, height: bh } };
  }
  return {
    mode: "cutout",
    hole,
    placement: "inside",
    bubble: { left: cx, top: clamp(stage.height - bh - margin, margin, stage.height), width: bw, height: bh },
  };
}

/** Scale that fits a fixed 1920x1080 stage into the viewport. */
export function fitScale(viewport: Size, design: Size = { width: 1920, height: 1080 }): number {
  if (viewport.width <= 0 || viewport.height <= 0) return 1;
  return Math.min(viewport.width / design.width, viewport.height / design.height);
}
