# DeepBrief

DeepBrief makes a technical research pipeline visible, resumable, and auditable, then packages its checkpoints into an executive dossier.

## Run & Operate

- API: `uv run python artifacts/api-server/main.py` (FastAPI; workflow supplies port 8080)
- Web: `pnpm --filter @workspace/deepbrief run dev`
- Resilience suite: `python -m unittest discover -s artifacts/api-server/tests -v`
- Typecheck: `pnpm run typecheck`
- Regenerate API client after OpenAPI changes: `pnpm --filter @workspace/api-spec run codegen`
- Optional database path override: `DEEPBRIEF_DB`; default is `artifacts/api-server/deepbrief.sqlite3`

## Stack

- pnpm workspace, Node.js 24, TypeScript 5.9, Python 3.13
- API: FastAPI and Uvicorn
- Persistence: SQLite in WAL mode
- Frontend: Vite with native HTML, CSS, and JavaScript ES modules
- API contract: OpenAPI with Orval-generated client types

## Where things live

- `artifacts/api-server/main.py` — pipeline orchestration, API routes, SQLite checkpoints, SSE
- `artifacts/api-server/tests/test_resilience.py` — backoff, fallback, clean-run, and resume tests
- `artifacts/deepbrief/src/main.js` — workspace UI, live graph, inspector, dossier, and run history
- `artifacts/deepbrief/src/index.css` — interface theme and responsive styles
- `lib/api-spec/openapi.yaml` — API contract source of truth

## Architecture decisions

- Every stage output and run transition is saved in SQLite; SSE event IDs support replay and reconnect.
- A resumed run skips completed checkpoints and starts at the first incomplete stage.
- Fault injection uses deterministic demo source fixtures. The dossier labels these as illustrative, not live external research.

## Product

Users can launch a six-stage research run, watch live state changes and timings, inspect stage inputs/outputs/policies, inject retry/outage/crash conditions, resume from persisted checkpoints, and export a signed Markdown dossier or copyable team card.

## User preferences

The user requested a dark developer-oriented interface with a live DAG and resilience demonstrations.

## Gotchas

- API paths include `/api` because the shared proxy forwards the full path unchanged.
- Keep frontend named SSE listeners synchronized with event names emitted by the API.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
