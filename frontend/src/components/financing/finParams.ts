import { INPUT_DECIMAL, type Currency } from "@/lib/format";
import type { FinMode } from "@/lib/api/financing";

export type FinParams = {
  mode: FinMode;
  deal: string | undefined;
  amount: string | undefined;
  date: string | undefined;
  currency: Currency | undefined;
};

type Getter = { get: (key: string) => string | null };

/** Parse /app/financing query params; the dashboard alert link means shortfall mode with a prefilled amount. */
export function parseFinParams(params: Getter): FinParams {
  const rawMode = params.get("mode");
  const mode: FinMode =
    rawMode === "order" && params.get("prefill") !== "shortfall"
      ? "order"
      : "shortfall";
  const rawAmount = params.get("amount") ?? "";
  const rawDate = params.get("date") ?? "";
  const rawCur = params.get("currency");
  const rawDeal = params.get("deal") ?? "";
  return {
    mode,
    deal: /^[\w.-]{1,64}$/.test(rawDeal) ? rawDeal : undefined,
    amount: INPUT_DECIMAL.test(rawAmount) ? rawAmount : undefined,
    date: /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : undefined,
    currency:
      rawCur === "USD" || rawCur === "BDT" || rawCur === "CNY"
        ? rawCur
        : undefined,
  };
}
