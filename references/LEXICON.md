# Blazing Lexicon

**Version:** 2.0 (December 2024)
**Status:** Official naming convention for all Blazing components

This document defines the official terminology used throughout the Blazing framework. Consistent naming improves code clarity, reduces cognitive load, and aligns with industry standards.

---

## Core Concepts

### Execution Units

| Term | Definition | Industry Alignment | Example |
|------|------------|-------------------|---------|
| **Step** | An individual unit of work/computation | Airflow: Task, AWS Step Functions: State | `@app.step` decorator for a function |
| **Workflow** | Orchestration of multiple steps | Airflow: DAG, Temporal: Workflow | `@app.workflow` for multi-step processes |
| **Run** | A running instance of a workflow | Airflow: DAG Run, Temporal: Workflow Execution | Created when you call `app.run()` |
| **StepRun** | A running instance of a step within a workflow | Airflow: Task Instance | Internal tracking of step execution |

**Previous Terms (DEPRECATED):**
- ~~Station~~ → Step
- ~~Route~~ → Workflow
- ~~Unit~~ → Run
- ~~Operation~~ → StepRun

---

### Services & Integration

| Term | Definition | Industry Alignment | Example |
|------|------------|-------------------|---------|
| **Service** | Stateful capability with connectors | Microservices: Service, Kubernetes: Service | Database access, API client, ML model |
| **Connector** | Integration with external systems | ✅ Keep (universal term) | REST client, SQL connection, Redis client |

**Previous Terms (DEPRECATED):**
- ~~Service~~ → Service

---

### Infrastructure

| Term | Definition | Industry Alignment | Example |
|------|------------|-------------------|---------|
| **Coordinator** | Orchestrates worker pool and job distribution | Celery: Beat, Airflow: Scheduler | The "brain" that manages everything |
| **Worker** | Processes tasks from queues | ✅ Keep (universal term) | Polls queues and executes steps |
| **Runtime** | Execution environment/isolation mechanism | Node.js Runtime, Python Runtime | Where code actually runs |

**Previous Terms (DEPRECATED):**
- ~~Coordinator~~ → Coordinator
- ~~ExecutorBackend~~ → Runtime

---

### Runtime Types

| Type | Description | Use Case |
|------|-------------|----------|
| **ContainerRuntime** | Docker container-based execution | Production deployments with container isolation |
| **WasmRuntime** | WebAssembly/Pyodide execution | Browser/edge deployment, fast startup |

**Previous Terms (DEPRECATED):**
- ~~DockerExecutorBackend~~ → ContainerRuntime
- ~~PyodideExecutorBackend~~ → WasmRuntime
- ~~ExternalExecutorBackend~~ → REMOVED (not supported)

---

### Execution Modes

| Mode | Description | When to Use |
|------|-------------|-------------|
| **sync** | Synchronous/blocking execution | Database transactions, file I/O, blocking operations |
| **async** | Asynchronous/non-blocking execution | API calls, concurrent operations, I/O-bound tasks |
| **sandboxed** | Untrusted code execution in isolation | User-provided code, tenant code, security-critical |

**Previous Terms (DEPRECATED):**
- ~~BLOCKING~~ → sync
- ~~NON_BLOCKING~~ → async
- ~~*_SANDBOXED~~ → sync/async + sandboxed flag

---

### Worker Pool Management

| Concept | Constant Name | Description |
|---------|--------------|-------------|
| **Warm Pool** | `WARM_POOL_*` | Pre-initialized workers ready to execute |
| Min Sync Workers | `WARM_POOL_MIN_SYNC_WORKERS` | Minimum sync workers (prevents deadlock) |
| Min Async Workers | `WARM_POOL_MIN_ASYNC_WORKERS` | Minimum async workers (prevents deadlock) |
| Min Async Capacity | `WARM_POOL_MIN_ASYNC_CAPACITY` | Minimum A×C for async work |

**Previous Terms (DEPRECATED):**
- ~~PILOT_LIGHT_MIN_P~~ → WARM_POOL_MIN_SYNC_WORKERS
- ~~PILOT_LIGHT_MIN_A~~ → WARM_POOL_MIN_ASYNC_WORKERS
- ~~PILOT_LIGHT_ASYNC_SLOTS~~ → WARM_POOL_MIN_ASYNC_CAPACITY

---

### Data Access & Storage

| Term | Keep/Change | Notes |
|------|-------------|-------|
| **DAO** | ✅ Keep | Data Access Object (standard pattern) |
| **redis** | ✅ Keep | Technology name |
| **queue** | ✅ Keep | Universal term |

---

## API Examples

### Before (Old Lexicon)
```python
from blazing import Blazing

app = Blazing(api_url="...", api_token="...")

# Define a station (now: step)
@app.station
async def process_data(x: int, services=None):
    return x * 2

# Define a route (now: workflow)
@app.route
async def my_pipeline(a: int, b: int, services=None):
    result = await process_data(a, services=services)
    return result + b

# Define a service (now: service)
@app.service
class DatabaseService(BaseService):
    def __init__(self, connector_instances):
        self.db = connector_instances['database']

    async def query(self, sql):
        return await self.db.execute(sql)

# Publish and execute
await app.publish()
run = await app.run("my_pipeline", a=5, b=10)
result = await run.result()
```

### After (New Lexicon)
```python
from blazing import Blazing

app = Blazing(api_url="...", api_token="...")

# Define a step
@app.step
async def process_data(x: int, services=None):
    return x * 2

# Define a workflow
@app.workflow
async def my_pipeline(a: int, b: int, services=None):
    result = await process_data(a, services=services)
    return result + b

# Define a service
@app.service
class DatabaseService(BaseService):
    def __init__(self, connector_instances):
        self.db = connector_instances['database']

    async def query(self, sql):
        return await self.db.execute(sql)

# Publish and execute
await app.publish()
run = await app.run("my_pipeline", a=5, b=10)
result = await run.result()
```

---

## Migration Guide

### Phase 1: Client API (Blazing class)
- ✅ Decorator methods: `@app.step`, `@app.workflow`, `@app.service`
- ✅ Base classes: `BaseService` (was BaseService)
- ✅ Method names: `run()` (was run)
- ✅ Parameter names: `services=None` (was services=None)

### Phase 2: Internal Constants
- ✅ Worker types: `SYNC`, `ASYNC`, `SYNC_SANDBOXED`, `ASYNC_SANDBOXED`
- ✅ Warm pool: `WARM_POOL_MIN_SYNC_WORKERS`, etc.

### Phase 3: Data Models (DAOs)
- ✅ Classes: `StepDAO`, `WorkflowDAO`, `RunDAO`, `StepRunDAO`
- ✅ Redis keys: Update prefixes to use new names

### Phase 4: Documentation
- ✅ Update all docs to use new terminology
- ✅ Add deprecation warnings for old terms
- ✅ Update examples and tutorials

---

## Rationale

### Why "Step" instead of "Station"?
- **Industry standard:** AWS Step Functions, Azure Logic Apps, Airflow Tasks
- **Intuitive:** "Step in a process" is universally understood
- **Clearer:** "Station" has no clear meaning in computing

### Why "Workflow" instead of "Route"?
- **Industry standard:** Temporal Workflows, Airflow DAGs, GitHub Actions Workflows
- **Accurate:** Describes orchestration of multiple steps
- **Clearer:** "Route" implies HTTP routing, not orchestration

### Why "Service" instead of "Service"?
- **Industry standard:** Microservices, Kubernetes Services, AWS Services
- **Professional:** "Service" sounds informal/gamified
- **Accurate:** Describes stateful capabilities with external integrations

### Why "Run" instead of "Unit"?
- **Industry standard:** DAG Run, Workflow Execution, Job Run
- **Clearer:** "Unit" is too generic (unit test, unit of work, etc.)
- **Intuitive:** "Running instance" → "Run"

### Why "Coordinator" instead of "Coordinator"?
- **Industry standard:** Cluster Coordinator, Scheduler, Orchestrator
- **Professional:** "Coordinator" is construction industry jargon
- **Accurate:** Describes coordination of distributed workers

### Why "Runtime" instead of "ExecutorBackend"?
- **Industry standard:** Node.js Runtime, Python Runtime, JVM
- **Concise:** One word instead of two
- **Clearer:** Describes where code executes

### Why "Warm Pool" instead of "Pilot Light"?
- **Industry standard:** Connection pools, worker pools, warm starts
- **Clearer:** "Pilot light" is a metaphor from gas appliances
- **Accurate:** Describes pre-warmed worker capacity

---

## Implementation Status

- [x] Phase 1: Client API (Blazing class) - COMPLETE
  - [x] Decorator aliases: `@app.step`, `@app.workflow`, `@app.service`
  - [x] Base class alias: `BaseService`
  - [x] Method alias: `run()`
- [x] Phase 2: Internal Constants - COMPLETE
  - [x] Warm pool constant aliases (WARM_POOL_MIN_SYNC_WORKERS, etc.)
  - [x] Warm pool accessor functions (get_warm_pool_min_*_workers, etc.)
  - [x] WorkerConfig property aliases (config.warm_pool_min_sync_workers)
  - [x] Environment variable support with deprecation warnings
  - [x] Worker type constants (WORKER_TYPE_SYNC, WORKER_TYPE_ASYNC, etc.)
  - [x] Executor backend aliases (Runtime, ContainerRuntime, WasmRuntime)
  - Note: New names available, old names supported with warnings
- [x] Phase 3: Update Internal Code - COMPLETE
  - [x] Phase 3.1: DAO aliases - `ServiceDAO`, `WorkflowDAO`, `StepDAO`, `RunDAO`, `StepRunDAO`
  - [x] Phase 3.2: String literals → constants (45+ replacements)
  - [x] Phase 3.3: Comments updated (50+ critical comments)
  - [x] Phase 3.4: Log messages updated (42+ critical messages)
  - [x] Function rename: `_load_warm_pool_constants()`
  - [ ] Redis key prefixes (still using old names internally for compatibility)
- [x] Phase 4: Documentation - COMPLETE
  - [x] All user-facing docs updated to new terminology
  - [x] Examples updated to new terminology
  - [x] Technical docs updated to new terminology
- [x] Phase 5: Tests updated - COMPLETE
  - [x] test_new_lexicon.py validates new decorators
  - [x] Backward compatibility tests passing
  - [x] All 395+ unit tests passing
- [x] Phase 6: Deprecation warnings - COMPLETE
  - [x] Docstring warnings added to old decorators
  - [x] Runtime warnings added to @app.station, @app.route, @app.service
  - [x] Runtime warning added to run() method
  - [x] Runtime warning added to cancel_all_incomplete_units() method
  - [x] Runtime warning added to delete_units_and_operations_by_status() method
  - [x] Runtime warning added to get_unitDAOs_by_route_name() method
  - [x] Runtime warning added to BaseService inheritance (via `__init_subclass__`)
  - [x] Environment variable warnings for PILOT_LIGHT_* → WARM_POOL_*

**Status:** v2.0 Implementation Complete (December 8, 2024)
**Breaking Changes in v3.0:** Old names will be removed entirely

---

## Backward Compatibility

### Deprecation Strategy
1. **Alias old names** to new names (v2.0 - current)
2. **Add deprecation warnings** when old names used (v2.1)
3. **Remove old names** entirely (v3.0 - breaking change)

### Example Aliases
```python
# In blazing/__init__.py
BaseService = BaseService  # Deprecated, will be removed in v3.0

# In blazing/blazing.py
class Blazing:
    def station(self, *args, **kwargs):
        """DEPRECATED: Use @app.step instead. Will be removed in v3.0."""
        warnings.warn("@app.station is deprecated, use @app.step", DeprecationWarning)
        return self.step(*args, **kwargs)
```

---

## Complete Terminology Map

| Old Term | New Term | Component Type |
|----------|----------|----------------|
| Station | Step | Execution unit |
| Route | Workflow | Orchestration |
| Unit | Run | Instance |
| Operation | StepRun | Execution tracking |
| Service | Service | Capability |
| Coordinator | Coordinator | Infrastructure |
| ExecutorBackend | Runtime | Isolation |
| DockerExecutorBackend | ContainerRuntime | Runtime type |
| PyodideExecutorBackend | WasmRuntime | Runtime type |
| ExternalExecutorBackend | REMOVED | Runtime type |
| BLOCKING | sync | Execution mode |
| NON_BLOCKING | async | Execution mode |
| PILOT_LIGHT_MIN_P | WARM_POOL_MIN_SYNC_WORKERS | Worker pool |
| PILOT_LIGHT_MIN_A | WARM_POOL_MIN_ASYNC_WORKERS | Worker pool |
| PILOT_LIGHT_ASYNC_SLOTS | WARM_POOL_MIN_ASYNC_CAPACITY | Worker pool |
| services= | services= | Parameter name |
| BaseService | BaseService | Base class |
| run | run | Method name |
| cancel_all_incomplete_units | cancel_all_incomplete_runs | Method name |
| delete_units_and_operations_by_status | delete_runs_and_step_runs_by_status | Method name |
| get_unitDAOs_by_route_name | get_runs_by_workflow_name | Method name |
| StationDAO | StepDAO | Data model |
| WorkflowDAO | WorkflowDAO | Data model |
| UnitDAO | RunDAO | Data model |
| OperationDAO | StepRunDAO | Data model |
| RemoteUnit | RemoteRun | Client class |
| Coordinator | Coordinator | Runtime class |
| Services | Services | Runtime class |
| Route | Workflow | Runtime class |
| Station | Step | Runtime class |
| Unit | Run | Runtime class |
| Operation | StepRun | Runtime class |
| ExecutorBackend | Runtime | Executor base class |
| HTTPExecutorBackend | HTTPRuntime | Executor base class |
| DockerExecutorBackend | ContainerRuntime | Executor implementation |
| PyodideExecutorBackend | WasmRuntime | Executor implementation |
| WORKER_TYPE_BLOCKING | WORKER_TYPE_SYNC | Worker type constant |
| WORKER_TYPE_NON_BLOCKING | WORKER_TYPE_ASYNC | Worker type constant |

---

**Document Version:** 2.0
**Last Updated:** December 7, 2024
**Authors:** Blazing Core Team + Claude Code
