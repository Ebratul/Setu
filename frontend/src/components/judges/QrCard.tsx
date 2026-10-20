"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { downloadHref, downloadSvg, qrPngDataUrl, qrSvg } from "@/lib/qr";

type Props = { label: string; url: string; slug: string };

/** One labelled QR code, generated in the browser as a self-contained SVG, with PNG/SVG download. */
export function QrCard({ label, url, slug }: Props) {
  const t = useT();
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    qrSvg(url)
      .then((s) => live && setSvg(s))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [url]);

  const alt = t("judges.qr.alt", { label, url });
  return (
    <figure className="qr-card grid justify-items-center gap-3 rounded-2xl border border-line bg-surface p-4 text-center">
      {svg ? (
        <div
          role="img"
          aria-label={alt}
          data-testid={`qr-${slug}`}
          className="size-44 [&>svg]:size-full"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        <div className="size-44 rounded-lg bg-surface-alt" aria-hidden="true" />
      )}
      <figcaption className="grid gap-1">
        <span className="font-semibold text-ink">{label}</span>
        <span className="text-xs break-all text-muted">{url}</span>
      </figcaption>
      {failed ? (
        <p role="alert" className="text-sm text-danger">
          {t("judges.qr.fail")}
        </p>
      ) : null}
      <div className="qr-actions flex flex-wrap justify-center gap-2 print:hidden">
        <Button
          size="sm"
          variant="secondary"
          disabled={!svg}
          aria-label={t("judges.qr.dl", { kind: "PNG", label })}
          onClick={async () =>
            downloadHref(await qrPngDataUrl(url), `setu-${slug}-qr.png`)
          }
        >
          {t("judges.qr.png")}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={!svg}
          aria-label={t("judges.qr.dl", { kind: "SVG", label })}
          onClick={() => svg && downloadSvg(svg, `setu-${slug}-qr.svg`)}
        >
          {t("judges.qr.svg")}
        </Button>
      </div>
    </figure>
  );
}
