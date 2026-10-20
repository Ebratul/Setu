"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";

type Props = {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  /** Bump to move focus into the textarea (new chat, thread opened). */
  focusSignal?: number;
  initial?: string;
};

export function Composer({ busy, onSend, onStop, focusSignal = 0, initial }: Props) {
  const t = useT();
  const id = useId();
  const [text, setText] = useState(initial ?? "");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, [focusSignal]);

  function submit() {
    const v = text.trim();
    if (!v || busy) return;
    onSend(v);
    setText("");
    ref.current?.focus();
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex items-end gap-2"
    >
      <div className="min-w-0 flex-1">
        <label htmlFor={id} className="sr-only">
          {t("chat.input.label")}
        </label>
        <textarea
          id={id}
          ref={ref}
          rows={2}
          maxLength={4000}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t("chat.input.placeholder")}
          aria-describedby={`${id}-hint`}
          className="block max-h-40 min-h-12 w-full resize-y rounded-xl border border-muted bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        />
        <p id={`${id}-hint`} className="sr-only">
          {t("chat.input.hint")}
        </p>
      </div>
      {busy ? (
        <Button variant="secondary" onClick={onStop}>
          {t("chat.stop")}
        </Button>
      ) : (
        <Button type="submit" disabled={text.trim() === ""}>
          {t("chat.send")}
        </Button>
      )}
    </form>
  );
}
