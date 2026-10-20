"use client";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

import { SPEEDS, type Speed } from "./demoModel";

type Props = {
  started: boolean;
  busy: boolean;
  playing: boolean;
  speed: Speed;
  canPrev: boolean;
  canNext: boolean;
  showSpeed: boolean;
  onStart: () => void;
  onPrev: () => void;
  onNext: () => void;
  onTogglePlay: () => void;
  onSpeed: (s: Speed) => void;
};

/** Primary demo controls: Start / Previous / Next / Auto-play-Pause and the 1x-1.5x-2x speed. */
export function Controls({ started, busy, playing, speed, canPrev, canNext, showSpeed, onStart, onPrev, onNext, onTogglePlay, onSpeed }: Props) {
  const t = useT();
  return (
    <div role="group" aria-label={t("demo.controls.label")} className="flex flex-wrap items-center gap-2">
      {!started ? (
        <Button onClick={onStart} disabled={busy}>
          <Icon name="play" size={14} />
          {t("demo.controls.start")}
        </Button>
      ) : null}
      <Button variant="secondary" onClick={onPrev} disabled={!canPrev || busy}>
        <Icon name="arrow" size={14} className="rotate-180 rtl:rotate-0" />
        {t("demo.controls.prev")}
      </Button>
      <Button onClick={onNext} disabled={!canNext || busy}>
        {t("demo.controls.next")}
        <Icon name="arrow" size={14} className="rtl:rotate-180" />
      </Button>
      <Button variant={playing ? "accent" : "secondary"} onClick={onTogglePlay} aria-pressed={playing}>
        {playing ? t("demo.controls.pause") : t("demo.controls.autoplay")}
      </Button>
      {showSpeed ? (
        <div role="radiogroup" aria-label={t("demo.controls.speed")} className="inline-flex rounded-xl border border-line bg-surface p-1">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={speed === s}
              onClick={() => onSpeed(s)}
              className={`min-h-9 rounded-lg px-2.5 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none ${
                speed === s ? "bg-brand-700 text-white" : "text-muted hover:text-ink"
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
