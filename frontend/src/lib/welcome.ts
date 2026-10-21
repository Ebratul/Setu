const SEEN = "setu_onboarding_seen";
const doneKey = (userId: string) => `setu_welcome_done:${userId}`;

function safe<T>(fn: () => T, fallback: T): T {
  try {
    return fn();
  } catch {
    return fallback;
  }
}

/** Called while an account is still being verified, so the welcome tour only shows to people who went through onboarding. */
export function markOnboardingSeen() {
  safe(() => localStorage.setItem(SEEN, "1"), undefined);
}

export function shouldShowWelcome(userId: string): boolean {
  return safe(
    () =>
      localStorage.getItem(SEEN) === "1" &&
      localStorage.getItem(doneKey(userId)) !== "1",
    false,
  );
}

export function dismissWelcome(userId: string) {
  safe(() => {
    localStorage.setItem(doneKey(userId), "1");
    localStorage.removeItem(SEEN);
  }, undefined);
}
