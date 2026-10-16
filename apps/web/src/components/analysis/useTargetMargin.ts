"use client";

import { useState } from "react";

import { useT } from "@/i18n";
import { useDebounced } from "@/lib/useApi";

const VALID = /^\d{1,2}(\.\d{1,4})?$/;

/** Target-margin text input state: only a well-formed, debounced value is ever sent to the API. */
export function useTargetMargin() {
  const t = useT();
  const [value, setValue] = useState("");
  const trimmed = value.trim();
  const debounced = useDebounced(trimmed);
  const valid = trimmed === "" || VALID.test(trimmed);
  return {
    value,
    setValue,
    error: valid ? null : t("analysis.target.invalid"),
    request:
      valid && debounced !== "" && VALID.test(debounced)
        ? debounced
        : undefined,
    updating: valid && debounced !== trimmed,
  };
}
