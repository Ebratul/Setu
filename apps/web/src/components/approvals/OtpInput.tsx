"use client";

import { useId, useRef, type ClipboardEvent, type KeyboardEvent } from "react";

import { useT } from "@/i18n";

import { OTP_LENGTH, digitsOnly } from "./approvalLogic";

type Props = {
  value: string;
  onChange: (value: string) => void;
  label: string;
  help?: string;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
};

/** Six single-digit boxes: auto-advance, backspace goes back, paste/fill spreads the digits. */
export function OtpInput({ value, onChange, label, help, disabled, invalid, describedBy }: Props) {
  const t = useT();
  const labelId = useId();
  const helpId = useId();
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length: OTP_LENGTH }, (_, i) => value[i] ?? "");

  const focus = (i: number) => refs.current[Math.min(Math.max(i, 0), OTP_LENGTH - 1)]?.focus();

  function spread(from: number, text: string) {
    const typed = digitsOnly(text);
    if (!typed) return;
    const next = (value.slice(0, from) + typed).slice(0, OTP_LENGTH);
    onChange(next);
    focus(Math.min(from + typed.length, OTP_LENGTH - 1));
  }

  function setAt(i: number, raw: string) {
    const typed = digitsOnly(raw);
    if (typed === "") {
      if (raw === "") {
        const arr = [...digits];
        arr[i] = "";
        onChange(arr.join("").slice(0, OTP_LENGTH));
      }
      return;
    }
    if (typed.length > 1) {
      spread(0, typed);
      return;
    }
    const arr = [...digits];
    arr[i] = typed;
    onChange(arr.join("").replace(/\s/g, ""));
    if (i < OTP_LENGTH - 1) focus(i + 1);
  }

  function onKeyDown(i: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && digits[i] === "" && i > 0) {
      e.preventDefault();
      const arr = [...digits];
      arr[i - 1] = "";
      onChange(arr.join("").slice(0, OTP_LENGTH));
      focus(i - 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      focus(i - 1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      focus(i + 1);
    }
  }

  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    e.preventDefault();
    spread(0, e.clipboardData.getData("text"));
  }

  return (
    <div data-demo="otp-input">
      <p id={labelId} className="mb-1 text-sm font-medium text-ink">
        {label}
      </p>
      <div
        role="group"
        aria-labelledby={labelId}
        aria-describedby={[help ? helpId : "", describedBy ?? ""].filter(Boolean).join(" ") || undefined}
        data-testid="otp-input"
        className="flex gap-2"
      >
        {digits.map((d, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="text"
            inputMode="numeric"
            autoComplete="off"
            pattern="[0-9]*"
            value={d}
            disabled={disabled}
            aria-label={t("appr.t3.otpDigit", { n: i + 1 })}
            aria-invalid={invalid ? true : undefined}
            onChange={(e) => setAt(i, e.target.value)}
            onKeyDown={(e) => onKeyDown(i, e)}
            onPaste={onPaste}
            onFocus={(e) => e.currentTarget.select()}
            className="h-12 w-10 min-w-0 rounded-xl border border-muted bg-surface text-center text-xl font-bold text-ink tabular-nums focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none disabled:opacity-50 aria-[invalid=true]:border-danger sm:w-12"
          />
        ))}
      </div>
      {help ? (
        <p id={helpId} className="mt-1 text-xs text-muted">
          {help}
        </p>
      ) : null}
    </div>
  );
}
