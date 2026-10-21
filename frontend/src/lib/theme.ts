export type ThemeChoice = "system" | "light" | "dark";
export const THEME_KEY = "setu_theme";

export function resolveTheme(choice: ThemeChoice, prefersDark: boolean): "light" | "dark" {
  if (choice === "system") return prefersDark ? "dark" : "light";
  return choice;
}

export function readThemeChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* storage unavailable */
  }
  return "system";
}

export function applyTheme(choice: ThemeChoice) {
  const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  document.documentElement.dataset.theme = resolveTheme(choice, dark);
  try {
    localStorage.setItem(THEME_KEY, choice);
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event("setu-theme"));
}

/** Runs before first paint to avoid a flash; mirrors resolveTheme. */
export const THEME_INIT_SCRIPT = `try{var c=localStorage.getItem("${THEME_KEY}")||"system";var d=window.matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.dataset.theme=c==="system"?(d?"dark":"light"):c;}catch(e){}`;
