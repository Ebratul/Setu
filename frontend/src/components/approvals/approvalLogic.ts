/** Pure helpers for the approval dialogs (kept free of React so they are unit-testable). */

export const RING_RADIUS = 44;
export const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

/** Seconds left from the server value at fetch time, never negative. */
export function secondsLeft(serverSeconds: number | null | undefined, fetchedAt: number, now: number): number {
  if (serverSeconds == null) return 0;
  return Math.max(0, Math.ceil(serverSeconds - (now - fetchedAt) / 1000));
}

/** Fraction of the cooling-off already elapsed (0..1) and the matching stroke-dashoffset. */
export function ringState(left: number, total: number | null | undefined) {
  const tot = total && total > 0 ? total : 0;
  const elapsed = tot === 0 ? 1 : Math.min(1, Math.max(0, (tot - left) / tot));
  return { elapsed, dashoffset: RING_CIRCUMFERENCE * (1 - elapsed) };
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export const OTP_LENGTH = 6;

/** Tier 3 approve is possible only after the pause, with all 6 digits, and while not locked. */
export function canSubmitOtp(args: { left: number; code: string; locked: boolean; busy: boolean }): boolean {
  return args.left === 0 && /^\d{6}$/.test(args.code) && !args.locked && !args.busy;
}

/** Normalise pasted text into at most 6 digits. */
export function digitsOnly(text: string): string {
  return text.replace(/\D/g, "").slice(0, OTP_LENGTH);
}
