# AutoResilience web console

Next.js 16 (App Router) + React 19 + Tailwind v4 + TanStack Query.

```bash
npm install
npm run dev          # http://localhost:3000 (expects the API on :8000)
npm run lint
npm run typecheck    # next typegen && tsc --noEmit
npm run build
npm test             # Vitest, once (CI); npm run test:watch while developing
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

## Tests

Vitest + React Testing Library on happy-dom (`vitest.config.mts`, setup in `src/test/`).
Tests sit next to the component (`*.test.tsx`) and cover the critical workflows:

| File | Covers |
|---|---|
| `components/experiment/builder/experiment-builder.test.tsx` | required fields, server 422s on their fields, passed/blocked safety validation, confirmation before start, navigation to the room, duplicate-submit protection, discovered-workload picker |
| `components/shell/api-status.test.tsx` | ready, database not ready, API unreachable (network / bare proxy 500), recovery with refetch |
| `components/history/history-view.test.tsx` | rows from the API, search (debounced), filters, sort, paging, URL state, empty and error states |
| `components/experiment/room/experiment-room.test.tsx` | every state from VALIDATING to ABORTED, polling stops when terminal, score only when stored, NOT_SCORED, abort (success and refusal) |

How the tests talk to the "backend":

- `src/test/api.ts` stubs `fetch`, so requests go through the real `src/lib/api/client.ts`.
  Tests assert the request the UI sends (path, query, body) and answer with payloads typed by
  the generated contract (`src/test/fixtures.ts`). They never reimplement filtering, safety
  or scoring; a request without a handler fails the test.
- `src/test/navigation.tsx` replaces `next/navigation` / `next/link` with an in-memory URL,
  so URL state, `router.push` and refreshes are observable.
- Time-based behaviour (polling, readiness re-checks) uses Vitest fake timers.
- QueryClient defaults come from `src/lib/api/query-client.ts` (same as the app), with retries off.
