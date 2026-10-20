export type PresenterAction = "next" | "prev" | "toggle" | "reset" | "blackout" | "notes" | "fullscreen";

type KeyLike = {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  target?: EventTarget | null;
};

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/** True when the key press happened while the user is typing (or on a control that owns the key). */
export function isTypingTarget(target: EventTarget | null | undefined): boolean {
  const el = target as { tagName?: string; isContentEditable?: boolean; getAttribute?: (n: string) => string | null } | null;
  if (!el || typeof el.tagName !== "string") return false;
  if (TYPING.has(el.tagName.toUpperCase())) return true;
  if (el.isContentEditable) return true;
  const role = el.getAttribute?.("role");
  return role === "textbox" || role === "combobox" || role === "searchbox";
}

/** Maps a key press to a presenter action; null when it must be ignored (modifiers, typing). */
export function presenterAction(e: KeyLike): PresenterAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;
  if (isTypingTarget(e.target)) return null;
  switch (e.key) {
    case "ArrowRight":
      return "next";
    case "ArrowLeft":
      return "prev";
    case " ":
    case "Spacebar": {
      const tag = (e.target as { tagName?: string } | null)?.tagName?.toUpperCase();
      // Space activates a focused button, link or disclosure natively.
      return tag === "BUTTON" || tag === "A" || tag === "SUMMARY" ? null : "toggle";
    }
    case "r":
    case "R":
      return "reset";
    case "b":
    case "B":
      return "blackout";
    case "n":
    case "N":
      return "notes";
    case "f":
    case "F":
      return "fullscreen";
    default:
      return null;
  }
}
