---
paths:
  - "frontend/**"
---

# Frontend rules (frontend)

## Stack & structure
- Next.js App Router, TypeScript `strict`, Tailwind v4 (CSS-first `@theme` tokens in `src/app/globals.css`), pnpm.
- Server Components by default; add `"use client"` only for interactivity (forms, chat stream, modals, toggles).
- Layout:
  ```
  src/app/(marketing)/page.tsx        landing
  src/app/(app)/layout.tsx            app shell (sidebar/topbar, language toggle, Simulated badge)
  src/app/(app)/dashboard|cashflow|financing|analysis|orders/[id]|chat|approvals|audit/page.tsx
  src/components/ui/                  primitives (Button, Card, Badge, Stat, Table, Modal, Alert, Tabs)
  src/components/<feature>/           feature components
  src/lib/api/client.ts               typed fetch wrapper; schema.gen.ts is generated (never hand-edit)
  src/i18n/{en,bn,zh}.json + src/i18n/index.ts
  ```
- Data comes **only** from FastAPI via `src/lib/api/client.ts` (base URL from `NEXT_PUBLIC_API_BASE`, default `/api`).
  Never compute money in the browser — display server values (strings/Decimal-as-string) with a shared formatter.
- One component per file, PascalCase filenames; props typed with `type Props = {...}`; no `any`.

## Design tokens (original — Pexcon is inspiration only, never copy its code/CSS/images)
- Look: clean minimal business, generous whitespace, sticky header, strong hero, hover-lift cards, soft shadows, rounded-2xl.
- Define in `@theme`: `--color-brand-{50..900}` (deep teal, "bridge"), `--color-accent-{400..600}` (warm amber),
  `--color-ink`, `--color-muted`, `--color-surface`, `--color-surface-alt`, semantic `--color-success|warning|danger|info`,
  `--radius-card`, `--shadow-card`, `--shadow-card-hover`. Font vars: Inter (Latin), Noto Sans Bengali, Noto Sans SC via `next/font/google`.
- Use tokens only (`bg-brand-600`, `text-ink`), never raw hex in components.
- Tier colours: Tier 0 neutral, Tier 1 info, Tier 2 warning, Tier 3 danger — always paired with an icon + text label.
- Every money action / ledger view shows the `<SimulatedBadge />`.
- Images: generated SVG illustrations or royalty-free (record source + licence in `frontend/public/CREDITS.md`).

## Accessibility checklist (every page)
- Semantic landmarks: one `<h1>`, `<header> <nav> <main> <footer>`; headings in order.
- Text contrast ≥ 4.5:1 (≥ 3:1 large text/UI); never colour-only status.
- Visible focus: `focus-visible:ring-2 ring-brand-500 ring-offset-2` on all interactive elements.
- Every input has a `<label>`; errors linked via `aria-describedby`; required fields marked.
- Buttons are `<button>`, links are `<a>`/`<Link>`; icon-only buttons have `aria-label`.
- Modals: focus trap, `Esc` closes, return focus, `role="dialog" aria-modal="true" aria-labelledby`.
- Live regions: chat stream and alerts use `aria-live="polite"`; Tier 3 freeze uses `role="alert"`.
- Respect `prefers-reduced-motion` for sliders/animations. Responsive from 360px.
- `lang` attribute switches with the language toggle (`en`, `bn`, `zh`).

## i18n
- All user-visible strings via `t("key")`; add keys to `en.json` first, then `bn.json` (zh optional / cut-if-late).
- Numbers: `Intl.NumberFormat(locale)`; BDT shown as `৳`, USD `$`, CNY `¥` with ISO code on hover/aria-label.

## Commands
`pnpm --dir frontend dev | build | lint | typecheck | test`; regenerate API types with `make types`.
