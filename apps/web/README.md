# AutoResilience web console

Next.js 16 (App Router) + React 19 + Tailwind v4 + TanStack Query.

```bash
npm install
npm run dev          # http://localhost:3000 (expects the API on :8000)
npm run lint
npm run typecheck    # next typegen && tsc --noEmit
npm run build
```

- **Backend access:** the browser calls `/api/backend/*`; `next.config.ts` rewrites it to
  `AUTORESILIENCE_API_URL` (default `http://localhost:8000`). No CORS setup is needed.
  The rewrite is resolved **at build time** (`next build`/`next dev`): set the variable before
  building; `/settings` shows the target actually baked into the running build.
- **API types** are generated, never hand-written: `scripts/gen-api-contracts.sh` (repo root)
  exports the FastAPI OpenAPI schema to `packages/contracts/openapi.json` and regenerates
  `src/lib/api/schema.ts`. Use the friendly aliases in `src/lib/api/types.ts`.
- **Data hooks** live in `src/lib/api/queries.ts`. A single experiment polls only while it is
  non-terminal; the history list and overview poll every 3–5 s while a run is in progress and
  every 15 s otherwise (drafts don't count as in progress).
- **Statistics are computed by the backend** (`GET /dashboard/summary`, `GET /experiments/history`,
  see `docs/history-and-reports.md`); pages format them, they don't aggregate. History/report
  filters, sort and page live in the URL, so refresh and links keep them.
- **Reports** (`/reports/[id]`) print on white via the `@media print` tokens in `globals.css`;
  the shell is hidden with `print:hidden`. "Print / save as PDF" uses the browser's print dialog.
- **Experiment states** are presented only through `src/lib/experiment-state.ts` (`STATE_META`
  is typed against the generated state union, so a new backend state fails the typecheck).
- **UI primitives** live in `src/components/ui`. Pages show real API data or an explicit
  "planned" state, never sample data.
