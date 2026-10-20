# Authoring the Setu documentation (P29)

Source of truth for the in-app Documentation Center (`/docs`). One MDX file per page per language:

```
frontend/content/docs/{en,bn,zh}/<section>/<name>.mdx      page id = "<section>/<name>" (identical in every language)
```
Sections: `getting-started`, `buyer`, `supplier`, `admin`, `judge`, `security`, `faq`, `glossary`.
Languages: EN and BN for every page; ZH additionally for `supplier/*` and `getting-started/*` only.

## Front matter (all keys required unless marked optional)
```yaml
---
title: Funding the escrow          # page title (translated)
summary: One sentence for search results and cards.   # translated
section: buyer                     # one of the sections above
order: 40                          # sort within section (10, 20, 30 ...) - same in every language
roles: [buyer]                     # any of buyer | supplier | admin | judge
routes: ["/app/deals/[id]"]        # real app routes this page documents (exact folder-style, e.g. "/app/orders/[id]/analysis"). Use [] only for concept pages.
tryIt: "/app/deals"                # optional: deep link for the Try-it button ("/demo?step=N" for a demo step)
related: [buyer/deal-detail, security/permission-tiers]   # optional, page ids
updated: 2026-10-20
---
```

## Page template (feature pages) - use these exact heading ids
Headings carry an explicit id with the escaped-brace syntax so anchors stay identical across languages:
`## What it is \{#what-it-is}`  (the `\{#...}` suffix is stripped from the visible heading by the loader).

1. `## What it is \{#what-it-is}` - 1-2 sentences.
2. `## Who uses it \{#who}` - `<RoleBadge role="buyer" />` badges + one line.
3. `## When to use it \{#when}`
4. `## Step by step \{#how-to}` - `<Steps>` with `<Step title="...">` children; each step has a `<Screenshot />`.
5. `## What the results mean \{#results}` - explain every badge / status / number the screen shows (a table is fine).
6. `## Tips and common mistakes \{#tips}`
7. `## Related security notes \{#security}` - `<Callout type="security">` blocks; link to `/docs/<lang>/security/...`.
8. `## Try it \{#try-it}` - `<TryItButton href="..." />` (same target as `tryIt`).
9. `## Related pages \{#related}` - bullet links.
Concept pages (getting-started, security, judge, faq, glossary) may drop sections that do not apply but keep `#what-it-is` first.

## MDX components (all available without import)
- `<Steps><Step title="Open Deals">body</Step>...</Steps>`
- `<Callout type="info|tip|warning|security" title="optional">text</Callout>`
- `<Screenshot name="buyer/deals-new" route="/app/deals/new" as="buyer" alt="..." caption="..." />`
  `name` = image path under `public/docs-images/<lang>/` without extension; `route` = the app path the screenshot script visits;
  `as` = `buyer | supplier | admin | judge`; optional `wait` (CSS selector to wait for) and `click` (selector to click first).
  Alt text is mandatory and must describe what is shown. Do NOT create image files; the Playwright script generates them.
- `<RoleBadge role="buyer|supplier|admin|judge" />`, `<TierBadge tier={0|1|2|3} />`
- `<TryItButton href="/app/deals/new" label="optional override" />`
- `<Kbd>Ctrl</Kbd> + <Kbd>K</Kbd>`
- `<FAQ><FAQItem q="Question?">Answer</FAQItem></FAQ>` (collapsible)
- `<Video src="..." caption="..." />` (only if a real file exists; normally unused)
Plain Markdown (GFM tables, lists, links) works. Internal links: `/docs/<lang>/<section>/<name>` plus optional `#anchor`;
links into the app: `/app/...` (the coverage check verifies that the route exists). No raw HTML, no `<` or `{` in prose without escaping.

## Accuracy rules (the whole point of this phase)
- Read the real page component and the API behind each feature before writing. Say only what the app does. Use the exact button / label text
  from `frontend/src/i18n/en.json` + `frontend/src/i18n/parts/*.en.json` (and the BN/ZH files for translated pages).
- Money is simulated. Never imply real funds move. Tiers: 0 and 1 are automatic, 2 is one-tap approval, 3 needs OTP + 10 minute cooling-off.
- If something is unclear, partly built or you could not verify it, add an MDX comment `{/* REVIEW: what is uncertain */}` on that spot and list it in your report. Never invent a feature.
- Bangla: natural, plain Bangla; keep product terms people actually use in English (Tier, OTP, escrow, KYB, B/L, LC) in Latin script on first use with a Bangla gloss. Chinese: Simplified, business tone.
- Keep each page focused: ~250-700 words. Same structure and same heading ids in every language.
- Write only inside `frontend/content/docs/<lang>/<your sections>/`. Do not edit app code, i18n files, or other authors' pages.
