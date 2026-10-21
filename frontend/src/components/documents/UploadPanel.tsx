"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { inputClass } from "@/components/ui/FormField";
import { Bi } from "@/components/supplier/Bi";
import { useT } from "@/i18n";
import {
  DOC_TYPES,
  MAX_UPLOAD_BYTES,
  getDocument,
  isChecking,
  precheckFile,
  suggestDocType,
  supplierStatus,
  docUiStatus,
  typeFitsFile,
  uploadDocument,
  uploadErrorKey,
  type DocType,
  type DocumentOut,
} from "@/lib/api/documents";

import { DocStatusBadge, SupplierDocBadge } from "./DocStatusBadge";

type State = "staged" | "uploading" | "checking" | "done" | "error";
type Item = {
  id: number;
  file: File;
  docType: DocType;
  state: State;
  doc?: DocumentOut;
  reused?: boolean;
  problem?: string;
  timedOut?: boolean;
};

type Props = {
  dealId: string;
  allowedTypes?: DocType[];
  /** Supplier view: status words only, no link to the viewer, bilingual labels. */
  supplier?: boolean;
  onChanged?: () => void;
};

const POLL_MS = 1500;
const POLL_MAX = 40;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const linkCls =
  "font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function UploadPanel({ dealId, allowedTypes = DOC_TYPES, supplier = false, onChanged }: Props) {
  const t = useT();
  const uid = useId();
  const input = useRef<HTMLInputElement>(null);
  const alive = useRef(true);
  const nextId = useRef(1);
  const [items, setItems] = useState<Item[]>([]);
  const [over, setOver] = useState(false);
  const [announce, setAnnounce] = useState("");
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  });
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const patch = (id: number, p: Partial<Item>) =>
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...p } : x)));

  function addFiles(list: FileList | File[]) {
    const added: Item[] = [];
    for (const file of Array.from(list)) {
      const problem = precheckFile(file);
      added.push({
        id: nextId.current++,
        file,
        docType: suggestDocType(file.name, allowedTypes),
        state: problem ? "error" : "staged",
        problem: problem ? `docErr.${problem}` : undefined,
      });
    }
    setItems((xs) => [...xs, ...added]);
    const bad = added.filter((a) => a.state === "error").length;
    setAnnounce(bad ? t("doc.up.rejected", { n: bad }) : t("doc.up.added", { n: added.length }));
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  }

  async function run(item: Item) {
    patch(item.id, { state: "uploading", problem: undefined });
    setAnnounce(t("doc.up.uploading", { name: item.file.name }));
    try {
      const res = await uploadDocument(dealId, item.docType, item.file);
      if (!alive.current) return;
      let doc = res.document;
      patch(item.id, { doc, reused: res.reused, state: isChecking(doc) ? "checking" : "done" });
      if (res.reused) setAnnounce(t("doc.up.reused", { name: item.file.name }));
      else setAnnounce(t("doc.up.checking", { name: item.file.name }));
      onChanged?.();
      for (let i = 0; isChecking(doc) && i < POLL_MAX; i++) {
        await sleep(POLL_MS);
        if (!alive.current) return;
        let d: DocumentOut;
        try {
          d = await getDocument(doc.id);
        } catch {
          break;
        }
        if (!alive.current) return;
        doc = d;
        patch(item.id, { doc: d });
      }
      if (!alive.current) return;
      const timedOut = isChecking(doc);
      patch(item.id, { state: "done", doc, timedOut });
      setAnnounce(
        timedOut
          ? t("doc.up.timeout", { name: item.file.name })
          : t("doc.up.finished", {
              name: item.file.name,
              status: supplier
                ? t(`doc.sup.${supplierStatus(doc)}`)
                : t(`doc.status.${docUiStatus(doc)}`),
            }),
      );
      onChanged?.();
    } catch (error) {
      if (!alive.current) return;
      const key = uploadErrorKey(error);
      patch(item.id, { state: "error", problem: key });
      setAnnounce(`${item.file.name}: ${t(key)}`);
    }
  }

  async function uploadAll() {
    const todo = itemsRef.current.filter((x) => x.state === "staged" && typeFitsFile(x.docType, x.file.name));
    await Promise.all(todo.map(run));
  }

  const staged = items.filter((x) => x.state === "staged");
  const misfit = staged.some((x) => !typeFitsFile(x.docType, x.file.name));
  const busy = items.some((x) => x.state === "uploading");

  return (
    <Card as="section" labelledBy={`${uid}-h`} className="space-y-4">
      <h2 id={`${uid}-h`} className="text-lg font-bold text-ink">
        {supplier ? <Bi k="doc.up.title" /> : t("doc.up.title")}
      </h2>
      <div
        role="group"
        aria-labelledby={`${uid}-h`}
        data-testid="dropzone"
        data-over={over}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-6 text-center ${
          over ? "border-brand-600 bg-brand-50" : "border-muted bg-surface-alt"
        }`}
      >
        <p className="text-sm text-ink">{t("doc.up.drop")}</p>
        <Button variant="secondary" onClick={() => input.current?.click()} aria-describedby={`${uid}-rules`}>
          {t("doc.up.choose")}
        </Button>
        <p id={`${uid}-rules`} className="text-xs text-muted">
          {t("doc.up.rules", { mb: MAX_UPLOAD_BYTES / (1024 * 1024) })}
        </p>
        <input
          ref={input}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          data-testid="file-input"
          tabIndex={-1}
          aria-hidden="true"
          className="sr-only"
          onChange={(e) => {
            if (e.target.files?.length) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      <p role="status" aria-live="polite" data-testid="upload-live" className="sr-only">
        {announce}
      </p>

      {items.length > 0 ? (
        <ul className="space-y-2" data-testid="upload-queue">
          {items.map((x) => (
            <QueueRow
              key={x.id}
              item={x}
              allowedTypes={allowedTypes}
              supplier={supplier}
              onType={(docType) => patch(x.id, { docType })}
              onRemove={() => setItems((xs) => xs.filter((y) => y.id !== x.id))}
            />
          ))}
        </ul>
      ) : null}

      {staged.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={uploadAll} disabled={busy || misfit} data-testid="upload-go">
            {t("doc.up.go", { n: staged.length })}
          </Button>
          {misfit ? <p className="text-xs font-medium text-danger">{t("doc.up.misfit")}</p> : null}
        </div>
      ) : null}
    </Card>
  );
}

function QueueRow({
  item,
  allowedTypes,
  supplier,
  onType,
  onRemove,
}: {
  item: Item;
  allowedTypes: DocType[];
  supplier: boolean;
  onType: (t: DocType) => void;
  onRemove: () => void;
}) {
  const t = useT();
  const id = useId();
  const fits = typeFitsFile(item.docType, item.file.name);
  return (
    <li
      data-testid="upload-item"
      data-state={item.state}
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-line p-3 text-sm"
    >
      <span className="min-w-0 flex-1 font-semibold break-all text-ink">{item.file.name}</span>
      {item.state === "staged" ? (
        <div className="flex items-center gap-2">
          <label htmlFor={`${id}-type`} className="text-xs text-muted">
            {t("doc.up.type")}
          </label>
          <select
            id={`${id}-type`}
            value={item.docType}
            aria-invalid={fits ? undefined : true}
            onChange={(e) => onType(e.target.value as DocType)}
            className={`${inputClass} w-auto`}
          >
            {allowedTypes.map((d) => (
              <option key={d} value={d}>
                {t(`docType.${d}`)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {item.state === "uploading" ? <span className="text-muted">{t("doc.up.uploadingShort")}</span> : null}
      {item.state === "checking" || item.state === "done" ? (
        <span className="flex flex-wrap items-center gap-2">
          {item.doc ? (
            supplier ? (
              <SupplierDocBadge status={supplierStatus(item.doc)} />
            ) : (
              <DocStatusBadge status={docUiStatus(item.doc)} />
            )
          ) : null}
          {item.reused ? <span className="text-xs text-muted">{t("doc.up.reusedShort")}</span> : null}
          {item.timedOut ? <span className="text-xs text-warning">{t("doc.up.timeoutShort")}</span> : null}
          {!supplier && item.doc && item.state === "done" ? (
            <Link href={`/app/documents/${item.doc.id}`} className={linkCls}>
              {t("doc.open")}
            </Link>
          ) : null}
        </span>
      ) : null}
      {item.state === "error" && item.problem ? (
        <span role="alert" className="text-xs font-medium text-danger">
          <span aria-hidden="true">✕ </span>
          {t(item.problem, { mb: MAX_UPLOAD_BYTES / (1024 * 1024) })}
        </span>
      ) : null}
      {item.state === "staged" || item.state === "error" ? (
        <Button variant="ghost" onClick={onRemove} aria-label={t("doc.up.remove", { name: item.file.name })}>
          <span aria-hidden="true">×</span>
        </Button>
      ) : null}
    </li>
  );
}
