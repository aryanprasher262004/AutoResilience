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
- **API types** are generated, never hand-written: `scripts/gen-api-contracts.sh` (repo root)
  exports the FastAPI OpenAPI schema to `packages/contracts/openapi.json` and regenerates
  `src/lib/api/schema.ts`. Use the friendly aliases in `src/lib/api/types.ts`.
- **Data hooks** live in `src/lib/api/queries.ts`; experiment queries poll only while an
  experiment is in a non-terminal state.
- **Experiment states** are presented only through `src/lib/experiment-state.ts` (`STATE_META`
  is typed against the generated state union, so a new backend state fails the typecheck).
- **UI primitives** live in `src/components/ui`. Pages show real API data or an explicit
  "planned" state, never sample data.
