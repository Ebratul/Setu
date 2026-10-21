"use client";

import { useRef, useState } from "react";

import { Badge, type Tone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { apiErrorText } from "@/lib/api/formErrors";
import { deleteDocument, uploadDocument, type DocType, type DocStatus } from "@/lib/api/onboarding";
import { docsDone } from "@/lib/onboarding/steps";
import { MAX_UPLOAD_BYTES, OPTIONAL_DOCS, REQUIRED_DOCS, validateFile } from "@/lib/onboarding/validate";

import type { StepProps } from "./types";

const TONE: Record<DocStatus, Tone> = { UPLOADED: "info", VERIFIED: "success", REJECTED: "danger" };

function size(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function DocumentsStep({ state, onState, onNext }: StepProps) {
  const t = useT();
  const role = state.role === "SUPPLIER" ? "SUPPLIER" : "BUYER";
  const [busyType, setBusyType] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});

  const setErr = (type: string, msg: string | null) =>
    setErrors((e) => {
      const next = { ...e };
      if (msg) next[type] = msg;
      else delete next[type];
      return next;
    });

  async function onPick(type: DocType, file: File | undefined) {
    if (!file) return;
    const bad = validateFile(file);
    if (bad) {
      setErr(type, t(bad.key));
      return;
    }
    setBusyType(type);
    setErr(type, null);
    try {
      const doc = await uploadDocument(type, file);
      onState({ ...state, documents: [...state.documents.filter((d) => d.id !== doc.id), doc] });
    } catch (e) {
      setErr(type, apiErrorText(e, t, "ob.err"));
    } finally {
      setBusyType(null);
      const input = inputs.current[type];
      if (input) input.value = "";
    }
  }

  async function onRemove(id: string, type: string) {
    setBusyType(type);
    setErr(type, null);
    try {
      await deleteDocument(id);
      onState({ ...state, documents: state.documents.filter((d) => d.id !== id) });
    } catch (e) {
      setErr(type, apiErrorText(e, t, "ob.err"));
    } finally {
      setBusyType(null);
    }
  }

  const rows: { type: DocType; required: boolean }[] = [
    ...REQUIRED_DOCS[role].map((type) => ({ type: type as DocType, required: true })),
    ...OPTIONAL_DOCS[role].map((type) => ({ type: type as DocType, required: false })),
  ];

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">{t("ob.docs.lead", { mb: MAX_UPLOAD_BYTES / 1024 / 1024 })}</p>
      <ul className="space-y-4">
        {rows.map(({ type, required }) => {
          const docs = state.documents.filter((d) => d.type === type);
          const id = `ob-doc-${type}`;
          const busy = busyType === type;
          return (
            <li key={type} className="space-y-3 rounded-card border border-line bg-surface p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label htmlFor={id} className="font-semibold text-ink">
                  {t(`ob.doc.${type}`)} {required ? "*" : `(${t("ob.optional")})`}
                </label>
                {docs.length === 0 ? <Badge tone={required ? "warning" : "neutral"}>{t("ob.docs.missing")}</Badge> : null}
              </div>
              {docs.map((d) => (
                <div key={d.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="min-w-0 break-all text-ink">
                    {d.original_name} <span className="text-muted">({size(d.size)})</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <Badge tone={TONE[d.status]}>{t(`ob.docStatus.${d.status}`)}</Badge>
                    <Button size="sm" variant="secondary" onClick={() => void onRemove(d.id, type)} disabled={busy} aria-label={`${t("ob.docs.remove")}: ${d.original_name}`}>
                      {t("ob.docs.remove")}
                    </Button>
                  </span>
                  {d.reviewer_notes ? <p className="w-full text-danger">{d.reviewer_notes}</p> : null}
                </div>
              ))}
              <input
                ref={(el) => {
                  inputs.current[type] = el;
                }}
                id={id}
                type="file"
                accept="application/pdf,image/png,image/jpeg"
                disabled={busy}
                aria-describedby={errors[type] ? `${id}-err` : `${id}-hint`}
                onChange={(e) => void onPick(type, e.target.files?.[0])}
                className="block min-h-11 w-full text-sm text-ink file:mr-3 file:min-h-11 file:rounded-xl file:border file:border-line file:bg-surface-alt file:px-4 file:font-semibold file:text-ink"
              />
              <p id={`${id}-hint`} className="text-xs text-muted">
                {t("ob.docs.types")}
              </p>
              {busy ? (
                <p role="status" className="flex items-center gap-2 text-sm text-muted">
                  <progress className="h-2 w-32" aria-label={t("ob.docs.uploading")} />
                  {t("ob.docs.uploading")}
                </p>
              ) : null}
              {errors[type] ? (
                <p id={`${id}-err`} role="alert" className="text-sm font-medium text-danger">
                  {errors[type]}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
      <Button onClick={() => onNext()} disabled={!docsDone(state)}>
        {t("ob.next")}
      </Button>
      {!docsDone(state) ? <p className="text-xs text-muted">{t("ob.docs.needed")}</p> : null}
    </div>
  );
}
