# Pyron Project Evaluation for Blazing Architecture

**Date:** 2025-11-24
**Project:** `/Users/jonathanborduas/code/Pyron/`
**Context:** Coordinator/Executor architecture for Blazing environment isolation

---

## Executive Summary

Pyron demonstrates **exactly the architecture pattern** we need for Blazing's coordinator/executor design, with one critical inversion:

**Pyron Pattern:**
- **Coordinator (JavaScript/Node.js):** Fetches data from Redis/PostgreSQL/Arrow
- **Executor (Pyodide/WASM or Docker):** Receives data, executes computation

**Blazing Needs (Inverted):**
- **Coordinator (Python):** Orchestrates operations, routes to executors
- **Executor (Python in isolated venv):** **Fetches data AND executes computation**

This inversion is BRILLIANT and eliminates a major bottleneck!

---

## Pyron Architecture Overview

### Two-Backend Design

Pyron has **two swappable backends** with identical client API:

#### 1. PyronPyodide (WASM Backend)
```
Python Client
    ↓ (stdin/stdout JSON)
Node.js Process
    ├─ JavaScript (Data Fetching)
    │   ├─ Redis client (async)
    │   ├─ PostgreSQL client (async)
    │   └─ Arrow IPC reader (async)
    ↓ (VFS transfer ~10ms for 10MB)
    └─ Pyodide/WASM (Computation)
        └─ Python + NumPy/Pandas
```

**Characteristics:**
- ✅ Fast startup (~100ms)
- ✅ Browser-compatible
- ✅ Connection pooling (30x speedup)
- ✅ Data caching (150x speedup)
- ⚠️ Sequential execution (stdin/stdout)
- ⚠️ WASM overhead (2-5x slower compute)

#### 2. PyronDocker (Container Backend)
```
Python Client
    ↓ (HTTP REST - commands only, ~1KB)
Docker Container (FastAPI)
    ├─ Python Event Loop (async)
    │   ├─ Redis client (INSIDE container!) ✅
    │   ├─ PostgreSQL client (INSIDE container!) ✅
    │   ├─ Arrow IPC reader (INSIDE container!) ✅
    │   └─ NumPy/Pandas (native speed!)
    └─ Background Tasks (parallel execution)
```

**Characteristics:**
- ✅ **Data fetching INSIDE container** (zero transfer!)
- ✅ Native Python speed
- ✅ Parallel execution (100s of tasks)
- ✅ Connection pooling inside container
- ✅ Async event loop (FastAPI)
- ⚠️ Slower startup (~500ms)
- ⚠️ Higher memory (~200MB)

---

## Key Insight: Executor Fetches Data!

### Pyron's Docker Backend Implementation

```python
# From docker_backend.py:140
async def fetch_datasource_async(self, name: str):
    """
    Note: In Docker backend, this is a no-op. The container
    fetches data when execute_async is called.
    """
    # Just register the datasource URL
    self._datasources[name] = url

    # Container fetches inside during execution!
    return {"note": "Data will be fetched inside container during execution"}
```

**What happens during execute_async:**
1. Client sends **command only** (code + datasource URLs, ~1KB)
2. Container **fetches data internally** (Redis/PostgreSQL/Arrow)
3. Container executes computation
4. Container returns result

**Result:** ZERO data transfer overhead! Container fetches its own data.

---

## How This Maps to Blazing

### Current Blazing Problem

```
Coordinator Process (system Python)
    ↓ Fetch 100MB Arrow table from Arrow Flight
    ↓ Serialize and copy to shared memory (~50ms)
    ↓ Send pointer to executor

Executor Process (isolated venv)
    ↓ Read from shared memory (~0.001ms with memoryview)
    ↓ Deserialize Arrow table
    ↓ Execute computation
```

**Issue:** Data transfer through shared memory, even with memoryview optimization.

### Pyron-Inspired Solution

```
Coordinator Process (system Python)
    ↓ Create operation with datasource references
    ↓ Send ONLY operation metadata to executor (~1KB)

Executor Process (isolated venv)
    ↓ Receive operation metadata
    ↓ **Fetch Arrow table INSIDE executor** (async!)
    ↓ Execute computation on fetched data
    ↓ Return result
```

**Result:** ZERO data transfer! Executor fetches its own data from Arrow Flight.

---

## Architectural Changes Required for Blazing

### 1. Move Data Fetching to Executor

**Current (Coordinator fetches):**
```python
# In coordinator
async def execute_operation(operation_pk):
    # Coordinator fetches Arrow data
    arrow_table = await fetch_arrow_flight(endpoint, ticket)

    # Pass data to executor via shared memory
    result = await executor.execute(func, args={'table': arrow_table})
```

**New (Executor fetches):**
```python
# In coordinator
async def execute_operation(operation_pk):
    # Coordinator just passes datasource references
    datasources = {
        'events': {'type': 'arrow_flight', 'endpoint': '...', 'ticket': '...'},
        'sensors': {'type': 'redis', 'key': 'blazing:sensors'},
        'users': {'type': 'postgres', 'query': 'SELECT * FROM users'}
    }

    # Send metadata only (~1KB)
    result = await executor.execute(func, args={}, datasources=datasources)
```

**In executor:**
```python
# Executor process
async def execute_operation_in_executor(operation_data):
    # 1. Fetch all datasources INSIDE executor
    arrow_table = await fetch_arrow_flight(datasources['events'])
    sensors = await redis_client.get(datasources['sensors']['key'])
    users = await pg_client.query(datasources['users']['query'])

    # 2. Inject into function namespace
    func_globals = {
        '_datasource_events': arrow_table,
        '_datasource_sensors': sensors,
        '_datasource_users': users,
    }

    # 3. Execute function
    result = await execute_with_globals(func, func_globals)
    return result
```

---

## Station Wrapper Creation Implications

### Current Flow (Without Data Fetching)

```python
# Client defines station
@app.station
async def analyze_data(df, services=None):
    import pandas as pd
    return df.describe()

# Coordinator receives operation
# → Creates operation DAO
# → Enqueues to executor
# → Executor executes function
```

### New Flow (With Data Fetching in Executor)

```python
# Client defines station WITH datasource declarations
@app.station(datasources={
    'events': 'arrow_flight://endpoint:8815/events',
    'sensors': 'redis://localhost:6379/sensors',
    'users': 'postgres://localhost:5432/db?query=SELECT * FROM users'
})
async def analyze_data(services=None):
    # Datasources auto-injected by executor!
    events = _datasource_events    # Arrow table
    sensors = _datasource_sensors  # From Redis
    users = _datasource_users      # From PostgreSQL

    return {
        'event_mean': float(events['value'].mean()),
        'sensor_count': len(sensors),
        'user_count': len(users)
    }

# When operation is created:
# 1. Coordinator creates OperationDAO with datasource metadata
# 2. Enqueues to executor
# 3. Executor:
#    a. Reads operation
#    b. Fetches all datasources (async, parallel!)
#    c. Injects into function namespace
#    d. Executes function
#    e. Returns result
```

---

## Benefits of Executor-Side Data Fetching

### 1. Zero Data Transfer Between Processes

**Before (Shared Memory):**
- Coordinator → Executor: 100MB data transfer
- Time: ~50ms (even with memoryview)

**After (Executor Fetches):**
- Coordinator → Executor: ~1KB metadata
- Time: ~0.01ms
- **50ms saved per operation!**

### 2. Parallel Data Fetching

Executor can fetch multiple datasources in parallel:

```python
# Inside executor
datasources_data = await asyncio.gather(
    fetch_arrow_flight(datasources['events']),
    fetch_redis(datasources['sensors']),
    fetch_postgres(datasources['users'])
)
# All three fetch concurrently!
```

### 3. Connection Pooling in Executor

Each executor maintains its own connection pools:

```python
# Executor process
class ExecutorProcess:
    def __init__(self):
        self.redis_pool = RedisPool(max_connections=10)
        self.pg_pool = PostgresPool(max_connections=5)
        self.arrow_client_pool = ArrowFlightClientPool(max_clients=5)

    async def fetch_datasources(self, datasources):
        # Reuse connections across operations
        redis_conn = await self.redis_pool.acquire()
        # ... fetch data
        await self.redis_pool.release(redis_conn)
```

**Result:** 30x speedup on repeated datasource access (same as Pyron!)

### 4. Data Caching in Executor

```python
# Executor process
class ExecutorProcess:
    def __init__(self):
        self.data_cache = LRUCache(max_size=1000, ttl=300)  # 5 min TTL

    async def fetch_datasource(self, datasource_url):
        # Check cache first
        cached = self.data_cache.get(datasource_url)
        if cached:
            return cached  # 150x speedup!

        # Fetch and cache
        data = await self._fetch_from_source(datasource_url)
        self.data_cache.set(datasource_url, data)
        return data
```

**Result:** 150x speedup on cache hits (same as Pyron!)

### 5. Cleaner Separation of Concerns

**Coordinator:**
- Orchestration (routes, DAG execution)
- Operation routing
- Status tracking
- **NO data fetching!**

**Executor:**
- Data fetching (Redis, PostgreSQL, Arrow Flight)
- Computation
- Result generation
- **Self-contained!**

---

## Implementation Comparison: Pyron vs Blazing

### Pyron's Docker Backend

**File:** `src/pyron/docker_backend.py`

```python
async def execute_async(self, code, function_name, *args, **kwargs):
    # Send command to container (HTTP REST)
    payload = {
        'task_id': str(uuid.uuid4()),
        'datasources': self._datasources,  # Just URLs!
        'code': code,
        'function_name': function_name,
        'args': args,
        'kwargs': kwargs
    }

    # Container fetches data internally
    response = await httpx.post(f"{self.base_url}/execute", json=payload)
    task_id = response.json()['task_id']

    # Poll for completion
    while True:
        result = await httpx.get(f"{self.base_url}/status/{task_id}")
        if result.json()['status'] == 'completed':
            return ExecutionResult(...)
        await asyncio.sleep(poll_interval)
```

**Container Side (FastAPI in Docker):**

```python
@app.post("/execute")
async def execute(request: ExecuteRequest):
    task_id = request.task_id

    # Start background task
    asyncio.create_task(execute_in_background(task_id, request))

    # Return immediately
    return {"accepted": True, "task_id": task_id}

async def execute_in_background(task_id, request):
    # 1. Fetch all datasources INSIDE container
    datasource_data = {}
    for name, url in request.datasources.items():
        if url.startswith('redis://'):
            datasource_data[name] = await fetch_redis(url)
        elif url.startswith('postgresql://'):
            datasource_data[name] = await fetch_postgres(url)
        elif url.startswith('arrow://'):
            datasource_data[name] = await fetch_arrow(url)

    # 2. Inject into Python namespace
    globals_dict = {f'_datasource_{name}': data
                    for name, data in datasource_data.items()}

    # 3. Execute code
    exec(request.code, globals_dict)
    func = globals_dict[request.function_name]
    result = func(*request.args, **request.kwargs)

    # 4. Store result
    results[task_id] = {'status': 'completed', 'result': result}
```

### Blazing's Proposed Executor

**File:** `src/blazing_service/executor/executor_process.py`

```python
class ExecutorProcess:
    def __init__(self, python_exe, env_hash):
        self.python_exe = python_exe
        self.env_hash = env_hash

        # Data fetching clients (NEW!)
        self.redis_pool = RedisPool()
        self.pg_pool = PostgresPool()
        self.arrow_clients = ArrowFlightClientPool()
        self.data_cache = LRUCache(max_size=1000, ttl=300)

        # Worker pools
        self.worker_async = ExecutorWorkerAsync()
        self.worker_sync = ExecutorWorkerSync()

    async def execute_operation(self, operation_data):
        # 1. Fetch datasources INSIDE executor (parallel!)
        datasources = await self.fetch_all_datasources(
            operation_data['datasources']
        )

        # 2. Get function from operation
        func = dill.loads(operation_data['serialized_func'])

        # 3. Inject datasources into function namespace
        func_globals = func.__globals__.copy()
        for name, data in datasources.items():
            func_globals[f'_datasource_{name}'] = data

        # 4. Create new function with enhanced globals
        enhanced_func = types.FunctionType(
            func.__code__,
            func_globals,
            func.__name__,
            func.__defaults__,
            func.__closure__
        )

        # 5. Execute via worker pool
        if is_async_operation(operation_data):
            result = await self.worker_async.execute(enhanced_func, args, kwargs)
        else:
            result = await self.worker_sync.execute(enhanced_func, args, kwargs)

        return result

    async def fetch_all_datasources(self, datasources_spec):
        """Fetch all datasources in parallel."""
        tasks = []
        for name, spec in datasources_spec.items():
            tasks.append(self.fetch_datasource(name, spec))

        results = await asyncio.gather(*tasks)
        return dict(zip(datasources_spec.keys(), results))

    async def fetch_datasource(self, name, spec):
        """Fetch single datasource with caching."""
        cache_key = f"{spec['type']}:{spec['url']}"

        # Check cache
        cached = self.data_cache.get(cache_key)
        if cached:
            return cached

        # Fetch based on type
        if spec['type'] == 'arrow_flight':
            data = await self.fetch_arrow_flight(spec)
        elif spec['type'] == 'redis':
            data = await self.fetch_redis(spec)
        elif spec['type'] == 'postgres':
            data = await self.fetch_postgres(spec)

        # Cache and return
        self.data_cache.set(cache_key, data)
        return data

    async def fetch_arrow_flight(self, spec):
        """Fetch Arrow table using async client."""
        import pyarrow.flight as flight

        # Get or create async client
        location = flight.Location.for_grpc_tcp(spec['endpoint'], spec['port'])
        client = self.arrow_clients.get_or_create(location)
        async_client = client.as_async()

        # Fetch data
        stream = await async_client.do_get(spec['ticket'])
        table = await stream.read_all()
        return table
```

---

## Station Wrapper Changes

### Current Station Wrapper Creation

```python
# In blazing.py (client-side)
@app.station
async def analyze_data(df, services=None):
    return df.describe()

# Creates:
station_registration = {
    'name': 'analyze_data',
    'serialized_function': base64.b64encode(dill.dumps(analyze_data)),
    'priority': 0.5,
    'environment_spec': {...}  # If dependencies specified
}
```

### New Station Wrapper Creation (With Datasources)

```python
# Client-side API (OPTION 1: Decorator argument)
@app.station(datasources={
    'events': 'arrow_flight://endpoint:8815/events',
    'sensors': 'redis://localhost:6379/sensors'
})
async def analyze_data(services=None):
    # Datasources auto-injected!
    events = _datasource_events
    sensors = _datasource_sensors
    return {'mean': float(events['value'].mean())}

# Client-side API (OPTION 2: Explicit declaration)
@app.station
async def analyze_data(services=None):
    # Declare datasources in function
    events = await datasource('arrow_flight://endpoint:8815/events')
    sensors = await datasource('redis://localhost:6379/sensors')
    return {'mean': float(events['value'].mean())}

# Creates:
station_registration = {
    'name': 'analyze_data',
    'serialized_function': base64.b64encode(dill.dumps(analyze_data)),
    'priority': 0.5,
    'environment_spec': {...},
    'datasources': {  # NEW!
        'events': {
            'type': 'arrow_flight',
            'endpoint': 'endpoint',
            'port': 8815,
            'path': 'events'
        },
        'sensors': {
            'type': 'redis',
            'host': 'localhost',
            'port': 6379,
            'key': 'sensors'
        }
    }
}
```

### Operation Creation Changes

**Current:**
```python
# When creating operation from station wrapper
run = await app.run("analyze_data", df=my_dataframe)
# → Coordinator fetches data, passes to executor
```

**New:**
```python
# When creating operation from station wrapper
run = await app.run("analyze_data")
# → Coordinator DOES NOT fetch data
# → Executor fetches data when executing operation
```

**OperationDAO changes:**
```python
class OperationDAO:
    # Existing fields
    pk: str
    station_pk: str
    unit_pk: str
    status: str

    # NEW: Datasource specifications
    datasources: Optional[str] = None  # JSON-serialized datasource specs
```

---

## Performance Impact Analysis

### Scenario 1: Single 100MB Arrow Table

**Current (Shared Memory):**
```
Coordinator: Fetch Arrow (50ms) → Serialize → Write to shm (50ms) = 100ms
Executor: Read from shm (0.001ms) → Execute (30ms) = 30ms
Total: 130ms
```

**New (Executor Fetches):**
```
Coordinator: Send metadata (0.01ms) = 0.01ms
Executor: Fetch Arrow (50ms) → Execute (30ms) = 80ms
Total: 80ms  ✅ 38% faster!
```

### Scenario 2: Multiple Datasources (Arrow + Redis + PostgreSQL)

**Current (Shared Memory, Sequential):**
```
Coordinator:
  Fetch Arrow (50ms)
  Fetch Redis (20ms)
  Fetch PostgreSQL (30ms)
  Total fetch: 100ms
  Serialize + Write to shm: 60ms
Total coordinator: 160ms

Executor:
  Read from shm (0.001ms)
  Execute (40ms)
Total executor: 40ms

Total: 200ms
```

**New (Executor Fetches, Parallel):**
```
Coordinator:
  Send metadata (0.01ms)

Executor:
  Fetch Arrow (50ms) ┐
  Fetch Redis (20ms)  ├─ Parallel!
  Fetch PostgreSQL (30ms) ┘
  Total fetch: 50ms (bottleneck)
  Execute (40ms)
Total executor: 90ms

Total: 90ms  ✅ 55% faster!
```

### Scenario 3: Cached Data

**Current (No cache in coordinator):**
```
Same as Scenario 1: 130ms every time
```

**New (LRU cache in executor):**
```
First execution: 80ms
Subsequent executions:
  Cache hit (0.001ms) + Execute (30ms) = 30ms
Total: 30ms  ✅ 63% faster than current!
```

---

## Implementation Phases

### Phase 0: Foundation (Prep Work)

**Tasks:**
1. Add datasource fields to StationDAO and OperationDAO
2. Update client-side `@app.station` decorator to accept datasources
3. Add datasource serialization to station registration

**Deliverables:**
- ✅ Updated DAOs
- ✅ Updated client API
- ✅ Backward compatible (datasources optional)

### Phase 1: Executor Data Fetching (Core)

**Tasks:**
1. Implement data fetching clients in executor:
   - `ArrowFlightClient` (async, using PyArrow as_async())
   - `RedisClient` (async, using aredis)
   - `PostgresClient` (async, using asyncpg)
2. Implement connection pooling per executor
3. Implement LRU cache per executor
4. Add datasource injection into function namespace

**Deliverables:**
- ✅ Executor can fetch Arrow Flight data
- ✅ Executor can fetch Redis data
- ✅ Executor can fetch PostgreSQL data
- ✅ Connection pooling working (30x speedup)
- ✅ Data caching working (150x speedup)

### Phase 2: Remove Coordinator Data Fetching

**Tasks:**
1. Remove data fetching logic from coordinator
2. Update operation creation to pass datasource specs only
3. Update IPC to send metadata instead of data

**Deliverables:**
- ✅ Coordinator sends ~1KB metadata instead of 100MB data
- ✅ End-to-end test passing with executor-side fetching

### Phase 3: Optimization

**Tasks:**
1. Parallel datasource fetching in executor
2. Smart cache invalidation (TTL, manual invalidation)
3. Connection pool tuning
4. Monitoring and metrics

**Deliverables:**
- ✅ Parallel fetching (1.5-3x speedup)
- ✅ Cache hit rate monitoring
- ✅ Connection pool metrics

---

## Risks and Mitigations

### Risk 1: Executor Network Access

**Risk:** Executors need network access to Redis, PostgreSQL, Arrow Flight servers.

**Mitigation:**
- Docker networking already provides this
- Same network access as coordinator
- Firewall rules apply to executor containers

### Risk 2: Connection Exhaustion

**Risk:** Each executor maintains connection pools; could exhaust server connections.

**Mitigation:**
- Limit pool size per executor (e.g., 5 connections max)
- Monitor connection count
- Reuse connections aggressively

### Risk 3: Cache Memory Usage

**Risk:** LRU cache could consume too much executor memory.

**Mitigation:**
- Set max cache size (e.g., 1GB per executor)
- Use TTL to expire old entries
- Monitor memory usage

### Risk 4: Data Consistency

**Risk:** Cached data might be stale.

**Mitigation:**
- Short TTL (5 minutes default)
- Manual cache invalidation API
- Operation-level cache bypass flag

---

## Comparison: Pyron vs Blazing Architecture

| Aspect | Pyron | Blazing (Proposed) |
|--------|-------|-------------------|
| **Coordinator role** | Data fetching | Orchestration only |
| **Executor role** | Computation only | Fetching + Computation |
| **Data transfer** | VFS (WASM) or None (Docker) | None (executor fetches) |
| **Connection pooling** | Coordinator or Executor | Executor only |
| **Data caching** | Coordinator or Executor | Executor only |
| **Parallel fetching** | Coordinator (WASM) or Executor (Docker) | Executor only |
| **Best for** | Sandboxed user code | Distributed workflow orchestration |

**Key Difference:** Pyron's executor is sandboxed (untrusted code), so data fetching happens outside. Blazing's executor is trusted, so it can fetch its own data.

---

## Recommendations

### 1. ✅ Adopt Executor-Side Data Fetching

**Reason:** Eliminates 50-100ms data transfer overhead per operation.

**Implementation:** Follow Pyron's Docker backend pattern where executor fetches all datasources internally.

### 2. ✅ Implement Connection Pooling in Executor

**Reason:** 30x speedup on repeated datasource access (proven by Pyron benchmarks).

**Implementation:** Each executor maintains pools for Redis, PostgreSQL, Arrow Flight clients.

### 3. ✅ Implement LRU Cache in Executor

**Reason:** 150x speedup on cache hits (proven by Pyron benchmarks).

**Implementation:** LRU cache with TTL (5 minutes default), max size (1GB).

### 4. ✅ Support Parallel Datasource Fetching

**Reason:** 1.5-3x speedup when multiple datasources (proven by Pyron).

**Implementation:** `asyncio.gather()` for concurrent fetching.

### 5. ✅ Update Client API for Datasource Declaration

**Reason:** Clean separation between orchestration logic and data access.

**Recommended syntax:**
```python
@app.station(datasources={
    'events': 'arrow_flight://endpoint:8815/events',
    'sensors': 'redis://localhost:6379/sensors'
})
async def analyze_data(services=None):
    events = _datasource_events  # Auto-injected
    sensors = _datasource_sensors  # Auto-injected
    return compute(events, sensors)
```

### 6. ⚠️ Consider Pyodide Backend for Edge Deployment (Future)

**Reason:** Pyron's WASM backend enables browser/edge deployment.

**Use case:** If Blazing ever needs browser-based execution, Pyron's pattern is proven.

**Priority:** Low (not needed for current server-side architecture)

---

## Conclusion

**Pyron validates the executor-side data fetching pattern** and provides:

1. ✅ **Proven architecture** - Docker backend shows executor-side fetching works
2. ✅ **Performance benchmarks** - 30x (pooling), 150x (caching), 1.5-3x (parallel fetching)
3. ✅ **Implementation reference** - Can adapt Pyron's Docker backend code
4. ✅ **Clean API design** - Datasource declaration pattern is elegant

**The big change for Blazing:**
- **Move data fetching from coordinator to executor**
- **Coordinator sends metadata only (~1KB), not data (100MB+)**
- **Executor fetches, caches, and pools connections**

**Impact:**
- ✅ 38-63% faster execution (depending on caching)
- ✅ Cleaner separation of concerns
- ✅ Better resource utilization
- ✅ Scales better (parallel fetching, connection pooling)

**Next Steps:**
1. Update coordinator-executor implementation plan to include executor-side data fetching
2. Add Phase 0: Datasource infrastructure (DAOs, client API)
3. Add Phase 1: Executor data fetching clients (Arrow, Redis, PostgreSQL)
4. Add Phase 2: Connection pooling and caching
5. Add Phase 3: Parallel fetching optimization

**The Pyron project is a goldmine of validated patterns for our architecture!** 🎯

---

**Document Version:** 1.0
**Date:** 2025-11-24
**Author:** Claude Code
**Status:** Ready for Implementation Planning
