import { useEffect, useRef, type RefObject } from "react";

/** Open dialogs, innermost last: only the top one reacts to Esc / Tab. */
const openDialogs: symbol[] = [];

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Focus trap, Esc to close and focus return to the opener for any modal-like surface. */
export function useDialog(
  panel: RefObject<HTMLElement | null>,
  onClose: () => void,
  closeDisabled?: boolean,
) {
  const onCloseRef = useRef(onClose);
  const disabledRef = useRef(closeDisabled);
  useEffect(() => {
    onCloseRef.current = onClose;
    disabledRef.current = closeDisabled;
  });

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const el = panel.current;
    el?.focus();
    const me = Symbol("dialog");
    openDialogs.push(me);
    function onKey(e: KeyboardEvent) {
      if (!el || openDialogs[openDialogs.length - 1] !== me) return;
      if (e.key === "Escape") {
        if (!disabledRef.current) onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const items = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === el)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      } else if (!el.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const at = openDialogs.indexOf(me);
      if (at !== -1) openDialogs.splice(at, 1);
      opener?.focus?.();
    };
  }, [panel]);
}
