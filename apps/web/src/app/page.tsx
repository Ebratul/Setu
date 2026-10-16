import Link from "next/link";

import { AgentStatusCard } from "@/components/status/AgentStatusCard";

export default function Home() {
  return (
    <>
      <header className="bg-surface shadow-card">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
          <span className="text-lg font-semibold text-brand-700">
            Setu সেতু
          </span>
          <span className="rounded-full border border-warning px-3 py-1 text-xs font-semibold tracking-wide text-warning uppercase">
            Simulated sandbox
          </span>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-start gap-8 px-6 py-16">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            Setu — AI SME Finance Copilot
          </h1>
          <p className="mt-3 max-w-xl text-muted">
            Financing, cash flow and order analysis for SMEs importing from
            China. All money movement in this app is simulated.
          </p>
        </div>
        <Link
          href="/login"
          className="rounded-xl bg-brand-700 px-5 py-3 font-semibold text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          Open the demo → /login
        </Link>
        <AgentStatusCard />
      </main>
      <footer className="px-6 py-6 text-center text-sm text-muted">
        FinTechathon 2026 · Simulated sandbox — no real payments
      </footer>
    </>
  );
}
