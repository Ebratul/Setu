import type { AuditEntry } from "@/lib/api/audit";

export type TamperMode = "edit" | "delete" | "reorder";
export const TOP_FIELDS = ["decision", "tier", "action"] as const;

export const editableFields = (e: AuditEntry): string[] => [...Object.keys(e.payload), ...TOP_FIELDS];

export function currentValue(e: AuditEntry, field: string): string {
  if ((TOP_FIELDS as readonly string[]).includes(field)) return String(e[field as (typeof TOP_FIELDS)[number]]);
  const v = e.payload[field];
  return typeof v === "string" ? v : JSON.stringify(v);
}

/** Suggested tampered value; for `amount` it inserts a digit into the text (5760.00 -> 57600.00), no arithmetic. */
export function suggestValue(e: AuditEntry, field: string): string {
  const cur = currentValue(e, field);
  if (field === "amount" && /^\d+(\.\d+)?$/.test(cur)) return cur.replace(/^(\d+)/, "$10");
  if (field === "tier") return "0";
  return `${cur}!`;
}

export function defaultField(e: AuditEntry): string {
  return "amount" in e.payload ? "amount" : (editableFields(e)[0] ?? "decision");
}
