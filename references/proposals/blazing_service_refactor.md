# Blazing Service Refactor Plan

Remote execution is now the primary experience, but most of the engine still sits inside the `blazing` client package. This document enumerates what must move into `blazing_service`, why the move matters, and a phased plan to complete the migration without breaking tests.

---

## Current State (Problem)

*Update (current session):* `data_access/`, `util/`, `event_loop.py`, worker mix enhancements, and monitoring scripts have been moved under `blazing_service/`. Runtime classes now live in `blazing_service/engine/runtime.py` and are re-exported for clients.

```
src/
├── blazing/                 ← Client package (but contains server logic)
│   ├── blazing.py           (~4,800 LOC of mixed concerns)
│   ├── data_access/         (all Redis DAO classes)
│   ├── util/util.py         (Redis helpers, serialization)
│   ├── btop.py, event_loop.py, monitor_coordinator_charts.py
│   └── worker_mix_enhancements.py
└── blazing_service/         ← Actual service entrypoint (very small)
    ├── server.py
    ├── auth.py
    └── utils.py
```

The client package still imports `UnitDAO`, `OperationDAO`, `StationDAO`, etc., because legacy local execution lives side‑by‑side with the new remote SDK. This makes it trivial for client code to reach into Redis directly, violating the contract:

> **Only `blazing_service` should touch Redis. Clients must go through the HTTP API.**

---

## Target State (Clean Separation)

```
src/
├── blazing/                      ← Client SDK only
│   ├── blazing.py                (remote-mode Blazing class)
│   ├── api/client.py             (RemoteUnit, BlazingServiceClient)
│   └── backends/remote.py
└── blazing_service/              ← Engine + FastAPI server
    ├── server.py
    ├── auth.py
    ├── utils.py
    ├── data_access/              (all DAO classes)
    ├── util/                     (Redis helpers)
    ├── engine/
    │   ├── unit.py               (Unit, Operation)
    │   ├── station.py            (Station, Route)
    │   ├── coordinator.py            (HQ, Coordinator, controllers)
    │   └── connectors.py         (RESTConnector, SQLAlchemyConnector)
    ├── monitoring/               (btop, monitor_coordinator_charts, event_loop)
    └── workers/                  (worker_mix_enhancements, controllers)
```

Benefits:

- Client package cannot import DAO modules (enforced by project structure).
- Service package owns all Redis access and worker lifecycle code.
- Remote SDK shrinks to ~700 LOC and becomes easier to audit/test.
- Engine logic gains a dedicated namespace (`blazing_service.engine`), making future refactors tractable.

---

## Migration Phases

### Phase 1 — Move Data Layer (Low Risk, High Impact)
1. Move `src/blazing/data_access` → `src/blazing_service/data_access`.
2. Move `src/blazing/util` → `src/blazing_service/util`.
3. Update imports in `blazing_service/server.py` and any engine files.
4. Expose compatibility re-exports (temporary) if legacy modules still import the old paths.

### Phase 2 — Extract Execution Engine (High Effort)
1. Create `src/blazing_service/engine/` with submodules for core concepts.
2. Cut `Route`, `Station`, `Unit`, `Operation`, `BaseService` out of `blazing.py` into dedicated files.
3. Move HQ/Coordinator/Worker classes plus controllers and connectors.
4. Update `blazing_service/server.py` and worker entrypoints to import from the new engine package.

### Phase 3 — Trim Client SDK (Medium Effort)
1. Remove legacy local-execution helpers from `blazing.py`.
2. Keep only the remote-mode `Blazing` API surface, the decorators, and HTTP orchestration logic.
3. Ensure `RemoteUnit` (in `api/client.py`) provides the full async interface (`wait`, `result`, `get_result`, `cancel`).
4. Audit tests: mark local-only suites, update fixtures to spin up in-process FastAPI/Redis for remote tests.

### Phase 4 — Clean-Up & Documentation (Low Effort)
1. Update docs (`docs/architecture.md`, deployment guides) to reflect the new boundaries.
2. Deprecate environment variables or scripts tied to legacy local mode if no longer supported.
3. Add CI checks (or simple import tests) to ensure `blazing` package never imports `blazing_service.data_access`.

---

## Estimated Effort

| Phase | Scope                               | Estimate |
|-------|-------------------------------------|----------|
| 1     | Move `data_access`, `util`          | 0.5–1 day |
| 2     | Engine extraction                   | 2–3 days  |
| 3     | Client trim / remote-only polishing | 1 day     |
| 4     | Docs & guardrails                   | 0.5 day   |

Total: **~4–5 days** of focused work, best tackled in sequence to keep git history reviewable.

---

## Immediate Next Steps

1. Land the client-side guardrails already implemented (`RemoteUnit.wait`, `RemoteUnit.get_result`, and remote-aware `Blazing.wait/gather`).
2. Begin Phase 1 by physically moving `data_access/` and `util/` into `blazing_service` while keeping re-export stubs in place to avoid breaking imports mid-refactor.
3. Coordinate test ownership: remote tests run everywhere, local/engine tests live under a new `tests/engine` suite that targets `blazing_service`.

With this separation, developers no longer have to reason about Redis from the client side, and we unlock safer iterations on the distributed engine without risking SDK regressions.
