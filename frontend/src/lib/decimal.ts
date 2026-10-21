/** Exact decimal-string arithmetic for form previews (BigInt based, no floating point). */

const DEC = /^\d{1,14}(\.\d{1,4})?$/;

export function isDecimal(value: string): boolean {
  return DEC.test(value.trim());
}

function parts(value: string): { digits: bigint; scale: number } {
  const [whole, frac = ""] = value.trim().split(".");
  return { digits: BigInt(`${whole}${frac}`), scale: frac.length };
}

function render(digits: bigint, scale: number, minFrac: number): string {
  let s = digits.toString().padStart(scale + 1, "0");
  const whole = s.slice(0, s.length - scale);
  let frac = scale > 0 ? s.slice(s.length - scale) : "";
  frac = frac.replace(/0+$/, "").padEnd(minFrac, "0");
  s = frac ? `${whole}.${frac}` : whole;
  return s;
}

/** Exact product of two non-negative decimal strings, at least 2 decimals. Null on bad input. */
export function mulDecimal(a: string, b: string): string | null {
  if (!isDecimal(a) || !isDecimal(b)) return null;
  const x = parts(a);
  const y = parts(b);
  return render(x.digits * y.digits, x.scale + y.scale, 2);
}

/** True when the decimal string is zero. */
export function isZero(value: string): boolean {
  return isDecimal(value) && /^0*(\.0*)?$/.test(value.trim());
}

/** Sum of percent strings (exact), at least 0 decimals; null on bad input. */
export function sumDecimals(values: string[]): string | null {
  let scale = 0;
  const ps = values.map((v) => (isDecimal(v) ? parts(v) : null));
  if (ps.some((p) => p === null)) return null;
  for (const p of ps) scale = Math.max(scale, p!.scale);
  let total = BigInt(0);
  for (const p of ps) total += p!.digits * BigInt(10) ** BigInt(scale - p!.scale);
  return render(total, scale, 0);
}
