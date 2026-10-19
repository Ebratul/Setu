// Hand-written from the P18 contract until `make types` regenerates schema.gen.ts.

export type PrivacyType =
  | "NID"
  | "PASSPORT"
  | "PHONE"
  | "ACCT"
  | "IBAN"
  | "SWIFT"
  | "EMAIL"
  | "NAME"
  | "AMT";

export type Segment = { text: string; type: string | null; token: string | null };

export type PrivacyStats = {
  masked_by_type: Record<string, number>;
  protected: number;
  leaked_count: number;
  chars_sent: number;
};

export type PrivacyHit = {
  type: string;
  start: number;
  end: number;
  confidence: number;
  token: string;
  obfuscated: boolean;
  label_en: string;
  label_bn: string;
};

export type DryRunRequest = { text: string; mask_amounts: boolean };

export type DryRunResult = {
  simulated: true;
  mask_amounts: boolean;
  hits: PrivacyHit[];
  source_segments: Segment[];
  masked_segments: Segment[];
  masked: string;
  ai_answer_masked: string;
  ai_answer_segments: Segment[];
  restored_answer: string;
  restored_segments: Segment[];
  stats: PrivacyStats;
};

export type PrivacySummary = {
  protected: number;
  leaked: number;
  calls: number;
  by_type: Record<string, number>;
};

export type XrayLeft = { label: string; segments: Segment[] };
export type XrayRight = {
  label: string;
  node: string;
  model: string | null;
  sent: boolean;
  segments: Segment[];
};

export type PrivacyXrayData = {
  kind: "message" | "document";
  available: boolean;
  stats: PrivacyStats;
  left: XrayLeft[];
  right: XrayRight[];
};

export type PrivacyRecord = {
  id: string;
  created_at: string;
  source: string;
  node: string;
  model: string | null;
  sent: boolean;
  protected: number;
  leaked: number;
  by_type: Record<string, number>;
  masked_payload: string;
};

export type PrivacyOverview = {
  totals: { protected: number; leaked: number; calls: number };
  by_type: Record<string, number>;
  series: { day: string; protected: number; leaked: number }[];
  recent: PrivacyRecord[];
  trace: { enabled: boolean; url: string | null; run_id: string | null; note: string };
  config: { enabled: boolean; mask_amounts: boolean };
};
