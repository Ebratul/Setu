/** Keyboard shortcuts, documented here so the accessibility page can list them. */
export type Shortcut = { keys: string[]; labelKey: string };

export const SHORTCUTS: readonly Shortcut[] = [
  { keys: ["Ctrl/⌘", "K"], labelKey: "shortcuts.palette" },
  { keys: ["/"], labelKey: "shortcuts.chat" },
  { keys: ["Esc"], labelKey: "shortcuts.close" },
];

/** True when the event target is somewhere the user is typing (so single-key shortcuts must not fire). */
export function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

export const OPEN_CHAT_EVENT = "setu-open-chat";
export const OPEN_PALETTE_EVENT = "setu-open-palette";

export function openChat() {
  window.dispatchEvent(new Event(OPEN_CHAT_EVENT));
}

export function openPalette() {
  window.dispatchEvent(new Event(OPEN_PALETTE_EVENT));
}
