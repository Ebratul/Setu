"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import { verifyAuditNow } from "@/lib/api/audit";
import { useHref } from "@/lib/useHref";
import { useApi } from "@/lib/useApi";

import { ChainBlocks } from "./ChainBlocks";
import { EntryDrawer } from "./EntryDrawer";
import { EvidenceDashboard } from "./EvidenceDashboard";
import { TamperPanel } from "./TamperPanel";
import { useAuditFeed } from "./useAuditFeed";

type Props = { showEvidence?: boolean };

export function AuditChainPage({ showEvidence = false }: Props) {
  const t = useT();
  const router = useRouter();
  const href = useHref();
  const feed = useAuditFeed();
  const [picked, setPicked] = useState<number | null>(null);
  const qSeq = href ? Number(new URL(href).searchParams.get("seq")) : 0;
  const open = picked ?? (Number.isInteger(qSeq) && qSeq > 0 ? qSeq : null);
  const head = feed.entries.length ? feed.entries[feed.entries.length - 1].seq : 0;
  const live = useApi((s) => verifyAuditNow(s), `audit-live|${head}`, feed.loaded);

  function close() {
    setPicked(null);
    if (qSeq) router.replace(window.location.pathname);
  }

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("audit.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("audit.intro")}</p>
      </header>

      {showEvidence ? <EvidenceDashboard /> : null}

      <Card as="section" labelledBy="chain-h" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="chain-h" className="text-lg font-bold text-ink">
            {t("audit.chain.title")}
          </h2>
          <span aria-live="polite" data-testid="chain-status">
            {live.data ? (
              live.data.ok ? (
                <Badge tone="success" icon="✓">
                  {t("audit.evidence.ok", { n: live.data.entries_checked })}
                </Badge>
              ) : (
                <Badge tone="danger" icon="✕">
                  {t("audit.evidence.broken", { seq: live.data.broken_seq ?? "?" })}
                </Badge>
              )
            ) : null}
          </span>
        </div>
        <p className="text-sm text-muted">{t("audit.chain.help")}</p>
        {feed.error && !feed.loaded ? (
          <QueryError error={feed.error} onRetry={() => void feed.reload()} />
        ) : !feed.loaded ? (
          <Skeleton className="h-32" />
        ) : feed.entries.length === 0 ? (
          <p className="text-sm text-muted">{t("audit.chain.empty")}</p>
        ) : (
          <ChainBlocks
            entries={feed.entries}
            judge={live.data?.ok === true}
            newSeqs={feed.fresh}
            selected={open}
            onSelect={setPicked}
            label={t("audit.chain.label")}
          />
        )}
        <Button variant="ghost" onClick={() => void feed.reload()}>
          {t("audit.chain.refresh")}
        </Button>
      </Card>

      <TamperPanel entries={feed.entries} />

      {open ? <EntryDrawer seq={open} onClose={close} /> : null}
    </div>
  );
}
