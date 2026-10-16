---
name: new-ui-page
description: Step-by-step procedure to add a Setu Next.js page that uses the design tokens, generated API types, i18n and the accessibility checklist. Use whenever a new route or major screen is added in apps/web.
---

# Add a new UI page

1. **Confirm the API** exists: `grep` the route in `apps/web/src/lib/api/schema.gen.ts`. If missing or stale, run `make types`
   (agent must be running) — if the endpoint truly doesn't exist, stop and report the gap.
2. **Route**: create `apps/web/src/app/(app)/<route>/page.tsx` as a Server Component that fetches via `src/lib/api/client.ts`.
   Add `loading.tsx` (skeleton) and `error.tsx` (friendly message + retry). Add the nav item in the app-shell nav config.
3. **Components**: build from `src/components/ui/*` primitives; feature components in `src/components/<feature>/`.
   Client components only where interaction is needed. No raw hex; tokens only. Money values come pre-computed from the API
   and are rendered with `formatMoney()`; money/escrow screens include `<SimulatedBadge />`.
4. **Copy**: every string via `t("<page>.<key>")`; add keys to `src/i18n/en.json` and `src/i18n/bn.json`.
   Explanations from the API are shown verbatim in an "Why?" disclosure (`<details>`), with cited facts.
5. **Accessibility pass** (frontend.md checklist): one h1, landmarks, labels, focus-visible, contrast, aria-live for
   async results, keyboard-only walkthrough, 360px width check.
6. **Tests**: Vitest + Testing Library for each interactive component (renders, labels present, main interaction);
   mock the API client.
7. Run `pnpm --dir apps/web lint && pnpm --dir apps/web typecheck && pnpm --dir apps/web test`; open the page with
   `make dev` and check it renders with seed data in en and bn.
