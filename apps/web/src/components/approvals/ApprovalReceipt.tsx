"use client";

import { ReceiptButton } from "@/components/audit/ReceiptButton";
import { getTimeline, type Approval } from "@/lib/api/approvals";
import { useApi } from "@/lib/useApi";

/** Receipt for an approved / executed approval, found through the deal timeline's audit references. */
export function ApprovalReceipt({ approval: a }: { approval: Approval }) {
  const ref = a.deal_reference;
  const tl = useApi((s) => getTimeline(ref ?? "", s), `appr-rcpt|${a.id}|${a.status}`, Boolean(ref));
  if (!tl.data || tl.data.approval_id !== a.id) return null;
  const steps = tl.data.steps;
  const seq =
    steps.find((s) => s.key === "EXECUTED" && s.state === "DONE")?.audit_seq ??
    steps.find((s) => s.key === "HUMAN" && s.state === "DONE")?.audit_seq;
  return seq != null ? <ReceiptButton seq={seq} /> : null;
}
