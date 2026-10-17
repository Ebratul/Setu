"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useT } from "@/i18n";

type Tone = "success" | "danger" | "info";
type ToastItem = { id: number; tone: Tone; text: string };
type Push = (text: string, tone?: Tone) => void;

const ToastContext = createContext<Push>(() => {});

const ICON: Record<Tone, string> = { success: "✓", danger: "✕", info: "i" };
const CLS: Record<Tone, string> = {
  success: "border-success bg-success-soft text-ink",
  danger: "border-danger bg-danger-soft text-ink",
  info: "border-info bg-info-soft text-ink",
};

export function useToast(): Push {
  return useContext(ToastContext);
}

/** Polite live region; success/info toasts fade after 6 s, errors stay until dismissed. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback(
    (id: number) => setItems((xs) => xs.filter((x) => x.id !== id)),
    [],
  );
  const push = useCallback<Push>(
    (text, tone = "success") => {
      const id = nextId.current++;
      setItems((xs) => [...xs.slice(-3), { id, tone, text }]);
      if (tone !== "danger") setTimeout(() => dismiss(id), 6000);
    },
    [dismiss],
  );
  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-3 bottom-3 z-60 flex flex-col items-stretch gap-2 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:w-96"
      >
        {items.map((x) => (
          <ToastCard key={x.id} item={x} onClose={dismiss} label={t("common.close")} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({
  item,
  onClose,
  label,
}: {
  item: ToastItem;
  onClose: (id: number) => void;
  label: string;
}) {
  return (
    <div
      data-testid="toast"
      data-tone={item.tone}
      className={`pointer-events-auto flex items-start gap-2 rounded-xl border-2 p-3 text-sm shadow-card-hover ${CLS[item.tone]}`}
    >
      <span aria-hidden="true" className="font-bold">
        {ICON[item.tone]}
      </span>
      <p className="min-w-0 flex-1">{item.text}</p>
      <button
        type="button"
        aria-label={label}
        onClick={() => onClose(item.id)}
        className="rounded px-1 text-lg leading-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        <span aria-hidden="true">×</span>
      </button>
    </div>
  );
}
