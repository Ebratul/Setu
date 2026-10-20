"use client";

import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { useT } from "@/i18n";
import { apiBlob } from "@/lib/api/client";
import { documentUrl, type DocumentOut } from "@/lib/api/onboarding";
import { apiErrorText } from "@/lib/api/formErrors";

type Props = { doc: DocumentOut; onClose: () => void };

export function DocumentViewer({ doc, onClose }: Props) {
  const t = useT();
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    let made: string | null = null;
    documentUrl(doc.id)
      .then((r) => apiBlob(r.url))
      .then(
        (blob) => {
          made = URL.createObjectURL(blob);
          if (live) setUrl(made);
        },
        (e: unknown) => live && setError(apiErrorText(e, t, "vq.err")),
      );
    return () => {
      live = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [doc.id, t]);

  const image = doc.mime.startsWith("image/");
  return (
    <Modal title={`${t(`ob.doc.${doc.type}`)}: ${doc.original_name}`} onClose={onClose} size="xl">
      {error ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {error}
        </p>
      ) : !url ? (
        <p role="status">{t("common.loading")}</p>
      ) : (
        <div className="space-y-3">
          {image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={`${t(`ob.doc.${doc.type}`)}`} className="mx-auto max-h-[70vh] rounded-xl border border-line" />
          ) : (
            <iframe src={url} title={doc.original_name} className="h-[70vh] w-full rounded-xl border border-line" />
          )}
          <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500">
            {t("vq.doc.openTab")}
          </a>
        </div>
      )}
    </Modal>
  );
}
