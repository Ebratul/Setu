"use client";

import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useLang, useT } from "@/i18n";
import type { ChatThread } from "@/lib/api/chat";
import { formatDate } from "@/lib/format";

type Props = {
  threads: ChatThread[];
  activeId: string | null;
  query: string;
  onQuery: (q: string) => void;
  onSelect: (t: ChatThread) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  loading?: boolean;
};

const focusRing =
  "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function ThreadList({
  threads,
  activeId,
  query,
  onQuery,
  onSelect,
  onNew,
  onRename,
  onDelete,
  loading,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const searchId = useId();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirm, setConfirm] = useState<ChatThread | null>(null);
  const [busy, setBusy] = useState(false);
  const editRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) editRef.current?.select();
  }, [editing]);

  async function commit(id: string) {
    const title = draft.trim();
    setEditing(null);
    if (title) await onRename(id, title);
  }

  return (
    <div className="space-y-3">
      <Button className="w-full" onClick={onNew}>
        {t("chat.new")}
      </Button>
      <div>
        <label htmlFor={searchId} className="sr-only">
          {t("chat.search.label")}
        </label>
        <input
          id={searchId}
          type="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder={t("chat.search.placeholder")}
          className="block w-full rounded-xl border border-muted bg-surface px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        />
      </div>
      {threads.length === 0 ? (
        <p className="text-sm text-muted">
          {loading ? t("common.loading") : t("chat.threads.empty")}
        </p>
      ) : (
        <ul className="max-h-[50vh] space-y-1 overflow-y-auto" aria-label={t("chat.threads.label")}>
          {threads.map((th) => {
            const active = th.id === activeId;
            return (
              <li
                key={th.id}
                data-thread={th.id}
                className={`rounded-xl border p-1 ${active ? "border-brand-600 bg-brand-50" : "border-transparent hover:bg-surface-alt"}`}
              >
                {editing === th.id ? (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void commit(th.id);
                    }}
                  >
                    <label htmlFor={`rn-${th.id}`} className="sr-only">
                      {t("chat.rename.label")}
                    </label>
                    <input
                      id={`rn-${th.id}`}
                      ref={editRef}
                      value={draft}
                      maxLength={120}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Escape") setEditing(null);
                      }}
                      onBlur={() => void commit(th.id)}
                      className="block w-full rounded-lg border border-muted bg-surface px-2 py-1 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                    />
                  </form>
                ) : (
                  <div className="flex items-start gap-1">
                    <button
                      type="button"
                      onClick={() => onSelect(th)}
                      aria-current={active ? "true" : undefined}
                      className={`min-w-0 flex-1 rounded-lg px-2 py-1 text-left ${focusRing}`}
                    >
                      <span className="block text-sm font-semibold break-words text-ink">
                        {th.title}
                      </span>
                      <span className="block text-xs text-muted">
                        {formatDate((th.updated_at ?? th.created_at).slice(0, 10), lang)}
                        {th.deal_id ? ` · ${th.deal_id}` : ""}
                      </span>
                    </button>
                    <button
                      type="button"
                      aria-label={t("chat.rename.button", { title: th.title })}
                      onClick={() => {
                        setDraft(th.title);
                        setEditing(th.id);
                      }}
                      className={`rounded-lg px-2 py-1 text-sm text-muted hover:bg-surface-alt ${focusRing}`}
                    >
                      <span aria-hidden="true">✎</span>
                    </button>
                    <button
                      type="button"
                      aria-label={t("chat.delete.button", { title: th.title })}
                      onClick={() => setConfirm(th)}
                      className={`rounded-lg px-2 py-1 text-sm text-danger hover:bg-danger-soft ${focusRing}`}
                    >
                      <span aria-hidden="true">🗑</span>
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {confirm ? (
        <Modal
          title={t("chat.delete.title")}
          onClose={() => setConfirm(null)}
          closeDisabled={busy}
        >
          <p className="text-sm text-ink">
            {t("chat.delete.body", { title: confirm.title })}
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" disabled={busy} onClick={() => setConfirm(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              disabled={busy}
              className="!bg-danger hover:!bg-danger"
              onClick={async () => {
                setBusy(true);
                try {
                  await onDelete(confirm.id);
                } finally {
                  setBusy(false);
                  setConfirm(null);
                }
              }}
            >
              {t("chat.delete.confirm")}
            </Button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
