"use client";

import { useSyncExternalStore } from "react";

import { getDigits, setDigits, subscribeDigits, type DigitsPref } from "./format";

/** Subscribes a component to the digit-style preference; formatters stay pure and read the same setting. */
export function useDigits(): [DigitsPref, (d: DigitsPref) => void] {
  const d = useSyncExternalStore(subscribeDigits, getDigits, () => "native" as DigitsPref);
  return [d, setDigits];
}
