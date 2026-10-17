"use client";

import { hasKey, useT } from "@/i18n";
import type { FindingOut } from "@/lib/api/documents";

import { fieldLabel, fieldValue, mismatchesFromFindings } from "./mismatch";

const HIDE = new Set(["doc_type"]);

type Props = { fields: Record<string, unknown>; findings: readonly FindingOut[] };

export function FieldsTable({ fields, findings }: Props) {
  const t = useT();
  const mismatches = mismatchesFromFindings(findings, fields);
  const rows = Object.entries(fields).filter(([k]) => !k.startsWith("_") && !HIDE.has(k));
  if (rows.length === 0) return <p className="text-sm text-muted">{t("doc.fields.none")}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="fields-table">
        <caption className="sr-only">{t("doc.fields.title")}</caption>
        <thead>
          <tr className="border-b border-line text-left text-muted">
            <th scope="col" className="py-2 pr-3 font-medium">{t("doc.fields.field")}</th>
            <th scope="col" className="py-2 font-medium">{t("doc.fields.value")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, v]) => {
            const mm = mismatches.filter((m) => m.field === k);
            const bad = mm.length > 0;
            return (
              <tr
                key={k}
                data-testid="field-row"
                data-mismatch={bad}
                className={`border-b border-line align-top last:border-0 ${bad ? "bg-danger-soft" : ""}`}
              >
                <th scope="row" className="py-2 pr-3 text-left font-medium text-ink">
                  {hasKey(`doc.field.${k}`) ? t(`doc.field.${k}`) : fieldLabel(k)}
                </th>
                <td className="py-2 break-words text-ink">
                  <span className={bad ? "font-semibold text-danger" : ""}>
                    {bad ? <span aria-hidden="true">▲ </span> : null}
                    {fieldValue(v)}
                  </span>
                  {mm.map((m) => (
                    <span key={m.expected + String(m.against)} data-testid="field-conflict" className="mt-0.5 block text-xs font-medium text-danger">
                      {m.against && hasKey(`docType.${m.against}`)
                        ? t("doc.fields.otherSays", { source: t(`docType.${m.against}`), value: m.expected })
                        : m.against === "deal"
                          ? t("doc.fields.dealSays", { value: m.expected })
                          : t("doc.fields.expected", { value: m.expected })}
                    </span>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
