# AutoResilience web console

Next.js 16 (App Router) + React 19 + Tailwind v4 + TanStack Query.

```bash
npm ci               # at the repository root: one lockfile for all workspaces
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
- **UI primitives** live in `src/components/ui`; tokens, `cn`, `Badge` and `buttonClasses` come
  from `packages/ui`. Pages show real API data or an explicit "planned" state, never sample data.
- **Shell** (`src/components/shell`): grouped navigation (Workspace, Learn, System) as a sidebar
  (≥ lg), icon rail (md) or drawer (phones, portalled out of the blurred header). Unknown paths
  render the 404 with no active item and a single "Not found" crumb, matching its prerender.
- **Help content** (`src/lib/help-content.ts`): one source for page tours, the Help panel, the
  Help page's page guides and the onboarding explanations. Text only; it never decides.
  `pageFor(pathname)` maps a URL to its page.
- **Tours** (`src/components/tour`): `TourHost` in the layout opens the current page's tour on
  the first visit (Overview, Experiments, Applications, Topology, Settings) and records it as
  finished or skipped per page. Steps spotlight real controls marked
  `data-tour={TOUR_TARGET.x}` (the first visible one, so responsive duplicates work), say
  when a control is not on screen, and only let view-only controls (filters, legend, graph
  selection) be used to advance; everything else stays covered, and a tour never starts,
  confirms or approves anything. Back/Next/dots, ← →, Escape skips; focus returns on close;
  phones get a bottom sheet. Navigating away ends a tour unrecorded. Replay: top bar Tour,
  Help, Settings → Guided tours (also reset per page or all).
- **Help panel** (`src/components/help/help-panel.tsx`): the top bar's Help (or `?` when not
  typing) opens a side dialog for the current page: topics, its tour, documentation links.
- **Inline explanations:** `ui/tooltip.tsx` (hover/focus, `aria-describedby`, Escape) for the
  topology toggles, `ui/info-hint.tsx` ("?" disclosure) beside complex controls.
- **Preferences** (`src/lib/preferences.ts`, localStorage): experiment defaults (mode, duration,
  affected replicas) that only pre-fill the builder, and which page tours were finished or
  skipped. They
  are never limits: the server's namespace policy decides every run. Malformed storage falls
  back field by field.
- **Guidance text** (`src/lib/guidance.ts`) explains phases and checks; it never decides. The
  builder's summary shows the discovered workload's ready replicas next to the requested blast
  radius without judging it, and failed checks get background beside the server's message.
- **Runtime** (`src/lib/runtime.ts`): only `local` exists; desktop and Cloud are listed as planned
  (Settings). Keep mode-specific assumptions behind this module.
- **Pages:** Help (live setup checklist, page guides, troubleshooting per readiness reason,
  state glossary), How it works, Support (honest channels, copyable secret-free diagnostics;
  nothing is sent), About, Settings (environment health, Kubernetes access, data and backups,
  stack operations, console preferences and tours; explanations only where nothing may be
  changed from the browser).
- **Topology** (`src/components/topology`): view state and presentation metadata are pure in
  `src/lib/topology.ts`; `TopologyGraph` is one renderer of `TopologyRendererProps`
  (`docs/topology.md`, "Views"). Legend, tooltips, inspector explanations and the List view
  read the same metadata as the graph.

## Tests

Vitest + React Testing Library on happy-dom (`vitest.config.mts`, setup in `src/test/`).
Tests sit next to the component (`*.test.tsx`) and cover the critical workflows:

| File | Covers |
|---|---|
| `components/experiment/builder/experiment-builder.test.tsx` | required fields, server 422s on their fields, passed/blocked safety validation, confirmation before start, navigation to the room, duplicate-submit protection, discovered-workload picker |
| `components/shell/api-status.test.tsx` | ready, database not ready, API unreachable (network / bare proxy 500), recovery with refetch |
| `components/history/history-view.test.tsx` | rows from the API, search (debounced), filters, sort, paging, URL state, empty and error states |
| `components/experiment/room/experiment-room.test.tsx` | every state from VALIDATING to ABORTED, polling stops when terminal, score only when stored, NOT_SCORED, abort (success and refusal) |
| `components/tour/tour.test.tsx` | first-visit start per page, focus, Next/Back/dots, Finish/Skip/Escape persisted, arrow keys, missing and responsive-hidden controls, advance only on safe controls, page change, pages without a tour |
| `lib/help-content.test.ts` | URL → page mapping, tours for the five pages, advance targets are view-only, every target known |
| `components/settings/preferences-form.test.tsx` | defaults, save, local validation only (no policy limits), reset, tolerant parsing |
| `components/experiment/builder/builder-preferences.test.tsx` | saved defaults pre-fill the builder and are sent unchanged; the server's refusal is shown |
| `components/shell/top-bar.test.tsx` | phone drawer (focus, Escape, closes on navigation), page Tour and page-aware Help, breadcrumbs incl. 404 |
| `components/help/help.test.tsx` | live setup checklist, fix links per failure, diagnostics copy (secret-free), Help panel (`?` not while typing, page content, starts the tour) |
| `components/topology/topology-view.test.tsx` | filters, inspector and builder hand-off, read-only clusters, List view, unknowns with explanations, tooltips, legend, selection announcement and clearing, filter empty state |
| `components/settings/settings-sections.test.tsx`, `stack-controls.test.tsx` | Kubernetes access, data and backups per runtime mode, tour progress/reset/replay; pairing steps and operation consequences |
| `components/experiment/room/phase-guide.test.tsx` | phase explanation for active runs only; check background only for non-passing checks |

How the tests talk to the "backend":

- `src/test/api.ts` stubs `fetch`, so requests go through the real `src/lib/api/client.ts`.
  Tests assert the request the UI sends (path, query, body) and answer with payloads typed by
  the generated contract (`src/test/fixtures.ts`). They never reimplement filtering, safety
  or scoring; a request without a handler fails the test.
- `src/test/navigation.tsx` replaces `next/navigation` / `next/link` with an in-memory URL,
  so URL state, `router.push` and refreshes are observable.
- Time-based behaviour (polling, readiness re-checks) uses Vitest fake timers.
- QueryClient defaults come from `src/lib/api/query-client.ts` (same as the app), with retries off.
