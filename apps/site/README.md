# AutoResilience public website

Next.js 16 static export (`output: "export"` → `out/`), Tailwind v4, tokens and primitives from
`@autoresilience/ui`. Architecture: `docs/product/v0.2-architecture.md` §3, §4.3, §9, §11.

```bash
npm ci                              # repository root
npm run dev --workspace site        # http://localhost:3100
npm run build --workspace site      # static files in apps/site/out
npm run check --workspace site      # isolation + accessibility checks on out/
npm run preview --workspace site    # serve out/ on http://127.0.0.1:3100
npm test --workspace site
```

- **No engine access, by construction.** A static export cannot run rewrites, headers, a proxy,
  route handlers or server actions. The source makes no network calls, and every page carries a
  CSP with `connect-src 'self'`. `scripts/check-static.mjs` fails the build in CI if any of this
  regresses or an engine address (`localhost:<port>`, `127.0.0.1`, `:8000`, `/api/backend`)
  appears in `out/`.
- **Truthful content only.** Facts come from the engine and its docs (safety limits, lifecycle,
  score v3 weights in `src/lib/site.ts`). Unfinished things are marked *Planned*, *Coming soon* or
  *Placeholder*; there are no sample recordings, testimonials or metrics. The topology is labelled
  as an illustration.
- **Playground** (`/playground`, `/playground/<recording_id>`). Built at build time from the
  committed `recordings/` (`src/lib/recordings/load.ts`; `RECORDINGS_DIR` overrides). Each file
  is re-checked before it is rendered: supported schema, the exporter's sha256 recomputed over
  the canonical form (`canonical.ts` keeps number lexemes, so it is byte-identical to Python),
  file name, and `synthetic: false`. A failing file is listed as an error and never replayed.
  Types come from the recording JSON Schemas (`npm run recordings:types`). The replay
  (`src/lib/recordings/replay.ts`) uses only recorded timestamps and counts; what the evidence
  lacks (e.g. the exact deletion moment) is stated, not inferred.
- **Motion.** CSS only: scroll-driven reveals and pan (`animation-timeline: view()`, progressive
  enhancement) and the hero's looping pod-delete. All of it is off under
  `prefers-reduced-motion`. Interactive 3D is P3.
- **Colour.** Console tokens, except `faint`, which the site lightens to meet WCAG AA for small
  text. `signal` (cyan) marks the healthy request path only.
