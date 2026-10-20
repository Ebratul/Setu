"use client";

import { useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";
import { useDialog } from "@/lib/useDialog";

type Props = {
  name: string;
  alt: string;
  caption?: string;
  lang?: string;
  /** Used by the screenshot script only. */
  route?: string;
  as?: string;
  wait?: string;
  click?: string;
};

export function Screenshot({ name, alt, caption, lang = "en" }: Props) {
  const t = useT();
  const [src, setSrc] = useState(`/docs-images/${lang}/${name}.png`);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  function onError() {
    const fallback = `/docs-images/en/${name}.png`;
    if (src !== fallback) setSrc(fallback);
    else setFailed(true);
  }

  return (
    <figure className="not-prose my-4" data-screenshot={name}>
      {failed ? (
        <div
          role="img"
          aria-label={alt}
          className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-card border border-dashed border-line bg-surface-alt p-6 text-center text-sm text-muted"
        >
          <Icon name="panel" size={24} />
          <span>{t("docs.shot.pending")}</span>
          <span className="max-w-prose">{alt}</span>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={t("docs.shot.zoom", { alt })}
          className="block w-full cursor-zoom-in overflow-hidden rounded-card border border-line shadow-card focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- generated static PNGs of unknown size */}
          <img src={src} alt={alt} loading="lazy" onError={onError} className="h-auto w-full" />
        </button>
      )}
      {caption ? <figcaption className="mt-2 text-sm text-muted">{caption}</figcaption> : null}
      {open ? <Zoom src={src} alt={alt} panel={panel} onClose={() => setOpen(false)} /> : null}
    </figure>
  );
}

function Zoom({
  src,
  alt,
  panel,
  onClose,
}: {
  src: string;
  alt: string;
  panel: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
}) {
  const t = useT();
  useDialog(panel, onClose);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim p-4" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={alt}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="relative max-h-full max-w-6xl overflow-auto rounded-card bg-surface p-2 shadow-pop focus:outline-none"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label={t("docs.shot.close")}
          className="absolute top-2 right-2 flex size-11 items-center justify-center rounded-lg bg-surface text-ink shadow-card focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        >
          <Icon name="x" />
        </button>
        {/* eslint-disable-next-line @next/next/no-img-element -- generated static PNGs of unknown size */}
        <img src={src} alt={alt} className="h-auto w-full" />
      </div>
    </div>
  );
}
