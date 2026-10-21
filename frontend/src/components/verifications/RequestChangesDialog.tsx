"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { inputClass } from "@/components/ui/FormField";
import { hasKey, useT } from "@/i18n";
import type { ChangeItem, DocType } from "@/lib/api/onboarding";
import { labelKey } from "@/lib/onboarding/errors";

type Target = { target: string; kind: "field" | "doc" };
type Props = {
  fields: string[];
  docTypes: DocType[];
  busy: boolean;
  error: string | null;
  onConfirm: (items: ChangeItem[]) => void;
  onClose: () => void;
};

export function RequestChangesDialog({ fields, docTypes, busy, error, onConfirm, onClose }: Props) {
  const t = useT();
  const targets: Target[] = [
    ...fields.map((target) => ({ target, kind: "field" as const })),
    ...docTypes.map((target) => ({ target, kind: "doc" as const })),
  ];
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [on, setOn] = useState<Record<string, boolean>>({});
  const label = (x: Target) => (x.kind === "doc" ? t(`ob.doc.${x.target}`) : hasKey(`ob.f.${labelKey(x.target)}`) ? t(`ob.f.${labelKey(x.target)}`) : x.target);
  const chosen = targets.filter((x) => on[x.target]);
  const ready = chosen.length > 0 && chosen.every((x) => (notes[x.target] ?? "").trim().length >= 3);

  return (
    <ConfirmDialog
      title={t("vq.changes.title")}
      confirmLabel={t("vq.changes.send")}
      busy={busy}
      error={error}
      confirmDisabled={!ready}
      onConfirm={() => onConfirm(chosen.map((x) => ({ target: x.target, note: notes[x.target].trim() })))}
      onClose={onClose}
    >
      <p>{t("vq.changes.body")}</p>
      <ul className="max-h-80 space-y-3 overflow-y-auto">
        {targets.map((x) => {
          const id = `vq-ch-${x.target}`;
          return (
            <li key={x.target} className="space-y-2">
              <label className="flex min-h-11 items-center gap-3 font-semibold text-ink">
                <input type="checkbox" className="size-4" checked={Boolean(on[x.target])} onChange={(e) => setOn((s) => ({ ...s, [x.target]: e.target.checked }))} />
                {label(x)}
              </label>
              {on[x.target] ? (
                <div>
                  <label htmlFor={id} className="mb-1 block text-xs text-muted">
                    {t("vq.changes.note")}: {label(x)}
                  </label>
                  <textarea
                    id={id}
                    rows={2}
                    maxLength={300}
                    value={notes[x.target] ?? ""}
                    onChange={(e) => setNotes((s) => ({ ...s, [x.target]: e.target.value }))}
                    className={inputClass}
                  />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </ConfirmDialog>
  );
}
