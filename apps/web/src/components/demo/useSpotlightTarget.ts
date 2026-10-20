"use client";

import { useEffect, useState } from "react";

import type { Rect, Size } from "./spotlight";

export const FIND_TIMEOUT_MS = 6000;

type State = { key: string; rect: Rect | null; missing: boolean; size: Size | null };

const same = (a: Rect | null, b: Rect | null) =>
  a === b || (!!a && !!b && a.left === b.left && a.top === b.top && a.width === b.width && a.height === b.height);

/**
 * Finds `selector` inside the (same-origin) iframe and tracks its rect in iframe coordinates. Polls every
 * 250 ms and reacts to DOM mutations, so it follows client-side navigations, late data and layout shifts.
 * `missing` turns true when nothing matched within 6 s of the latest load.
 */
export function useSpotlightTarget(
  frame: HTMLIFrameElement | null,
  selector: string | null | undefined,
  resetKey: string,
  reducedMotion: boolean,
) {
  const [state, setState] = useState<State>({ key: "", rect: null, missing: false, size: null });

  useEffect(() => {
    if (!frame) return;
    let el: Element | null = null;
    let scrolled = false;
    let startedAt = Date.now();
    let raf = 0;
    let observer: MutationObserver | null = null;

    const report = (rect: Rect | null, missing: boolean) => {
      const size = { width: frame.offsetWidth, height: frame.offsetHeight };
      setState((prev) =>
        prev.key === resetKey &&
        same(prev.rect, rect) &&
        prev.missing === missing &&
        prev.size?.width === size.width &&
        prev.size?.height === size.height
          ? prev
          : { key: resetKey, rect, missing, size },
      );
    };

    const tick = () => {
      let doc: Document | null = null;
      try {
        doc = frame.contentDocument;
      } catch {
        doc = null;
      }
      const timedOut = Date.now() - startedAt > FIND_TIMEOUT_MS;
      if (!selector) return report(null, true);
      if (!doc?.body) return report(null, timedOut);
      if (!el || !el.isConnected) {
        try {
          el = doc.querySelector(selector);
        } catch {
          el = null;
        }
        scrolled = false;
      }
      if (!el) return report(null, timedOut);
      if (!scrolled) {
        scrolled = true;
        // Scroll only the frame's own window: element.scrollIntoView would also scroll the parent page.
        const win = el.ownerDocument.defaultView;
        const box = el.getBoundingClientRect();
        if (win && (box.top < 0 || box.bottom > win.innerHeight)) {
          win.scrollTo({ top: win.scrollY + box.top - (win.innerHeight - box.height) / 2, behavior: reducedMotion ? "auto" : "smooth" });
        }
      }
      const r = el.getBoundingClientRect();
      report({ left: r.left, top: r.top, width: r.width, height: r.height }, false);
    };

    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tick);
    };

    const attach = () => {
      observer?.disconnect();
      try {
        const root = frame.contentDocument?.documentElement;
        if (root) {
          observer = new MutationObserver(schedule);
          observer.observe(root, { childList: true, subtree: true, attributes: true, characterData: true });
        }
      } catch {
        /* cross-origin: polling only */
      }
    };

    const onLoad = () => {
      startedAt = Date.now();
      el = null;
      attach();
      tick();
    };

    attach();
    tick();
    const id = setInterval(tick, 250);
    frame.addEventListener("load", onLoad);
    window.addEventListener("resize", schedule);
    return () => {
      clearInterval(id);
      cancelAnimationFrame(raf);
      observer?.disconnect();
      frame.removeEventListener("load", onLoad);
      window.removeEventListener("resize", schedule);
    };
  }, [frame, selector, resetKey, reducedMotion]);

  return state.key === resetKey ? state : { key: resetKey, rect: null, missing: false, size: null };
}
