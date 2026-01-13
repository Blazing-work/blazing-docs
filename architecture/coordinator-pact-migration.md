# Pact Architecture: HTTP Proxy for External Executors

## Executive Summary

Pact is a **pure HTTP proxy client** for external executors (Docker, Pyodide) to communicate with the Coordinator. It provides a clean abstraction layer so that executors never directly access Redis.

**Key Principle:** The Coordinator owns all state. Executors are "dumb muscle" that receive commands and report status via HTTP.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           COORDINATOR                                    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Internal Worker Management                                       │    │
│  │                                                                  │    │
│  │   Direct DAO Access (proven, battle-tested)                      │    │
│  │   • CoordinatorDAO.current_command                               │    │
│  │   • WorkerProcessDAO.current_command                             │───→ REDIS
│  │   • WorkerThreadDAO.current_command                              │    │
│  │   • WorkerAsyncDAO.current_command                               │    │
│  │   • Util.update_fields_in_transaction()                          │    │
│  │                                                                  │    │
│  │   This code is NOT changing - it works perfectly.                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Pact HTTP API (thin layer over same DAOs)                        │    │
│  │                                                                  │    │
│  │   GET  /v1/pact/processes/{pk}/command                           │    │
│  │   POST /v1/pact/processes/{pk}/command                           │    │
│  │   GET  /v1/pact/threads/{pk}/command                             │    │
│  │   POST /v1/pact/threads/{pk}/command                             │    │
│  │   GET  /v1/pact/async-workers/{pk}/command                       │    │
│  │   POST /v1/pact/async-workers/{pk}/command                       │    │
│  │   POST /v1/pact/processes/{pk}/status                            │    │
│  │   POST /v1/pact/processes/{pk}/identity                          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ HTTP only
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL EXECUTORS                                │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PactClient (HttpProxyBackend)                                    │    │
│  │                                                                  │    │
│  │   .get_process_command(pk) → GET /v1/pact/processes/{pk}/command │    │
│  │   .set_process_command(pk) → POST /v1/pact/processes/{pk}/command│    │
│  │   .update_status(pk)       → POST /v1/pact/processes/{pk}/status │    │
│  │   .update_identity(pk)     → POST /v1/pact/processes/{pk}/identity│   │
│  │                                                                  │    │
│  │   NEVER touches Redis directly                                   │    │
│  │   ALL state goes through Coordinator HTTP API                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Docker Executor                     Pyodide Executor                   │
│  ├── PactClient                      ├── PactClient (JS)                │
│  ├── Polls for commands              ├── Polls for commands             │
│  ├── Executes user code              ├── Executes user code (WASM)      │
│  └── Reports status                  └── Reports status                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Why This Architecture?

### 1. Separation of Concerns

| Component | Responsibility | Redis Access |
|-----------|----------------|--------------|
| **Coordinator** | Owns all state, makes all decisions | Direct DAO access |
| **Executors** | Execute user code, follow commands | None (HTTP only) |

### 2. Security

Executors run potentially untrusted user code. They should NOT have direct Redis access:
- No risk of data corruption
- No risk of accessing other tenants' data
- Coordinator validates all operations

### 3. Simplicity

One code path for state management:
- Coordinator uses proven, battle-tested DAO code
- External executors use simple HTTP client
- No need to maintain two implementations

### 4. Flexibility

The HTTP API provides a stable contract:
- Executors can be written in any language (Python, JavaScript, etc.)
- Implementation details hidden behind API
- Easy to add new executor types

## PactClient (for Executors)

The only Pact component executors need:

```python
class PactClient:
    """
    HTTP client for external executors to communicate with Coordinator.

    This is the ONLY way executors interact with state.
    All state is owned by Coordinator.
    """

    def __init__(self, coordinator_url: str, auth_token: str):
        self._coordinator_url = coordinator_url
        self._auth_token = auth_token
        self._client = httpx.AsyncClient(...)

    # =========================================================================
    # Command Polling (Executor polls for scaling commands)
    # =========================================================================

    async def get_process_command(self, pk: str) -> str:
        """Poll for scaling command from Coordinator."""
        response = await self._get(f"/v1/pact/processes/{pk}/command")
        return response.get("command", "")

    async def get_thread_command(self, pk: str) -> str:
        """Poll for thread scaling command."""
        response = await self._get(f"/v1/pact/threads/{pk}/command")
        return response.get("command", "")

    async def get_async_command(self, pk: str) -> str:
        """Poll for async slot scaling command."""
        response = await self._get(f"/v1/pact/async-workers/{pk}/command")
        return response.get("command", "")

    # =========================================================================
    # Status Reporting (Executor reports state to Coordinator)
    # =========================================================================

    async def update_status(self, pk: str, status: str) -> None:
        """Report current status to Coordinator."""
        await self._post(f"/v1/pact/processes/{pk}/status", {"status": status})

    async def update_identity(self, pk: str, identity: dict) -> str:
        """Report identity (hostname, PID, etc.) and get assigned PK."""
        response = await self._post(f"/v1/pact/processes/{pk}/identity", identity)
        return response.get("pk")
```

## Command Protocol

Commands flow from Coordinator to Executors:

| Command | Meaning | Action |
|---------|---------|--------|
| `COUNT=N` | Scale to N workers | Spawn/kill processes/threads |
| `STOP` | Graceful shutdown | Finish current work, then exit |

Example flow:
```
1. Coordinator decides to scale up
2. Coordinator calls: backend.set_process_command(pk, "COUNT=5")
3. This writes to WorkerProcessDAO.current_command in Redis
4. Executor polls: GET /v1/pact/processes/{pk}/command
5. API reads WorkerProcessDAO.current_command, returns {"command": "COUNT=5"}
6. Executor spawns workers to reach count of 5
```

## What We're NOT Doing

### NOT Migrating Coordinator to Pact

The Coordinator's internal worker management uses direct DAO access:
```python
# This code is PROVEN and BATTLE-TESTED - we're NOT changing it
self.coordinator_DAO = await CoordinatorDAO.get(self.coordinator_DAO.pk)
command = self.coordinator_DAO.current_command
```

Why not migrate?
1. **It works perfectly** - The existing code is reliable
2. **Same underlying mechanism** - Pact API uses the same DAOs
3. **Risk vs. reward** - No tangible benefit, potential for bugs
4. **Unnecessary abstraction** - Coordinator already has direct Redis access

### NOT Having Two Pact Backends

Previously, Pact had:
- `RedisBackend` - For direct Redis access (used by Coordinator)
- `HttpProxyBackend` - For HTTP access (used by Executors)

Now, Pact has ONLY:
- `PactClient` (formerly `HttpProxyBackend`) - HTTP client for executors

The Coordinator doesn't need a Pact backend - it uses direct DAO access.

## Files

| File | Purpose |
|------|---------|
| `src/pact/client.py` | PactClient HTTP client for executors |
| `src/blazing_service/server.py` | Pact HTTP API endpoints |
| `src/blazing_executor/service.py` | Uses PactClient for command polling |
| `docker/pyodide-executor/pact.mjs` | JavaScript PactClient for Pyodide |

## Migration Steps

### Step 1: Rename and Simplify

1. Rename `HttpProxyBackend` to `PactClient`
2. Remove `RedisBackend` class entirely
3. Remove `PersistenceBackend` abstract base class
4. Update imports in executor code

### Step 2: Clean Up Tests

1. Remove `RedisBackend` tests
2. Keep `HttpProxyBackend`/`PactClient` tests
3. Update test fixtures

### Step 3: Update Documentation

1. Update this document (done)
2. Update any references to RedisBackend
3. Update executor setup documentation

## Summary

| Before | After |
|--------|-------|
| Pact had RedisBackend + HttpProxyBackend | Pact has PactClient only |
| Coordinator could use Pact internally | Coordinator uses direct DAO access |
| Two code paths for commands | One code path: DAO for internal, HTTP for external |
| Complex abstraction | Simple HTTP client |

**The bottom line:** Pact is a clean HTTP API for external executors. The Coordinator's internal worker management is proven code that we're not touching.
