/** Build-time public configuration for the judges page. NEXT_PUBLIC_* must be read as literal `process.env.X`. */

export const JUDGE_EMAIL_DEFAULT = "judge@demo.setu";

const clean = (v: string | undefined): string | null =>
  v && v.trim() !== "" ? v.trim() : null;

/** Only http(s) URLs are accepted, so a bad env value can never become a javascript: href. */
export function safeUrl(v: string | null): string | null {
  if (!v) return null;
  try {
    const u = new URL(v);
    return u.protocol === "https:" || u.protocol === "http:"
      ? u.toString()
      : null;
  } catch {
    return null;
  }
}

export type JudgeConfig = {
  email: string;
  note: string | null;
  repoUrl: string | null;
  docsUrl: string | null;
  videoUrl: string | null;
  statusUrl: string | null;
  siteUrl: string | null;
};

export function judgeConfig(): JudgeConfig {
  const repo = safeUrl(clean(process.env.NEXT_PUBLIC_REPO_URL));
  return {
    email: clean(process.env.NEXT_PUBLIC_JUDGE_EMAIL) ?? JUDGE_EMAIL_DEFAULT,
    note: clean(process.env.NEXT_PUBLIC_JUDGE_NOTE),
    repoUrl: repo,
    docsUrl: repo ? `${repo.replace(/\/$/, "")}/tree/main/docs` : null,
    videoUrl: safeUrl(clean(process.env.NEXT_PUBLIC_VIDEO_URL)),
    statusUrl: safeUrl(clean(process.env.NEXT_PUBLIC_STATUS_URL)),
    siteUrl:
      safeUrl(clean(process.env.NEXT_PUBLIC_SITE_URL))?.replace(/\/$/, "") ??
      null,
  };
}

export type TryItem = {
  id: "guided" | "risk" | "privacy" | "attack" | "verify";
  href: string;
};
export const TRY_ITEMS: TryItem[] = [
  { id: "guided", href: "/demo/run" },
  { id: "risk", href: "/demo/risk-playground" },
  { id: "privacy", href: "/demo/privacy-playground" },
  { id: "attack", href: "/demo/attack-console" },
  { id: "verify", href: "/verify" },
];

export type ScoreRow = { id: string; href: string };
export const SCORE_ROWS: ScoreRow[] = [
  { id: "fr1", href: "/app/financing" },
  { id: "fr2", href: "/app/cashflow" },
  { id: "fr3", href: "/app/analysis" },
  { id: "fr4", href: "/app/suppliers" },
  { id: "fr5", href: "/demo?step=5" },
  { id: "fr6", href: "/demo?step=9" },
  { id: "fr7", href: "/demo?step=6" },
  { id: "fr8", href: "/demo?step=12" },
  { id: "fr9", href: "/app/chat" },
  { id: "sr12", href: "/demo/risk-playground" },
  { id: "sr3", href: "/demo/attack-console" },
  { id: "sr4", href: "/demo/privacy-playground" },
  { id: "sr5", href: "/verify" },
  { id: "sr6", href: "/demo?step=10" },
  { id: "sr89", href: "/demo?step=8" },
  { id: "nfr12", href: "/accessibility" },
  { id: "nfr4", href: "/#results" },
];
