"use client";

import { useSyncExternalStore } from "react";

type L = "en" | "bn" | "zh";

const TEXT: Record<L, { title: string; body: string; retry: string; home: string; ref: string }> = {
  en: {
    title: "Something went wrong on our side",
    body: "Nothing was changed and no money moved. Please try again.",
    retry: "Try again",
    home: "Go to home",
    ref: "Reference",
  },
  bn: {
    title: "আমাদের দিকে একটি সমস্যা হয়েছে",
    body: "কিছুই বদলায়নি এবং কোনো টাকা সরেনি। অনুগ্রহ করে আবার চেষ্টা করুন।",
    retry: "আবার চেষ্টা করুন",
    home: "হোমে যান",
    ref: "রেফারেন্স",
  },
  zh: {
    title: "我们这边出了点问题",
    body: "没有任何改动，也没有资金变动。请重试。",
    retry: "重试",
    home: "返回首页",
    ref: "参考编号",
  },
};

function readLang(): L {
  const m = /(?:^|; )setu_lang=(\w+)/.exec(document.cookie);
  return m?.[1] === "bn" || m?.[1] === "zh" ? m[1] : "en";
}

const noop = () => () => {};

/** Rendered outside every provider (it replaces the root layout), so it reads the language cookie itself. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const lang = useSyncExternalStore<L>(noop, readLang, () => "en");
  const s = TEXT[lang];
  return (
    <html lang={lang}>
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, sans-serif",
          background: "Canvas",
          color: "CanvasText",
        }}
      >
        <main style={{ maxWidth: 480, padding: 24, textAlign: "center" }}>
          <p aria-hidden="true" style={{ fontSize: 56, fontWeight: 800, margin: 0 }}>
            500
          </p>
          <h1 style={{ fontSize: 24, margin: "8px 0" }}>{s.title}</h1>
          <p style={{ opacity: 0.8 }}>{s.body}</p>
          {error.digest ? (
            <p style={{ fontSize: 12, opacity: 0.7, wordBreak: "break-all" }}>
              {s.ref}: {error.digest}
            </p>
          ) : null}
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap", marginTop: 16 }}>
            <button
              type="button"
              onClick={reset}
              style={{ minHeight: 44, padding: "8px 16px", fontSize: 14, fontWeight: 600, borderRadius: 12, cursor: "pointer" }}
            >
              {s.retry}
            </button>
            {/* Plain anchor on purpose: a full reload is the safest recovery when the root layout failed. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/"
              style={{ minHeight: 44, display: "inline-flex", alignItems: "center", padding: "8px 16px", fontSize: 14, fontWeight: 600 }}
            >
              {s.home}
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
