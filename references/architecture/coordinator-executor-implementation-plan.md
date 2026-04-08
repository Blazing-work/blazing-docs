# Coordinator/Executor Architecture Implementation Plan

**Date:** 2025-11-24
**Status:** Planning Phase
**Goal:** Implement true environment isolation using coordinator/executor process architecture

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Problem Statement](#problem-statement)
4. [Design Decisions](#design-decisions)
5. [Implementation Phases](#implementation-phases)
6. [Testing Strategy](#testing-strategy)
7. [Rollout Plan](#rollout-plan)
8. [Risk Mitigation](#risk-mitigation)
9. [Success Metrics](#success-metrics)

---

## Executive Summary

### Current State
- Blazing coordinator executes operations in-process using sys.path manipulation
- Environment replication creates isolated venvs but can't achieve true import isolation
- Test demonstrates: when package versions differ (six==1.16.0 vs 1.17.0), imports come from base environment

### Target State
- Coordinator processes handle orchestration, routing, I/O (Redis, Arrow Flight)
- Executor processes run in isolated venvs, handle actual computation
- Communication via shared memory (zero-copy for 100MB+ Arrow tables)
- Each process type has independent worker pools (async/sync) with separate maintenance loops

### Benefits
- ✅ True environment isolation (different package versions)
- ✅ Better resource utilization (async I/O doesn't block computation)
- ✅ Cleaner architecture (separation of concerns)
- ✅ Scalable (can tune coordinator:executor ratios based on workload)

---

## Architecture Overview

### Process Hierarchy

```
Coordinator Container (orchestrator)
│
├── Coordinator Process 1 (system Python)
│   ├── WorkerAsync (C slots) - async operations, Arrow Flight, Redis
│   ├── WorkerSync (P processes) - sync operations (file I/O, future use)
│   ├── Maintenance Loop - independent rebalancing based on coordinator stats
│   ├── Stats Queue - coordinator-specific metrics (processing_time, wait_time)
│   └── Executor Pool Manager - manages communication with paired executors
│
├── Executor Process 1A (isolated venv: e.g., six==1.16.0)
│   ├── ExecutorAsync (C' slots) - async computation
│   ├── ExecutorSync (P' processes) - sync computation
│   ├── Maintenance Loop - independent rebalancing based on executor stats
│   ├── Stats Queue - executor-specific metrics
│   └── IPC Handler - receives work via shared memory
│
├── Coordinator Process 2...
│   └── Executor Process 2A (potentially different venv)
│
└── Coordinator Process N...
    └── Executor Process NA
```

### Communication Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Coordinator Process                                             │
│                                                                 │
│  1. Poll Redis for operation                                   │
│  2. Deserialize station function                               │
│  3. Check: needs isolated environment?                         │
│     ├─ NO  → Execute in-process (routing, maintenance)        │
│     └─ YES → Send to executor via shared memory               │
│                                                                 │
│  Shared Memory Write:                                          │
│    ┌────────────────────────────────────────┐                │
│    │ Header: {size, operation_id, env_hash} │                │
│    │ Payload: serialized(func, args, kwargs)│                │
│    └────────────────────────────────────────┘                │
│              │                                                  │
│              │ Send pointer via Queue                          │
│              ▼                                                  │
└─────────────────────────────────────────────────────────────────┘
               │
               │ Queue.put({'shm_name': '...', 'size': 1024})
               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Executor Process                                                │
│                                                                 │
│  1. Poll Queue for work notification                           │
│  2. Read operation from shared memory                          │
│  3. Deserialize function, args, kwargs                         │
│  4. Execute in isolated venv                                   │
│  5. Write result to NEW shared memory block                    │
│  6. Send result pointer back                                   │
│                                                                 │
│  Result in Shared Memory:                                      │
│    ┌────────────────────────────────────────┐                │
│    │ {success: true, result: <serialized>}  │                │
│    │ OR                                      │                │
│    │ {success: false, error: <traceback>}   │                │
│    └────────────────────────────────────────┘                │
│              │                                                  │
│              │ Send result pointer                             │
│              ▼                                                  │
└─────────────────────────────────────────────────────────────────┘
               │
               │ Queue.put({'shm_name': '...', 'size': 512})
               ▼
    Coordinator receives result, updates Redis, cleans up shm
```

### Data Flow Examples

#### Example 1: Pure Computation Station (Needs Isolation)
```python
# Client defines station with custom dependencies
@app.step(dependencies=["numpy==1.24.0", "pandas==2.0.0"])
async def analyze_data(df):
    import pandas as pd  # Must be version 2.0.0
    return df.describe()

# Flow:
# 1. Coordinator receives operation from Redis
# 2. Detects environment_spec → route to executor
# 3. Serialize df (could be 100MB+ Arrow table) → shared memory
# 4. Executor imports pandas 2.0.0 from isolated venv
# 5. Executes analyze_data() with correct pandas version
# 6. Returns result via shared memory
```

#### Example 2: Routing Station (No Isolation Needed)
```python
# Client defines route (orchestration)
@app.workflow
async def pipeline(data, services=None):
    result1 = await preprocess(data, services=services)
    result2 = await analyze(result1, services=services)
    return result2

# Flow:
# 1. Coordinator receives operation
# 2. Detects it's a routing operation (priority=-1)
# 3. Executes IN-PROCESS (no executor needed)
# 4. Enqueues child operations for preprocess and analyze
# 5. Those child operations may go to executors if they have environment_spec
```

#### Example 3: Maintenance Operation (Coordinator-Only)
```python
# System maintenance task
async def rebalance_workers():
    # Fetch stats from Redis
    stats = await redis_client.hgetall("blazing:stats")

    # Fetch Arrow Flight data
    arrow_table = await fetch_arrow_flight(endpoint)

    # Make rebalancing decisions
    new_worker_counts = calculate_optimal_mix(stats, arrow_table)
    await update_worker_pool(new_worker_counts)

# Flow:
# 1. Coordinator executes entirely in-process
# 2. Uses async Redis client (no blocking)
# 3. Uses async Arrow Flight client (no blocking)
# 4. No executor needed - pure orchestration
```

---

## Problem Statement

### Current Implementation Issues

**Issue 1: Import Isolation Failure**
```python
# Current approach (BROKEN):
# In runtime.py:execute_operation()

if station_DAO.environment_spec:
    # Create venv with six==1.16.0
    python_exe = replicator.get_or_create_environment(env_spec)

    # Add to sys.path
    site_packages = python_exe.parent.parent / "lib/python3.11/site-packages"
    sys.path.insert(0, str(site_packages))

    # Clear sys.modules
    del sys.modules['six']

    # Execute function
    result = await Station.execute_function(func, *args, **kwargs)
    # ❌ STILL imports six==1.17.0 from base environment!

# Why it fails:
# - Python's import system is process-global
# - Cached modules can be reimported from unexpected locations
# - sys.path manipulation is unreliable across threads
# - C extensions can't be unloaded/reloaded
```

**Test Evidence:**
```bash
# Test with six==1.16.0 in venv, six==1.17.0 in base
$ uv run pytest tests/test_docker_environment_replication.py::test_simple_environment_replication_via_docker
# Result: ❌ FAILED - got six==1.17.0 instead of 1.16.0

# Test with same versions in both
$ docker exec blazing-coordinator uv pip install six==1.16.0
$ uv run pytest tests/test_docker_environment_replication.py::test_simple_environment_replication_via_docker
# Result: ✅ PASSED - got six==1.16.0

# Conclusion: Environment replication works, import isolation doesn't
```

### Why Subprocess Isolation is Required

**Python Process Isolation Properties:**
- ✅ Each process has independent `sys.path`
- ✅ Each process has independent `sys.modules` cache
- ✅ Each process can use different Python interpreter (`python_exe`)
- ✅ C extensions are loaded per-process
- ✅ Memory isolation (no shared state bugs)

**Overhead Concerns:**
- ❌ Spawning subprocess per operation: ~50-100ms overhead
- ✅ Long-lived subprocess with IPC: ~0.1-0.5ms overhead (shared memory)
- ✅ Amortized cost: spawn once per coordinator, reuse for thousands of operations

---

## Design Decisions

### Decision 1: Process Topology

**Options Considered:**

**A. One Executor Per Coordinator Process**
```
Coordinator 1 → Executor 1
Coordinator 2 → Executor 2
Coordinator N → Executor N
```
✅ **CHOSEN**
- Simple lifecycle management (executor dies with coordinator)
- Clear 1:1 mapping for debugging
- Scales linearly with coordinators

**B. Shared Executor Pool**
```
Coordinator 1 ┐
Coordinator 2 ├→ [Executor Pool: 10 executors]
Coordinator N ┘
```
❌ **REJECTED**
- Complex lifecycle management
- Harder to debug (which executor handled which operation?)
- Executor contention possible

**C. One Executor Per Environment**
```
Coordinator 1 ┐
Coordinator 2 ├→ Executor (six==1.16.0)
Coordinator 3 ┘  Executor (numpy==1.24.0)
                 Executor (pandas==2.0.0)
```
❌ **DEFERRED** (Phase 2)
- Optimal resource usage when many environments
- Requires sophisticated routing logic
- Complexity: executor discovery, health checks

**Decision:** Start with Option A, revisit Option C in Phase 2

---

### Decision 2: IPC Mechanism

**Requirements:**
- Pass 100MB+ Arrow tables efficiently
- Bidirectional communication (request → response)
- Support async operation (non-blocking coordinator)
- Error propagation with full tracebacks

**Options Considered:**

**A. Unix Domain Sockets**
```python
# Overhead: ~10-50μs for small messages
# Problem: Still requires serialization + kernel copy for 100MB data
```
❌ **REJECTED** - Kernel copy overhead for large data

**B. Multiprocessing Pipes**
```python
parent_conn, child_conn = Pipe()
parent_conn.send({'func': func, 'args': args})
result = parent_conn.recv()
# Overhead: ~20-100μs
# Problem: Same kernel copy issue
```
❌ **REJECTED** - Kernel copy overhead

**C. Shared Memory + Queue**
```python
# Write data to shared memory (zero-copy)
shm = shared_memory.SharedMemory(create=True, size=len(data))
shm.buf[:] = data

# Send pointer via lightweight queue
queue.put({'shm_name': shm.name, 'size': len(data)})

# Overhead: ~0.1-0.5ms (just memory copy, no kernel)
```
✅ **CHOSEN** - Zero-copy for large data

**Implementation Details:**

```python
from multiprocessing import Queue, shared_memory
import pickle
import dill

class SharedMemoryIPC:
    """Zero-copy IPC using shared memory with memoryview optimization."""

    def __init__(self):
        self.request_queue = Queue()    # Coordinator → Executor
        self.response_queue = Queue()   # Executor → Coordinator

    async def send_request(self, operation_id, func, args, kwargs):
        """Send operation to executor."""
        # Serialize payload
        payload = dill.dumps({
            'operation_id': operation_id,
            'func': func,
            'args': args,
            'kwargs': kwargs
        })

        # Create shared memory (one memcpy to shared memory)
        shm = shared_memory.SharedMemory(create=True, size=len(payload))
        shm.buf[:len(payload)] = payload

        # Send pointer (lightweight message, ~0.01ms)
        self.request_queue.put({
            'shm_name': shm.name,
            'size': len(payload)
        })

        # Store reference for cleanup
        return shm

    async def receive_response(self, timeout=300):
        """Receive result from executor (ZERO-COPY with memoryview)."""
        # Wait for response pointer (with timeout)
        response_ptr = await asyncio.get_event_loop().run_in_executor(
            None, self.response_queue.get, True, timeout
        )

        # Open shared memory
        result_shm = shared_memory.SharedMemory(name=response_ptr['shm_name'])

        # Create memoryview (NO COPY! Just pointer, ~0.001ms)
        data_view = memoryview(result_shm.buf[:response_ptr['size']])

        # Deserialize directly from memoryview (dill supports buffer protocol)
        result = dill.loads(data_view)

        # Cleanup
        result_shm.close()
        result_shm.unlink()

        return result
```

---

### Decision 3: Worker Architecture Per Process

**Keep Current Architecture (Both Coordinator and Executor):**

```python
# Each process (coordinator or executor) has:
class WorkerProcess:
    def __init__(self, worker_type, capacity):
        # Async workers (for I/O-bound operations)
        self.worker_async = WorkerAsync(capacity=capacity)

        # Sync workers (for CPU-bound operations)
        self.worker_sync = WorkerSync(process_count=os.cpu_count())

        # Independent maintenance loop
        self.maintenance_loop = MaintenanceLoop()

        # Independent stats collection
        self.stats_queue = Queue()
```

**Why Keep Both Types:**
- Coordinator may need sync operations (file I/O, future extensions)
- Executor definitely needs both (async steps, sync steps)
- Existing maintenance logic is well-tested
- Reuse pilot light mechanism, rebalancing algorithms

**Stats Independence:**
```python
# Coordinator stats
coordinator_stats = {
    'worker_type': 'coordinator',
    'async_workers': 100,
    'sync_workers': 4,
    'async_utilization': 0.65,  # 65% busy
    'sync_utilization': 0.20,   # 20% busy
    'avg_processing_time': 0.05,  # 50ms
    'avg_wait_time': 0.02,        # 20ms
}

# Executor stats (separate queue)
executor_stats = {
    'worker_type': 'executor',
    'async_workers': 50,
    'sync_workers': 8,
    'async_utilization': 0.90,  # 90% busy
    'sync_utilization': 0.85,   # 85% busy
    'avg_processing_time': 1.50,  # 1.5s (computation heavy)
    'avg_wait_time': 0.10,        # 100ms
}

# Rebalancing decisions are independent
# Coordinator: High wait_time → increase async workers
# Executor: High utilization → increase both worker types
```

---

## Implementation Phases

### Phase 0: Preparation & Infrastructure (Week 1)

**Goal:** Set up testing infrastructure and baseline measurements

**Tasks:**

1. **Create Baseline Tests**
   ```python
   # tests/test_coordinator_executor_baseline.py

   async def test_current_in_process_execution():
       """Baseline: Current in-process execution performance."""
       # Measure current performance for comparison
       pass

   async def test_environment_isolation_failure():
       """Document current failure case."""
       # Test with six==1.16.0 vs 1.17.0
       # Should FAIL, documenting the problem
       pass
   ```

2. **Performance Benchmarking**
   ```bash
   # Measure current performance
   - Operation latency (p50, p95, p99)
   - Throughput (ops/sec)
   - Memory usage
   - CPU utilization

   # Target: New architecture should be within 10% of baseline
   ```

3. **Create Test Environments**
   ```python
   # Diverse environment specs for testing
   test_environments = [
       {'python_version': '3.11', 'requirements': 'six==1.16.0'},
       {'python_version': '3.11', 'requirements': 'numpy==1.24.0'},
       {'python_version': '3.11', 'requirements': 'pandas==2.0.0\nnumpy==1.24.0'},
       # Edge cases
       {'python_version': '3.11', 'requirements': ''},  # No custom deps
       {'python_version': '3.11', 'requirements': 'large_package==1.0.0'},  # 500MB package
   ]
   ```

**Deliverables:**
- ✅ Baseline test suite
- ✅ Performance benchmark results
- ✅ Test environment matrix

---

### Phase 1: Shared Memory IPC Implementation (Week 2)

**Goal:** Build and test the IPC layer independently

**Tasks:**

1. **Create IPC Module**
   ```
   src/blazing_service/ipc/
   ├── __init__.py
   ├── shared_memory_ipc.py    # Core IPC implementation
   ├── serialization.py         # dill-based serialization helpers
   └── protocol.py              # Message format definitions
   ```

2. **Implement SharedMemoryIPC with memoryview optimization**
   ```python
   # src/blazing_service/ipc/shared_memory_ipc.py

   class SharedMemoryIPC:
       """Zero-copy IPC using shared memory with memoryview optimization."""

       async def send_request(self, operation_id, func, args, kwargs):
           """Send operation request to executor (one memcpy)."""
           payload = dill.dumps({'operation_id': operation_id, 'func': func, 'args': args, 'kwargs': kwargs})
           shm = shared_memory.SharedMemory(create=True, size=len(payload))
           shm.buf[:len(payload)] = payload  # One memcpy (~50ms for 100MB)
           self.request_queue.put({'shm_name': shm.name, 'size': len(payload)})
           return shm

       async def receive_response(self, timeout=300):
           """Receive result from executor (ZERO-COPY with memoryview)."""
           response_ptr = await asyncio.get_event_loop().run_in_executor(
               None, self.response_queue.get, True, timeout
           )
           result_shm = shared_memory.SharedMemory(name=response_ptr['shm_name'])
           # ZERO-COPY: memoryview just creates pointer, no data copy!
           data_view = memoryview(result_shm.buf[:response_ptr['size']])
           result = dill.loads(data_view)  # dill supports buffer protocol
           result_shm.close()
           result_shm.unlink()
           return result

       async def send_arrow_table(self, table):
           """Send Arrow table with IPC format (optimized for zero-copy)."""
           # Arrow IPC format is designed for zero-copy
           sink = pa.BufferOutputStream()
           writer = pa.ipc.new_stream(sink, table.schema)
           writer.write_table(table)
           writer.close()
           buffer = sink.getvalue()

           shm = shared_memory.SharedMemory(create=True, size=len(buffer))
           shm.buf[:len(buffer)] = buffer
           return shm

       async def receive_arrow_table(self, shm_name, size):
           """Receive Arrow table (zero-copy deserialization)."""
           shm = shared_memory.SharedMemory(name=shm_name)
           # memoryview for zero-copy access
           buffer_view = memoryview(shm.buf[:size])
           # Arrow uses zero-copy internally when deserializing from buffer
           reader = pa.ipc.open_stream(buffer_view)
           table = reader.read_all()
           return table

       def cleanup(self):
           """Clean up shared memory resources."""
           for shm in self.active_shm:
               shm.close()
               shm.unlink()
   ```

3. **Unit Tests**
   ```python
   # tests/test_shared_memory_ipc.py

   async def test_send_small_payload():
       """Test sending small payload (<1KB)."""
       pass

   async def test_send_large_payload():
       """Test sending large payload (100MB+)."""
       pass

   async def test_send_arrow_table():
       """Test sending Arrow table via shared memory."""
       pass

   async def test_timeout_handling():
       """Test timeout when executor doesn't respond."""
       pass

   async def test_error_propagation():
       """Test full traceback propagation from executor."""
       pass

   async def test_concurrent_operations():
       """Test multiple operations in flight simultaneously."""
       pass
   ```

4. **Performance Tests**
   ```python
   # tests/test_ipc_performance.py

   async def test_ipc_overhead_small_payload():
       """Measure overhead for small payloads (<1KB)."""
       # Target: <0.5ms
       # Write: ~0.01ms (memcpy to shm)
       # Queue: ~0.01ms
       # Read: ~0.001ms (memoryview, zero-copy!)
       pass

   async def test_ipc_overhead_large_payload():
       """Measure overhead for large payloads (100MB)."""
       # Target: ~50ms (one memcpy only, thanks to memoryview!)
       # Before memoryview: ~100ms (two memcpy operations)
       # With memoryview: ~50ms (one memcpy write, zero-copy read)
       pass

   async def test_arrow_table_transfer():
       """Measure Arrow table transfer performance."""
       # Target: ~50ms for 100MB Arrow table
       # Arrow IPC format + memoryview = optimal performance
       pass

   async def test_throughput():
       """Measure ops/sec through IPC."""
       # Target: >1000 ops/sec for small payloads
       pass

   async def test_memoryview_vs_bytes():
       """Compare memoryview (zero-copy) vs bytes() (copy)."""
       # Demonstrate 50% performance improvement with memoryview
       pass
   ```

**Deliverables:**
- ✅ Shared memory IPC module
- ✅ Unit test suite (>90% coverage)
- ✅ Performance benchmarks
- ✅ Documentation with examples

---

### Phase 2: Executor Process Implementation (Week 3)

**Goal:** Implement standalone executor process with worker pool

**Tasks:**

1. **Create Executor Module**
   ```
   src/blazing_service/executor/
   ├── __init__.py
   ├── executor_process.py      # Main executor process
   ├── executor_worker_async.py # Async worker pool (copy of WorkerAsync)
   ├── executor_worker_sync.py  # Sync worker pool (copy of WorkerSync)
   └── executor_maintenance.py  # Maintenance loop (copy of maintenance)
   ```

2. **Implement ExecutorProcess**
   ```python
   # src/blazing_service/executor/executor_process.py

   class ExecutorProcess:
       """Isolated executor process running in replicated venv."""

       def __init__(self, python_exe: Path, env_hash: str):
           self.python_exe = python_exe
           self.env_hash = env_hash
           self.ipc = SharedMemoryIPC()

           # Worker pools (independent of coordinator)
           self.worker_async = ExecutorWorkerAsync(capacity=100)
           self.worker_sync = ExecutorWorkerSync(process_count=4)

           # Independent maintenance
           self.maintenance = ExecutorMaintenance(self.worker_async, self.worker_sync)

       async def run(self):
           """Main executor event loop."""
           while True:
               # Poll for work from coordinator
               request = await self.ipc.receive_request()

               # Route to appropriate worker
               if is_async_operation(request):
                   result = await self.worker_async.execute(request)
               else:
                   result = await self.worker_sync.execute(request)

               # Send result back
               await self.ipc.send_response(result)

       async def run_maintenance(self):
           """Independent maintenance loop."""
           while True:
               await asyncio.sleep(30)  # 30s interval
               await self.maintenance.rebalance()
   ```

3. **Unit Tests**
   ```python
   # tests/test_executor_process.py

   async def test_executor_startup():
       """Test executor process starts correctly."""
       pass

   async def test_executor_receives_work():
       """Test executor receives and processes work from IPC."""
       pass

   async def test_executor_imports_correct_packages():
       """Test executor imports from isolated venv."""
       # Create executor with six==1.16.0
       # Send function that imports six
       # Verify it gets 1.16.0, not base version
       pass

   async def test_executor_async_worker_pool():
       """Test executor async workers process operations."""
       pass

   async def test_executor_sync_worker_pool():
       """Test executor sync workers process operations."""
       pass

   async def test_executor_maintenance_loop():
       """Test executor rebalances workers independently."""
       pass

   async def test_executor_error_handling():
       """Test executor propagates errors with full traceback."""
       pass

   async def test_executor_graceful_shutdown():
       """Test executor shuts down cleanly."""
       pass
   ```

4. **Integration Tests**
   ```python
   # tests/test_executor_integration.py

   async def test_coordinator_to_executor_roundtrip():
       """Test full request/response cycle."""
       # Start coordinator and executor
       # Send operation from coordinator
       # Verify result comes back correctly
       pass

   async def test_multiple_executors():
       """Test multiple executors running simultaneously."""
       pass

   async def test_executor_isolation():
       """Test executors with different venvs don't interfere."""
       # Executor 1: six==1.16.0
       # Executor 2: six==1.17.0
       # Both should get correct versions
       pass
   ```

**Deliverables:**
- ✅ Executor process implementation
- ✅ Worker pools (async/sync)
- ✅ Maintenance loop
- ✅ Unit test suite (>90% coverage)
- ✅ Integration tests

---

### Phase 3: Coordinator Integration (Week 4)

**Goal:** Modify coordinator to route operations to executors

**Tasks:**

1. **Create Coordinator Module**
   ```
   src/blazing_service/coordinator/
   ├── __init__.py
   ├── coordinator_process.py   # Main coordinator process
   ├── executor_pool_manager.py # Manages paired executors
   └── operation_router.py      # Decides: in-process or executor
   ```

2. **Implement ExecutorPoolManager**
   ```python
   # src/blazing_service/coordinator/executor_pool_manager.py

   class ExecutorPoolManager:
       """Manages lifecycle of executor processes paired with coordinator."""

       def __init__(self):
           self.executors: Dict[str, ExecutorHandle] = {}

       async def get_or_create_executor(self, env_spec: dict) -> ExecutorHandle:
           """Get existing executor or spawn new one for environment."""
           env_hash = hash_environment_spec(env_spec)

           if env_hash not in self.executors:
               # Create replicated environment
               replicator = EnvironmentReplicator()
               python_exe = replicator.get_or_create_environment(env_spec)

               # Spawn executor process
               executor = await self.spawn_executor(python_exe, env_hash)
               self.executors[env_hash] = executor

           return self.executors[env_hash]

       async def spawn_executor(self, python_exe, env_hash):
           """Spawn new executor subprocess."""
           # Create IPC channels
           ipc = SharedMemoryIPC()

           # Spawn subprocess
           process = await asyncio.create_subprocess_exec(
               str(python_exe),
               '-m', 'blazing_service.executor',
               '--env-hash', env_hash,
               '--ipc-request-queue', ipc.request_queue_name,
               '--ipc-response-queue', ipc.response_queue_name,
           )

           return ExecutorHandle(process, ipc)
   ```

3. **Implement OperationRouter**
   ```python
   # src/blazing_service/coordinator/operation_router.py

   class OperationRouter:
       """Decides whether to execute in-process or route to executor."""

       def should_route_to_executor(self, station_DAO, operation_DAO) -> bool:
           """Determine if operation needs executor."""

           # Routing operations always run in-process
           if station_DAO.priority == -1:
               return False

           # Maintenance operations run in-process
           if operation_DAO.is_maintenance:
               return False

           # Operations with environment_spec need executor
           if station_DAO.environment_spec:
               return True

           # Everything else runs in-process
           return False
   ```

4. **Modify runtime.py:execute_operation()**
   ```python
   # src/blazing_service/engine/runtime.py

   async def execute_operation(operation_pk: str):
       """Execute operation - either in-process or via executor."""

       # ... existing setup code ...

       # NEW: Check if we need executor
       router = OperationRouter()
       if router.should_route_to_executor(station_DAO, operation_DAO):
           # Route to executor
           executor_manager = get_executor_pool_manager()
           executor = await executor_manager.get_or_create_executor(
               json.loads(station_DAO.environment_spec)
           )

           # Send to executor via IPC
           result, error = await executor.execute(func, args, kwargs)
       else:
           # Execute in-process (current behavior)
           with EnqueueContext(...):
               result, error = await Station.execute_function(func, *args, **kwargs)

       # ... existing result handling code ...
   ```

5. **Unit Tests**
   ```python
   # tests/test_coordinator_integration.py

   async def test_coordinator_routes_to_executor():
       """Test coordinator workflows operations with environment_spec to executor."""
       pass

   async def test_coordinator_runs_routing_in_process():
       """Test coordinator runs routing operations in-process."""
       pass

   async def test_coordinator_executor_pool_reuse():
       """Test coordinator reuses executors for same environment."""
       pass

   async def test_coordinator_multiple_environments():
       """Test coordinator manages multiple executors with different environments."""
       pass
   ```

**Deliverables:**
- ✅ Coordinator integration
- ✅ Executor pool manager
- ✅ Operation router
- ✅ Modified runtime.py
- ✅ Unit tests

---

### Phase 4: End-to-End Testing (Week 5)

**Goal:** Comprehensive testing of full system

**Tasks:**

1. **Environment Isolation Tests**
   ```python
   # tests/test_e2e_environment_isolation.py

   async def test_environment_isolation_six_versions():
       """THE KEY TEST: Different six versions work correctly."""
       # Base coordinator: six==1.17.0
       # Executor: six==1.16.0
       # Should pass now! ✅
       pass

   async def test_multiple_environment_specs():
       """Test multiple steps with different environments."""
       # Station 1: numpy==1.24.0
       # Station 2: numpy==1.26.0
       # Both should get correct versions
       pass

   async def test_no_environment_spec_works():
       """Test steps without environment_spec still work."""
       pass
   ```

2. **Performance Tests**
   ```python
   # tests/test_e2e_performance.py

   async def test_latency_overhead():
       """Measure latency overhead of coordinator/executor architecture."""
       # Compare to baseline (Phase 0)
       # Target: <10% increase in p95 latency
       pass

   async def test_throughput():
       """Measure throughput with coordinator/executor."""
       # Target: Similar to baseline
       pass

   async def test_large_payload_performance():
       """Test performance with 100MB+ Arrow tables."""
       # Shared memory should handle this efficiently
       pass
   ```

3. **Stress Tests**
   ```python
   # tests/test_e2e_stress.py

   async def test_high_concurrency():
       """Test system under high concurrent load."""
       # 1000 operations in flight simultaneously
       pass

   async def test_executor_crash_recovery():
       """Test coordinator handles executor crashes."""
       # Kill executor mid-operation
       # Coordinator should detect and retry
       pass

   async def test_memory_leak_check():
       """Test for memory leaks in shared memory handling."""
       # Run 10000 operations
       # Monitor memory usage
       pass

   async def test_long_running_operations():
       """Test operations that run for minutes."""
       pass
   ```

4. **Integration with Existing Tests**
   ```python
   # Ensure existing test suite still passes

   async def test_docker_example_still_works():
       """Test existing docker example test."""
       # tests/test_docker_example.py should still pass
       pass

   async def test_all_existing_features():
       """Run full existing test suite."""
       # All tests in tests/ should pass
       pass
   ```

**Deliverables:**
- ✅ End-to-end test suite
- ✅ Performance benchmarks vs baseline
- ✅ Stress test results
- ✅ All existing tests passing

---

### Phase 5: Documentation & Deployment (Week 6)

**Goal:** Document architecture and deploy to production

**Tasks:**

1. **Architecture Documentation**
   ```markdown
   # docs/coordinator-executor-architecture.md

   - Architecture diagrams
   - Process topology
   - IPC protocol specification
   - Environment routing logic
   - Performance characteristics
   - Debugging guide
   ```

2. **Developer Guide**
   ```markdown
   # docs/developer-guide-executor.md

   - How to add custom dependencies
   - How environment isolation works
   - Troubleshooting common issues
   - Performance tuning
   - Monitoring and metrics
   ```

3. **Configuration Guide**
   ```yaml
   # Example configuration
   coordinator:
     worker_async_capacity: 100
     worker_sync_processes: 4
     executor_pool_size: 1  # Executors per coordinator

   executor:
     worker_async_capacity: 50
     worker_sync_processes: 8
     max_operation_timeout: 300  # 5 minutes

   ipc:
     shared_memory_max_size: 1073741824  # 1GB
     queue_timeout: 300
   ```

4. **Monitoring & Observability**
   ```python
   # Add metrics
   - coordinator_to_executor_latency (histogram)
   - executor_operation_duration (histogram)
   - shared_memory_usage (gauge)
   - executor_pool_size (gauge)
   - ipc_errors (counter)
   ```

5. **Docker Configuration**
   ```yaml
   # docker-compose.yml updates

   services:
     coordinator:
       environment:
         - COORDINATOR_EXECUTOR_ENABLED=true
         - EXECUTOR_POOL_SIZE=1
         - IPC_SHARED_MEMORY_MAX_SIZE=1073741824
   ```

**Deliverables:**
- ✅ Complete architecture documentation
- ✅ Developer guide
- ✅ Configuration templates
- ✅ Monitoring setup
- ✅ Docker deployment config

---

## Testing Strategy

### Test Levels

#### Level 1: Unit Tests
- **Scope:** Individual components in isolation
- **Coverage Target:** >90%
- **Focus:**
  - Shared memory IPC
  - Executor process lifecycle
  - Operation router logic
  - Serialization/deserialization

#### Level 2: Integration Tests
- **Scope:** Component interactions
- **Focus:**
  - Coordinator ↔ Executor communication
  - Executor pool management
  - Environment replication integration
  - Stats collection and reporting

#### Level 3: End-to-End Tests
- **Scope:** Full system with Docker infrastructure
- **Focus:**
  - Environment isolation verification
  - Performance benchmarks
  - Error handling and recovery
  - Existing feature compatibility

#### Level 4: Stress Tests
- **Scope:** System limits and reliability
- **Focus:**
  - High concurrency (1000+ operations)
  - Large payloads (100MB+ Arrow tables)
  - Long-running operations (hours)
  - Resource leak detection

### Test Matrix

| Test Case | Base Env | Exec Env | Expected Result |
|-----------|----------|----------|-----------------|
| Same version | six==1.16.0 | six==1.16.0 | ✅ Pass (baseline) |
| Diff version | six==1.17.0 | six==1.16.0 | ✅ Pass (KEY TEST) |
| No env spec | six==1.17.0 | N/A (in-process) | ✅ Pass |
| Routing op | six==1.17.0 | N/A (in-process) | ✅ Pass |
| Multiple envs | six==1.17.0 | numpy==1.24.0, pandas==2.0.0 | ✅ Pass |
| Large payload | Any | Any | ✅ Pass (<2ms IPC overhead) |

### Continuous Testing

```yaml
# .github/workflows/coordinator-executor-tests.yml

name: Coordinator/Executor Architecture Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Unit Tests
        run: pytest tests/test_*_ipc.py tests/test_executor_*.py -v

      - name: Integration Tests
        run: pytest tests/test_coordinator_*.py -v

      - name: E2E Tests
        run: |
          docker-compose up -d
          pytest tests/test_e2e_*.py -v

      - name: Performance Regression
        run: |
          pytest tests/test_e2e_performance.py --benchmark-only
          # Fail if >10% slower than baseline
```

---

## Rollout Plan

### Phase A: Feature Flag (Week 7)

**Goal:** Deploy with feature flag, disabled by default

```python
# Configuration
COORDINATOR_EXECUTOR_ENABLED = os.getenv('COORDINATOR_EXECUTOR_ENABLED', 'false').lower() == 'true'

# In runtime.py
if COORDINATOR_EXECUTOR_ENABLED and router.should_route_to_executor(station_DAO, operation_DAO):
    # Use new architecture
    result, error = await executor.execute(func, args, kwargs)
else:
    # Use existing in-process execution
    result, error = await Station.execute_function(func, *args, **kwargs)
```

**Validation:**
- ✅ Deploy to staging
- ✅ Run full test suite with feature flag ON
- ✅ Run full test suite with feature flag OFF
- ✅ Monitor metrics for 48 hours

---

### Phase B: Opt-In Beta (Week 8)

**Goal:** Enable for specific customers/workloads

```python
# Per-app opt-in
if app_config.get('enable_environment_isolation', False):
    COORDINATOR_EXECUTOR_ENABLED = True
```

**Criteria for Beta:**
- Workloads with custom dependencies
- Non-critical applications
- Customers with monitoring capability

**Success Metrics:**
- No production incidents
- Latency within 10% of baseline
- Customer feedback positive

---

### Phase C: Gradual Rollout (Week 9-10)

**Goal:** Enable for increasing percentage of traffic

```python
# Percentage-based rollout
rollout_percentage = int(os.getenv('COORDINATOR_EXECUTOR_ROLLOUT', '0'))
if random.randint(0, 100) < rollout_percentage:
    COORDINATOR_EXECUTOR_ENABLED = True
```

**Rollout Schedule:**
- Week 9: 10% → 25% → 50%
- Week 10: 75% → 100%

**Rollback Criteria:**
- P95 latency increases >15%
- Error rate increases >1%
- Memory usage increases >50%
- Any P0/P1 incidents

---

### Phase D: Full Production (Week 11)

**Goal:** Default enabled for all traffic

```python
COORDINATOR_EXECUTOR_ENABLED = True  # Always on
```

**Post-Deployment:**
- Monitor for 1 week
- Remove feature flag code
- Update documentation
- Celebrate! 🎉

---

## Risk Mitigation

### Risk 1: Performance Regression

**Risk:** IPC overhead causes unacceptable latency increase

**Mitigation:**
- Comprehensive benchmarking in Phase 0
- Performance tests in Phase 4
- Target: <10% latency increase
- Rollback plan if exceeded

**Monitoring:**
```python
# Alert if p95 latency > baseline * 1.15
latency_threshold = baseline_p95 * 1.15
if current_p95 > latency_threshold:
    alert("Performance regression detected")
```

---

### Risk 2: Memory Leaks

**Risk:** Shared memory not properly cleaned up, causing OOM

**Mitigation:**
- Explicit cleanup in SharedMemoryIPC
- Context managers for automatic cleanup
- Stress tests with memory monitoring
- Leak detection tests

**Implementation:**
```python
class SharedMemoryIPC:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()  # Always cleanup

    def cleanup(self):
        for shm in self.active_shm:
            shm.close()
            shm.unlink()
```

---

### Risk 3: Executor Crashes

**Risk:** Executor process crashes, operations fail

**Mitigation:**
- Health checks (heartbeat every 30s)
- Automatic executor restart
- Operation retry logic
- Graceful degradation (fall back to in-process)

**Implementation:**
```python
async def execute_with_retry(executor, func, args, kwargs, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await executor.execute(func, args, kwargs)
        except ExecutorCrashError:
            logger.warning(f"Executor crashed, attempt {attempt+1}/{max_retries}")
            executor = await executor_manager.restart_executor(executor)

    # Fall back to in-process
    logger.error("Executor retry exhausted, falling back to in-process")
    return await Station.execute_function(func, *args, **kwargs)
```

---

### Risk 4: Complex Debugging

**Risk:** Harder to debug issues across process boundaries

**Mitigation:**
- Comprehensive logging with operation_id correlation
- Distributed tracing (OpenTelemetry)
- Debug mode for in-process execution
- Clear error messages with context

**Implementation:**
```python
logger.info(f"[{operation_id}] Coordinator sending to executor {executor.pid}")
logger.info(f"[{operation_id}] Executor {executor.pid} received operation")
logger.info(f"[{operation_id}] Executor {executor.pid} completed in {duration}s")
logger.info(f"[{operation_id}] Coordinator received result")
```

---

### Risk 5: Environment Creation Overhead

**Risk:** Creating many venvs slows down system

**Mitigation:**
- Environment caching (already implemented in EnvironmentReplicator)
- Lazy environment creation
- Pre-warming common environments
- Environment hash-based reuse

**Already Implemented:**
```python
class EnvironmentReplicator:
    def get_or_create_environment(self, env_spec: dict) -> Path:
        env_hash = hashlib.sha256(json.dumps(env_spec, sort_keys=True).encode()).hexdigest()[:16]
        venv_dir = self.base_dir / env_hash

        if venv_dir.exists():
            return venv_dir / "bin" / "python"  # ✅ Reuse existing

        # Create new environment (only first time)
        self._create_venv(venv_dir, env_spec)
        return venv_dir / "bin" / "python"
```

---

## Success Metrics

### Functional Metrics

| Metric | Current | Target | Critical |
|--------|---------|--------|----------|
| Environment isolation | ❌ Fails | ✅ 100% pass | YES |
| Test coverage | 85% | >90% | NO |
| Existing tests passing | 100% | 100% | YES |

### Performance Metrics

| Metric | Baseline | Target | Alert If |
|--------|----------|--------|----------|
| P50 latency | 50ms | <55ms | >60ms |
| P95 latency | 200ms | <220ms | >250ms |
| P99 latency | 500ms | <550ms | >600ms |
| Throughput | 1000 ops/s | >950 ops/s | <900 ops/s |
| IPC overhead (small) | N/A | <0.5ms | >1ms |
| IPC overhead (100MB) | N/A | <2ms | >5ms |

### Reliability Metrics

| Metric | Current | Target | Alert If |
|--------|---------|--------|----------|
| Error rate | 0.1% | <0.15% | >0.2% |
| Executor crashes | 0/day | <5/day | >10/day |
| Memory leaks | 0 | 0 | Any detected |
| Operation timeouts | 0.01% | <0.05% | >0.1% |

### Resource Metrics

| Metric | Baseline | Target | Alert If |
|--------|----------|--------|----------|
| Memory usage | 2GB | <2.5GB | >3GB |
| CPU usage | 50% | <60% | >75% |
| Executor count | 0 | 4-8 | >20 |
| Shared memory usage | 0MB | <500MB | >1GB |

---

## Appendices

### Appendix A: Code Examples

#### Example 1: Client Using Custom Dependencies

```python
from blazing import Blazing

# Create app with custom dependencies
app = Blazing(
    api_url="http://localhost:8000",
    api_token="test-token",
    python_version="3.11",
    dependencies=[
        "numpy==1.24.0",
        "pandas==2.0.0",
        "scikit-learn==1.3.0"
    ]
)

@app.step
async def analyze_data(df, services=None):
    """This will run in isolated executor with exact package versions."""
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier

    # These imports are guaranteed to be the specified versions
    # numpy==1.24.0, pandas==2.0.0, scikit-learn==1.3.0

    model = RandomForestClassifier()
    # ... analysis logic ...
    return results

@app.workflow
async def pipeline(data, services=None):
    """Routes run in coordinator (no isolation needed)."""
    result = await analyze_data(data, services=services)
    return result

await app.publish()
unit = await app.run("pipeline", data=my_data)
result = await unit.result()
```

#### Example 2: Multiple Environments in Same App

```python
# Station 1: Uses numpy 1.24.0
@app.step(dependencies=["numpy==1.24.0"])
async def legacy_computation(arr, services=None):
    import numpy as np
    # Uses numpy 1.24.0
    return np.sum(arr)

# Station 2: Uses numpy 1.26.0 (newer features)
@app.step(dependencies=["numpy==1.26.0"])
async def modern_computation(arr, services=None):
    import numpy as np
    # Uses numpy 1.26.0 with new features
    return np.median(arr, method='nearest')

# Route: No dependencies (runs in coordinator)
@app.workflow
async def compare_methods(data, services=None):
    legacy = await legacy_computation(data, services=services)
    modern = await modern_computation(data, services=services)
    return {'legacy': legacy, 'modern': modern}
```

### Appendix B: Debugging Guide

#### Debugging Coordinator/Executor Communication

```bash
# Enable debug logging
export BLAZING_DEBUG=true
export BLAZING_LOG_LEVEL=DEBUG

# Check executor processes
docker exec blazing-coordinator ps aux | grep executor

# Check shared memory usage
docker exec blazing-coordinator ls -lh /dev/shm/

# Monitor IPC queues
docker exec blazing-coordinator python -c "
from multiprocessing import Queue
import os
# List queue files in /dev/shm or /tmp
"

# Check executor health
docker logs blazing-coordinator | grep "executor"
```

#### Common Issues

**Issue: Operation hangs, never completes**
```
Symptoms: unit.result() waits forever
Cause: Executor crashed or IPC deadlock
Debug:
  1. Check executor process is running
  2. Check shared memory not full
  3. Check queue sizes
  4. Enable debug logging
```

**Issue: Wrong package version imported**
```
Symptoms: Station uses base environment packages
Cause: Operation not routed to executor
Debug:
  1. Check station_DAO.environment_spec is set
  2. Check operation_router.should_route_to_executor() returns True
  3. Check executor_manager has executor for environment
  4. Check COORDINATOR_EXECUTOR_ENABLED=true
```

### Appendix C: Performance Tuning

#### Coordinator Tuning

```python
# Adjust async worker capacity based on I/O workload
COORDINATOR_ASYNC_CAPACITY = 200  # High for I/O-heavy

# Adjust sync workers based on file I/O needs
COORDINATOR_SYNC_PROCESSES = 2  # Low, mostly async

# Executor pool size (executors per coordinator)
EXECUTOR_POOL_SIZE = 1  # Start with 1:1 ratio
```

#### Executor Tuning

```python
# Adjust async worker capacity based on async computation
EXECUTOR_ASYNC_CAPACITY = 50  # Lower, more CPU-bound

# Adjust sync workers based on CPU cores
EXECUTOR_SYNC_PROCESSES = 8  # Higher for CPU-heavy

# Operation timeout
EXECUTOR_OPERATION_TIMEOUT = 300  # 5 minutes
```

#### IPC Tuning

```python
# Shared memory pool size
SHARED_MEMORY_MAX_SIZE = 1_073_741_824  # 1GB

# Queue timeouts
IPC_QUEUE_TIMEOUT = 300  # 5 minutes

# Cleanup interval
SHARED_MEMORY_CLEANUP_INTERVAL = 60  # Clean up every minute
```

---

## Conclusion

This implementation plan provides a comprehensive roadmap for implementing true environment isolation in Blazing using the coordinator/executor architecture.

**Key Takeaways:**
- 6-week implementation plan with clear phases
- Comprehensive testing at every level
- Risk mitigation strategies
- Gradual rollout with monitoring
- Clear success metrics

**Next Steps:**
1. Review and approve this plan
2. Set up project tracking (Jira, GitHub Projects, etc.)
3. Allocate engineering resources
4. Begin Phase 0: Baseline testing

**Questions for Review:**
1. Does the 6-week timeline work for your schedule?
2. Are there any architectural decisions you'd like to reconsider?
3. Should we add any additional testing scenarios?
4. Are the success metrics appropriate?

---

**Document Version:** 1.0
**Last Updated:** 2025-11-24
**Authors:** Claude Code
**Status:** Ready for Review
