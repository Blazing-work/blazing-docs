# Blazing Architecture Overview

This document explains how Blazing orchestrates long-running, stateful pipelines across Redis, Python processes, and asynchronous workers. Use it as the reference for understanding core services, execution flow, and how to extend the platform.

> **New to Blazing?** Start with the [Getting Started Guide](getting-started.md) to build and run your first pipeline.

---

## Table of Contents

1. [High-Level Topology](#high-level-topology)
2. [Core Runtime Components](#core-runtime-components)
   - [Redis State Store](#redis-state-store)
   - [Coordinator](#coordinator)
   - [Worker Processes](#worker-processes)
   - [Worker Threads & Controllers](#worker-threads--controllers)
   - [Workflows, Steps, Runs, Step Runs](#routes-stations-units-operations)
   - [Services](#services)
   - [Connectors](#connectors)
3. [Execution Lifecycle](#execution-lifecycle)
4. [Scheduling & Worker Mix Optimisation](#scheduling--worker-mix-optimisation)
5. [State, Observability & Safety](#state-observability--safety)
6. [Authoring Pipelines](#authoring-pipelines)
7. [Running the Runtime](#running-the-runtime)
8. [Related Guides](#related-guides)

---

## High-Level Topology

Blazing splits orchestration into distinct control layers:

```
┌───────────────────────────────────────────────┐
│ Redis (State Store & Task Queues)             │
│  • Global state & metadata                    │
│  • Workflow / step registry                   │
│  • Connector definitions                      │
│  • Operational telemetry                      │
└───────────────────────────────────────────────┘
              ▲                    ▲
              │                    │
              │ Redis + Arrow      │
              │ queues / tables    │
              │                    │
┌────────────────────┐    ┌────────────────────┐
│ Coordinator (per host) │    │ Coordinator (per host) │
│  • Manages worker  │    │  • Manages worker  │
│    processes       │    │    processes       │
│  • Applies worker  │    │  • Applies worker  │
│    mix decisions   │    │    mix decisions   │
└─────────▲──────────┘    └─────────▲──────────┘
          │                         │
          │ Commands & telem.       │
          │                         │
  ┌─────────────────┐       ┌─────────────────┐
  │ Worker Processes │ ...  │ Worker Processes │
  │  • Async or      │      │  • Async or      │
  │    blocking role │      │    blocking role │
  │  • Host steps │      │  • Host steps │
  └─────────────────┘       └─────────────────┘
              │
              ▼
  ┌────────────────────────────────────────────┐
  │ BTOP Dashboard (Web Monitoring)            │
  │  • Real-time worker statistics             │
  │  • Queue depths and throughput             │
  │  • System health visualization             │
  └────────────────────────────────────────────┘
```

Workflows submit work to Redis queues. Foremen fetch assignments, provision worker processes, and continuously rebalance the mix of asynchronous and blocking workers. Each worker process executes step operations and persists results back through Redis-backed queues and Arrow Flight transport. The BTOP web dashboard provides real-time monitoring and observability.

---

## Core Runtime Components

### Redis State Store

Redis (or KeyDB) serves as the single source of truth for configuration and state, storing:

- Registered workflows, steps, and services (`WorkflowDAO`, `StepDAO`, `ServiceDAO`)
- Connector configurations (with optional encryption handled via `ConnectorDAO`)
- Active units, operations, and their statuses (`UnitDAO`, `OperationDAO`)
- Worker and coordinator health metrics

Because all metadata lives in Redis, components can be restarted without losing orchestration state. The BTOP web dashboard provides monitoring and observability by querying Redis state through the `/v1/stats` API.

### Coordinator

Each machine that runs Blazing workloads hosts a Coordinator process. Responsibilities include:

- Spawning, supervising, and retiring worker processes
- Collecting timing statistics from completed operations
- Applying worker mix optimisation decisions (async vs blocking, concurrency per async worker)
- Reporting telemetry to HQ so the broader system can monitor capacity and health

Foremen communicate exclusively through Redis; no peer-to-peer coordination is required.

### Worker Processes

Worker processes execute step functions. When launched, a worker is assigned one of two roles:

- **Blocking worker**: Designed for CPU-heavy or long-running tasks. Processes one operation at a time.
- **Async worker**: Runs an asyncio/uvloop event loop and can service multiple operations concurrently.

Workers are intentionally single-purpose to simplify resource accounting and avoid cross-load interference.

### Worker Threads & Controllers

Inside each worker process, a `WorkerThread` manages queue polling and lifecycle events. Async workers additionally maintain a configurable number (`C`) of coroutine controllers (`WorkerAsync`) that run operations concurrently. Blocking workers keep a single controller that executes synchronously.

### Workflows, Steps, Runs, Step Runs

- **Route**: An `async` function decorated with `@app.workflow` that defines orchestration logic.
- **Station**: A function (sync or async) decorated with `@app.step`. Each step has an independent queue.
- **Unit**: Represents a single run through a workflow. Tracks arguments, results, and status.
- **Operation**: A step invocation tied to a specific unit. Workers dequeue operations, execute the step function, and persist results.

### Services

Services bundle reusable logic and long-lived resources. Defining a class that inherits `BaseService` and decorating it with `@app.service` registers it with HQ. Stations receive a `services` mapping that exposes instantiated service classes, enabling code reuse without repeated setup/teardown.

### Connectors

Connectors capture external integration details (database DSNs, API credentials, SSH tunnels). HQ stores encrypted configuration, and services or workflows request connector instances as needed. Because connectors are declared centrally, credential rotation and auditing are straightforward.

---

## Execution Lifecycle

1. **Definition**: Decorated workflows, steps, and services are registered during application start-up. HQ persists metadata and queues are prepared.
2. **Publication**: Calling `await app.publish()` runs aredis-om migrations so DAO schemas exist inside Redis.
3. **Task Submission**: `await app.run("workflow_name", *args, **kwargs)` enqueues a new unit and seeds its first operation.
4. **Dispatch**: Foremen poll HQ for outstanding operations, assign them to worker processes, and update telemetry.
5. **Processing**: Workers fetch operations from step queues, execute step functions (reusing services and connectors), and record results plus timing metrics.
6. **Completion**: Once all operations in a workflow finish, the unit status is marked complete and awaiting clients receive the result payload.

This lifecycle is entirely event-driven and resilient to restarts because all progress markers live in Redis.

---

## Scheduling & Worker Mix Optimisation

To maintain throughput without over-provisioning, Foremen run a maintenance loop that:

1. Samples recent operation timings and queue backlogs.
2. Scores candidate mixes of blocking workers (`P`), async workers (`A`), and concurrency per async worker (`C`).
3. Applies the best mix that respects safety invariants:
   - Global capacity cap (`P + A·C ≤ MAX_CONCURRENT_TASKS_PER_COORDINATOR`)
   - Pilot light guarantee (`P ≥ 1` for blocking workloads, `A ≥ 1` and `A·C ≥ 3` for async workloads)
4. Records decisions and rationale in `worker_mix.log`.

For detailed algorithms, staged rollouts, and telemetry structure, see [worker-mix-optimizer.md](worker-mix-optimizer.md).

---

## State, Observability & Safety

- **Persistence**: All DAOs store data in Redis hashes or sorted sets. Large payloads (e.g., data frames) can route through Apache Arrow Flight for zero-copy transport.
- **Logging**: Worker mix transitions, queue backlogs, and urgency scores are logged per maintenance tick. Scripts (`blazing_service/monitoring/btop.py`, `blazing_service/monitoring/monitor_coordinator_charts.py`) visualise live metrics.
- **Cleanup**: `app.cancel_all_incomplete_units()` and `app.delete_units_and_operations_by_status()` help recover from interrupted runs.
- **Security**: Connector credentials can be AES-encrypted. Redis ACLs and network isolation remain the operator’s responsibility.

---

## Authoring Pipelines

Below is a minimal example demonstrating the primary decorators. Note the absence of parentheses on the decorators—Blazing injects metadata at definition time.

```python
from blazing import Blazing, BaseService

app = Blazing(redis_config={"host": "localhost", "port": 6380})

@app.service
class DataAccess(BaseService):
    def __init__(self, connector_instances):
        self.db = connector_instances["PostgreSQL_readonly"]

    async def fetch_customer(self, customer_id):
        query = "SELECT * FROM customers WHERE id = :id"
        async with self.db.get_session_factory()() as session:
            result = await session.execute(query, {"id": customer_id})
            return result.fetchone()

@app.step
async def enrich(request, services=None):
    customer = await services.DataAccess.fetch_customer(request["customer_id"])
    request["customer"] = dict(customer) if customer else None
    return request

@app.step
async def dispatch(payload, services=None):
    # Call downstream API, queue message, etc.
    return {"status": "delivered", "payload": payload}

@app.workflow
async def customer_pipeline(request, services=None):
    enriched = await enrich(request)
    return await dispatch(enriched)
```

Key points:

- Routes are `async` functions that may call stations directly or await them.
- Stations receive a `services` keyword argument; provide a default (`None`) to keep signatures compatible.
- Services are instantiated once per worker process and shared across station invocations.

---

## Running the Runtime

1. **Publish metadata**:
   ```python
   async with app:
       await app.publish()
   ```
2. **Start HQ**: Launch `scripts/start_hq.py` (configure Redis connection via environment variables).
3. **Start Foremen**: Run `scripts/start_coordinator.py` on each compute host. Configure encryption keys or connector pools as needed.
4. **Submit work**:
   ```python
   unit = await app.run("customer_pipeline", {"customer_id": 123})
   result = await unit.wait_for_result()
   ```
5. **Monitor**: Use `blazing.btop` or `monitor_coordinator_charts.py` to watch queue depth, worker utilisation, and mix transitions.

Because HQ and Foremen are independent processes, you can deploy them via systemd, containers, or orchestration platforms of your choice.

---

## Related Guides

- [Getting Started Guide](getting-started.md): A step-by-step tutorial for new users.
- [Deployment Guide](deployment.md): Best practices for deploying Blazing to production.
- [API Reference](api-reference.md): Detailed information about the Blazing API.
- [Glossary](glossary.md): Definitions of common Blazing terms.
- [Benchmarking Guide](benchmarking.md): Methodology for performance measurement and cross-framework comparisons.
- [Testing Guide](testing.md): How to validate worker mix behaviour under varying workloads.
- [Worker Mix Optimiser](worker-mix-optimizer.md): Deep dive into the optimisation algorithm, staged rollouts, and telemetry.
- [Framework Comparisons](comparisons.md): Positioning Blazing against Celery, Dask, and Modal.

For production hardening checklists, monitoring recommendations, and deployment blueprints, contact the Blazing team or refer to forthcoming solution briefs.
