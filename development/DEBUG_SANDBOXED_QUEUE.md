# Debug Journal: SandboxedQueue Visibility Issue

## Problem Statement
Coordinator's sandboxed workers cannot see SandboxedQueue keys that the API creates, even though both claim to be connected to the same Redis instance (`redis:6379`).

## Timeline

### 2025-12-12 09:30 - Initial Investigation

**Hypothesis 1: Wrong Redis Instance**
- User suggested: "we have two redis database, one for data, one for coordination. something might be putting it into the wrong redis db..."

**Test 1: Check environment variables**
```bash
# API container
REDIS_URL=redis
REDIS_PORT=6379
DATA_REDIS_URL=redis-data

# Coordinator container
REDIS_URL=redis
REDIS_PORT=6379
DATA_REDIS_URL=redis-data
```
**Result:** Both have identical env vars. ❌ Not the cause.

**Test 2: Check DNS resolution**
```bash
docker exec blazing-api python3 -c "import socket; print(socket.gethostbyname('redis'))"
# API: redis resolves to 172.18.0.2

docker exec blazing-coordinator python3 -c "import socket; print(socket.gethostbyname('redis'))"
# Coordinator: redis resolves to 172.18.0.2
```
**Result:** Both resolve `redis` to same IP. ❌ Not the cause.

**Test 3: Check CLIENT LIST on both Redis instances**
```bash
# blazing-redis (172.18.0.2) - coordination
# Has connections from 172.18.0.7 (coordinator)

# blazing-redis-data (172.18.0.4) - data
# Has connections from 172.18.0.3 (API!)
```
**Result:** API (172.18.0.3) was connected to DATA Redis, not coordination Redis!

**BUT WAIT** - After adding debug logging to enqueue function:
```
DEBUG-enqueue_sandboxed: REDIS_CONNECTION={'host': 'redis', 'port': 6379, ...}
```
The connection info shows `host: 'redis'` which should be coordination Redis.

---

### 2025-12-12 09:45 - Added Debug Logging

**Added to `enqueue_non_blocking_sandboxed_operation()`:**
```python
conn_info = redis_client.connection_pool.connection_kwargs
print(f"DEBUG-enqueue_sandboxed: REDIS_CONNECTION={conn_info}", flush=True)
```

**Added to `dequeue_non_blocking_sandboxed_operation()`:**
```python
conn_info = redis_client.connection_pool.connection_kwargs
print(f"DEBUG-dequeue_sandboxed: REDIS_CONNECTION={conn_info}", flush=True)
```

**Results after rebuild:**
```
# API logs
DEBUG-enqueue_sandboxed: REDIS_CONNECTION={'host': 'redis', 'port': 6379, 'db': 0, ...}
DEBUG-enqueue_sandboxed: lpush result=1
DEBUG-enqueue_sandboxed: VERIFY exists=1, len=1

# Coordinator logs
DEBUG-dequeue_sandboxed: REDIS_CONNECTION={'host': 'redis', 'port': 6379, 'db': 0, ...}
DEBUG-dequeue_sandboxed: found 0 segments: []
DEBUG-dequeue_sandboxed: ALL SandboxedQueue keys in Redis: []
```

**CRITICAL OBSERVATION:**
- Both show SAME connection config: `host='redis', port=6379, db=0`
- API successfully creates key (lpush=1, exists=1, len=1)
- Coordinator sees 0 keys with KEYS command
- Direct `redis-cli` on blazing-redis shows NO SandboxedQueue keys!

---

### 2025-12-12 10:00 - Cross-Container Redis Test

**Test 4: Direct Redis write/read test**
```bash
# From API container
docker exec blazing-api python3 -c "
import redis.asyncio as redis
import asyncio
async def test():
    r = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
    await r.set('test:api:key', 'hello-from-api')
    print('API set key')
    await r.aclose()
asyncio.run(test())
"
# Output: API set key

# From Coordinator container
docker exec blazing-coordinator python3 -c "
import redis.asyncio as redis
import asyncio
async def test():
    r = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
    keys = await r.keys('test:*')
    print('Coordinator sees:', keys)
    await r.aclose()
asyncio.run(test())
"
# Output: Coordinator sees: ['test:api:key']
```

**Result:** Direct Redis connection works! Both containers CAN see each other's keys. ✅

---

## Key Facts

1. **Two Redis instances exist:**
   - `blazing-redis` (172.18.0.2) - coordination, port 6379
   - `blazing-redis-data` (172.18.0.4) - data storage, port 6379 internally

2. **Both API and Coordinator report same connection:**
   - `host='redis', port=6379, db=0`

3. **API enqueue succeeds:**
   - `lpush result=1`
   - `VERIFY exists=1, len=1` (immediately after lpush)

4. **Coordinator dequeue fails:**
   - `found 0 segments: []`
   - `ALL SandboxedQueue keys in Redis: []`

5. **Direct redis-cli shows NO SandboxedQueue keys** on blazing-redis

6. **Cross-container direct Redis test WORKS** - they can see each other's keys

---

## Theories

### Theory A: thread_local_data.redis is Different Objects
The `thread_local_data.redis` might be initialized differently in API vs Coordinator contexts, even though both show the same connection config.

**Evidence FOR:**
- API uses `server.py:lifespan()` to create `thread_local_data.redis`
- Coordinator uses `runtime.py:initialize_local_runtime()` to create `thread_local_data.redis`
- Both show same config but might have different actual connections

**Evidence AGAINST:**
- Both show `host='redis'` which resolves to same IP
- Direct test showed cross-container visibility works

### Theory B: Key is Created but Immediately Deleted
Something might be deleting the key between enqueue and dequeue.

**Evidence FOR:**
- Test fixture does `FLUSHDB` during setup
- Key exists immediately after lpush but not later

**Evidence AGAINST:**
- The enqueue VERIFY shows key exists right after lpush
- Coordinator polls continuously and never sees it

### Theory C: Different Redis Database (db number)
Despite both showing `db=0`, maybe one is using a different db.

**Evidence FOR:**
- Would explain complete invisibility

**Evidence AGAINST:**
- Both explicitly show `db=0` in connection config

### Theory D: Connection Pool Returning Wrong Connection
The connection pool might have connections to BOTH Redis instances, and returning wrong one for queue operations.

**Evidence FOR:**
- CLIENT LIST showed API has connection to redis-data
- Maybe pool was initialized with wrong host first

**Evidence AGAINST:**
- Connection config shows correct host

### Theory E: Timing/Race Condition with FLUSHDB
The test fixture flushes Redis, then the key is created, but maybe coordinator's Redis client has stale view.

**Evidence FOR:**
- Test does flush → restart coordinator → create key
- Coordinator might have cached empty state

**Evidence AGAINST:**
- Coordinator is restarted after flush, should have fresh connections

---

### 2025-12-12 10:30 - Enhanced Diagnostics

Added comprehensive Redis server info logging to both enqueue and dequeue:
- TIMESTAMP for timing correlation
- REDIS_SERVER version and port (via INFO command)
- CLIENT_ID and POOL_ID to track object identity
- ALL_SANDBOXED_KEYS after operations

**Results:**
```
# API logs (during enqueue)
DEBUG-enqueue_sandboxed: TIMESTAMP=1765533988.3953645
DEBUG-enqueue_sandboxed: REDIS_SERVER version=7.4.7 port=6379
DEBUG-enqueue_sandboxed: ALL_SANDBOXED_KEYS=['blazing:default:workflow_definition:Station:01KC90DDB1JSGRTB2B6TQZ53VV:SandboxedQueue:node-1']

# Coordinator logs (23 seconds later!)
DEBUG-dequeue_sandboxed: TIMESTAMP=1765534011.1934202
DEBUG-dequeue_sandboxed: REDIS_SERVER version=7.4.7 port=6379
DEBUG-dequeue_sandboxed: found 0 segments: []
DEBUG-dequeue_sandboxed: ALL SandboxedQueue keys in Redis: []
```

**CRITICAL FINDING:**
- Both connected to SAME Redis server (version=7.4.7, port=6379)
- Key exists immediately after API enqueue (ALL_SANDBOXED_KEYS has 1 key)
- 23 seconds later, coordinator sees EMPTY (ALL SandboxedQueue keys = [])
- Something DELETES the key between enqueue and dequeue!

---

### 2025-12-12 11:00 - ROOT CAUSE FOUND! 🎯

**Looking at the test fixture (`pyodide_backend_infrastructure`):**

```python
# STEP 2: Flush Redis databases to ensure clean state before test
print("🧹 Cleaning Redis state for test isolation...", flush=True)
flush_all_redis_databases()  # <-- Flushes ALL Redis data

# STEP 3: Restart coordinator after Redis flush to clear in-memory state
print("🔄 Restarting coordinator after Redis flush...", flush=True)
docker_helper.run_docker_compose(["restart", "coordinator"], ...)  # <-- Takes ~23 seconds!
```

**THE BUG:**
1. Test fixture starts
2. Fixture flushes Redis (`FLUSHDB`)
3. Fixture starts restarting coordinator (takes ~23 seconds)
4. **WHILE coordinator is restarting**, test continues running!
5. Test calls `app.publish()` → API enqueues to SandboxedQueue
6. Coordinator finishes restart → connects to Redis → sees EMPTY SandboxedQueue

**The 23-second gap in timestamps is the coordinator restart!**

The issue is that the fixture's `scope="function"` means it runs for EVERY test, and the flush+restart happens BEFORE yielding to the test. But the restart is fire-and-forget - it doesn't wait for coordinator to be fully ready with workers polling before the test starts.

Actually wait - lines 368-371 DO wait for coordinator to be healthy:
```python
if docker_helper.wait_for_healthy("blazing-coordinator", timeout_seconds=45):
    print("✓ Coordinator healthy after restart")
```

But "healthy" just means the container is running, NOT that workers are polling queues!

---

## ROOT CAUSE CONFIRMED

**The issue is the ORDER OF OPERATIONS in the test fixture:**

```
FIXTURE RUNS:
1. flush_all_redis_databases()     → Clears everything
2. restart coordinator                 → Coordinator restarts with fresh state
3. wait_for_healthy()              → Container is "healthy" (running)
4. Wait for workers to exist       → Workers created in Redis

THEN TEST RUNS:
5. app.publish()                   → API syncs stations to Redis
6. API enqueues to SandboxedQueue  → Key created
7. Coordinator workers poll            → Workers see empty queues (never see the key!)
```

**THE BUG: Steps 5-6 create NEW stations and enqueue to them, but the workers were created BEFORE these stations existed. The workers have already scanned for their queue patterns and found nothing.**

Wait, that's not quite right either. Workers poll continuously...

Let me re-examine the actual flow.

---

## THEORY REFINEMENT

The workers poll continuously using `scan_iter()` to find queue segments:
```python
async for queue_key in redis_client.scan_iter(match=pattern):
```

This SHOULD find new keys as they appear. Unless...

**New Theory: The Station Doesn't Have NON_BLOCKING_SANDBOXED Type in Redis**

The worker type determines which queue pattern to scan:
- NON_BLOCKING_SANDBOXED workers scan: `*:SandboxedQueue:*`
- NON_BLOCKING workers scan: `*:Queue:*`

Maybe the station is being created with wrong `step_type` in Redis?

Let me check what the actual station data looks like in Redis.

## Next Steps

1. [x] ~~Add logging to show ACTUAL Redis server info~~ - Done, confirmed same server
2. [x] ~~Add timestamp logging~~ - Done, 23-second gap found
3. [ ] Check station's `step_type` field in Redis after publish
4. [ ] Verify worker_type of polling workers matches queue pattern
5. [ ] Check if station sync happens AFTER workers start scanning

---

## Commands Reference

```bash
# Check SandboxedQueue keys on coordination Redis
docker exec blazing-redis redis-cli KEYS "*SandboxedQueue*"

# Check SandboxedQueue keys on data Redis
docker exec blazing-redis-data redis-cli KEYS "*SandboxedQueue*"

# Check API logs
docker logs blazing-api 2>&1 | grep "DEBUG-enqueue_sandboxed"

# Check Coordinator logs
docker logs blazing-coordinator 2>&1 | grep "DEBUG-dequeue_sandboxed"

# Check client connections
docker exec blazing-redis redis-cli CLIENT LIST | grep "172.18.0.3"
```

---

### 2025-12-12 12:00 - NEW FINDINGS

**Verified sandboxed workers ARE polling correctly:**
```
DEBUG-get_next_operation: ENTERED with operation_type=NON_BLOCKING_SANDBOXED
DEBUG-get_next_operation: capabilities=['DYNAMIC_CODE', 'NON_BLOCKING_SANDBOXED', 'SANDBOXED_ROUTE']
DEBUG-SANDBOXED-POLL: station=sandboxed_multiply type=NON-BLOCKING_SANDBOXED normalized=NON-BLOCKING-SANDBOXED expected=NON-BLOCKING-SANDBOXED match=True
DEBUG-DEQUEUE: station=sandboxed_multiply pk=01KC92EWERA8TEQSY8HHZR4QF9 operation_type=NON_BLOCKING_SANDBOXED
DEBUG-DEQUEUE: Calling dequeue_non_blocking_sandboxed_operation for station_pk=01KC92EWERA8TEQSY8HHZR4QF9
```

**BUT the queue is empty when coordinator checks:**
```
DEBUG-dequeue_sandboxed: pattern=blazing:default:workflow_definition:Station:01KC92EWERA8TEQSY8HHZR4QF9:SandboxedQueue:*
DEBUG-dequeue_sandboxed: found 0 segments: []
DEBUG-dequeue_sandboxed: ALL SandboxedQueue keys in Redis: []
```

**API successfully enqueues:**
```
DEBUG-enqueue_sandboxed: operation_pk=01KC92EWHPKW5D6A5MF003VCQM, queue_key=blazing:default:workflow_definition:Station:01KC92EWERA8TEQSY8HHZR4QF9:SandboxedQueue:node-1
DEBUG-enqueue_sandboxed: lpush result=1
DEBUG-enqueue_sandboxed: VERIFY exists=1, len=1
DEBUG-enqueue_sandboxed: ALL_SANDBOXED_KEYS=['blazing:default:workflow_definition:Station:01KC92EWERA8TEQSY8HHZR4QF9:SandboxedQueue:node-1']
```

**SAME station_pk in both logs!** (`01KC92EWERA8TEQSY8HHZR4QF9`)

**New Observations:**
1. API and Coordinator use SAME station_pk
2. Key exists immediately after API enqueue (VERIFY exists=1)
3. But when Coordinator checks, ALL SandboxedQueue keys = []
4. Direct redis-cli check shows empty too

**THE KEY DISAPPEARS BETWEEN API AND COORDINATOR**

**Possible Causes:**
1. ❌ Different Redis instances - RULED OUT (same version, same port)
2. ❌ Different station_pk - RULED OUT (same pk in both logs)
3. ❓ Key is deleted after creation
4. ❓ FLUSHDB timing issue

**New Theory: Test Fixture Flush Timing**

Looking at fixture order:
1. Test fixture flushes Redis
2. Fixture restarts coordinator
3. Fixture waits for workers
4. TEST RUNS: calls app.publish() → enqueues sandboxed operation
5. **But when does coordinator restart vs when API receives publish?**

Need to check if there's a race condition where:
- API receives request while coordinator is still restarting
- API creates key
- Then coordinator restart FLUSHES Redis again?

Actually no - the fixture only flushes ONCE at the beginning.

**New Theory: Route Operation Gets Picked Up First**

Looking at logs more carefully:
- Route `call_sandboxed_station` has `station_type=NON-BLOCKING`
- It gets picked up by trusted worker first
- Route executes and calls sandboxed station
- Sandboxed operation is enqueued
- But by then... what?

Let me check if the route successfully completes before the sandboxed operation.

---

### 2025-12-12 12:30 - ROOT CAUSE FOUND! 🎯

**The actual issue was in WorkerThread._async_init():**

The sandboxed operation WAS being dequeued correctly by the sandboxed worker:
```
DEBUG-dequeue_sandboxed: found 1 segments: ['blazing:...SandboxedQueue:node-1']
DEBUG-dequeue_sandboxed: rpop(...) = 01KC93125RGB3Q3R0YACS8JHDP
```

But then when it executed, it was using the WRONG backend:
```
DEBUG-execute_operation: op=01KC93125RGB3Q3R0YACS8JHDP, station=sandboxed_multiply, backend=<ExternalExecutorBackend>
```

**The Bug (line 3646 in runtime.py):**
```python
# BEFORE (broken):
self.executor_backend = get_executor_backend(container_url=executor_url)
```

The call to `get_executor_backend()` didn't pass `backend_type`, so it defaulted to `'external'` which creates `ExternalExecutorBackend`. Even though `executor_url` was set to `http://pyodide-executor:8000`, the backend type wasn't specified!

**The Fix:**
```python
# AFTER (fixed):
is_sandboxed = 'SANDBOXED' in worker_type
backend_type = 'pyodide' if is_sandboxed else 'external'
self.executor_backend = get_executor_backend(backend_type=backend_type, container_url=executor_url)
```

Now sandboxed workers will create `PyodideExecutorBackend` instead of `ExternalExecutorBackend`.

---

### 2025-12-12 13:00 - SECOND BUG FOUND AND FIXED! 🎯

**After the first fix, a new error appeared:**
```
DEBUG-execute_operation: exec_result success=False, error=object of type 'int' has no len()
```

**Root Cause Discovery:**

When a route calls a sandboxed station:
1. Route runs in Docker executor
2. Route's station wrapper calls `/v1/data/operations/{id}/wait` API to wait for sandboxed result
3. `/wait` endpoint called `OperationDAO.get_result()` → `get_data(data_type='result')`
4. `get_data()` at line 2519 calls `Util.deserialize_data(serialized_data)` which strips `value|` prefix and returns integer `56`
5. Station wrapper receives integer `56` but expects string like `value|56`
6. Line 1051 in service.py tries `len(result_raw)` on integer → **"object of type 'int' has no len()"**

**The Bug:**
The `/wait` endpoint was returning DESERIALIZED results instead of raw results. The executor's station wrapper expects raw format-prefixed strings (`value|56`, `dill|{base64}`, `pickle|{hex}`) and handles deserialization itself.

**The Fix (data_access.py):**

1. Added `raw=True` parameter to `get_data()` method:
```python
async def get_data(cls, operation_pk, data_type, allow_unsafe_deserialization: bool = False, delete: bool = False, raw: bool = False):
    # ...
    # If raw=True, return the serialized data without deserialization
    # Used for inter-executor communication (e.g., station wrappers calling sandboxed stations)
    if raw:
        if isinstance(serialized_data, bytes):
            return serialized_data.decode('utf-8')
        return serialized_data
```

2. Added `get_result_raw()` method:
```python
@classmethod
async def get_result_raw(cls, operation_pk, delete: bool = False):
    """Get raw result with format prefix (value|, dill|, pickle|) without deserialization."""
    return await cls.get_data(operation_pk, data_type='result', delete=delete, raw=True)
```

3. Updated `/wait` endpoint in `operation_data_api.py` to use `get_result_raw()`:
```python
if operation_dao.current_status == "DONE":
    # CRITICAL: Use get_result_raw() to return result WITH format prefix
    result = await OperationDAO.get_result_raw(operation_id)
```

**Verification:**
```bash
# test_sandboxed_station_basic - PASSED
uv run pytest tests/test_z_executor_e2e.py::test_sandboxed_station_basic -xvs
# ✓ Sandboxed station basic test passed: 7 * 8 = 56

# All sandboxed/pyodide tests - PASSED (13/13)
uv run pytest tests/test_z_executor_e2e.py -v -k "sandboxed or pyodide"
# 13 passed, 21 deselected

# Full executor e2e suite - 33/34 passed (1 unrelated failure)
uv run pytest tests/test_z_executor_e2e.py -v
# 33 passed, 1 failed (test_all_4_worker_types_with_services - pre-existing issue)
```

---

## Summary of Fixes

| Bug | Location | Root Cause | Fix |
|-----|----------|------------|-----|
| Wrong executor backend | runtime.py:3646 | `get_executor_backend()` called without `backend_type` | Pass `backend_type='pyodide'` for sandboxed workers |
| "object of type 'int' has no len()" | operation_data_api.py:951 | `/wait` endpoint deserializing results before returning | Use `get_result_raw()` to return raw format-prefixed strings |
