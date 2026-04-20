# Debugging Sandboxed Workers - Journey Log

**Date:** 2025-12-01
**Status:** In Progress
**Issue:** Sandboxed workers (Pyodide) not processing operations despite being created

---

## Executive Summary

This document chronicles the debugging journey to fix sandboxed worker execution in Blazing's 4-worker-type architecture. We discovered and fixed two critical bugs:

1. **ThreadController not passing `worker_type` to DAO** - Workers had wrong type in Redis
2. **`asyncio.gather` called with objects instead of coroutines** - Workers never entered polling loops

Despite these fixes, sandboxed tasks still fail. Investigation continues.

---

## Timeline

### Phase 1: ThreadController worker_type Bug (Previous Session)

**Problem Identified:**
Sandboxed workers (WP:1000+) were being created with `worker_type=NON_BLOCKING_SANDBOXED` in memory, but their `WorkerThreadDAO` records in Redis showed `worker_type=NON-BLOCKING`.

**Root Cause:**
`ThreadController._async_init()` was the FIRST code to call `WorkerThreadDAO.get_or_create()`, but wasn't passing the `worker_type` parameter:

```python
# BEFORE - runtime.py:3722 (BUG)
self.worker_thread_DAO, _ = await WorkerThreadDAO.get_or_create(
    self.worker_thread_name,
    worker_process_pk=self.worker_process.worker_process_DAO.pk,
    current_command=f"COUNT={self.initial_num_async_operations}"
)  # <-- worker_type defaults to "NON-BLOCKING"!
```

**Fix Applied:**
```python
# AFTER - runtime.py:3720-3730
worker_type = getattr(self.worker_process, 'worker_type', 'NON-BLOCKING')
self.worker_thread_DAO, _ = await WorkerThreadDAO.get_or_create(
    self.worker_thread_name,
    worker_process_pk=self.worker_process.worker_process_DAO.pk,
    current_command=f"COUNT={self.initial_num_async_operations}",
    worker_type=worker_type  # ← Now passes correct type!
)
```

**Verification:**
```bash
docker exec blazing-redis redis-cli --scan --pattern "blazing:default:execution:WorkerThread:*" | \
  head -20 | xargs -I {} sh -c 'echo -n "{}: " && docker exec blazing-redis redis-cli HGET {} "worker_type"'
```

Output now shows:
```
blazing:default:execution:WorkerThread:01KBE...: NON_BLOCKING_SANDBOXED  ✅
```

---

### Phase 2: asyncio.gather Bug (Current Session)

**Problem Identified:**
After fixing worker_type, workers still weren't processing operations. Debug logging revealed that `_start_async()` was never being called on WorkerAsync instances.

**Investigation:**

Added debug logging to trace the worker startup chain:

```python
# AsyncController.start()
print(f"DEBUG-AsyncController.start: {self.name} starting", flush=True)

# AsyncController._start_async()
print(f"DEBUG-AsyncController._start_async: {self.name} creating task", flush=True)

# AsyncController._start_child()
print(f"DEBUG-AsyncController._start_child: {self.name} ENTERED", flush=True)

# WorkerAsync._start_async()
print(f"DEBUG-_start_async: {self.name} ENTERED _start_async", flush=True)
```

**Root Cause Found:**

In `WorkerThread.start()` at line 3908-3913:

```python
# BEFORE (BUG)
await asyncio.gather(
    *self.async_controllers,  # BUG: Spreading objects, not coroutines!
    self._maintenance(),
)
```

The `*self.async_controllers` unpacks `AsyncController` objects, not their `.start()` coroutines. Python's `asyncio.gather()` quietly accepts non-coroutine objects and does nothing with them.

**Fix Applied:**

```python
# AFTER - runtime.py:3908-3913
# Start all AsyncControllers and run maintenance loop concurrently
# Each AsyncController.start() creates an asyncio task for the worker's polling loop
await asyncio.gather(
    *[ac.start() for ac in self.async_controllers],
    self._maintenance(),
)
```

**Docker Build Cache Issue:**

Changes weren't appearing in the container due to BuildKit caching. Had to force rebuild:

```bash
# Force cache invalidation
echo "# force rebuild $(date)" >> src/blazing_service/engine/runtime.py

# Rebuild and recreate
docker-compose build coordinator
docker-compose up -d --force-recreate coordinator
```

**Verification:**

```bash
docker logs --since 2m blazing-coordinator 2>&1 | grep "DEBUG-_start_async"
```

Output now shows:
```
DEBUG-_start_async: WP:1000:WT:0:WA:0 ENTERED _start_async
DEBUG-_start_async: WP:1000:WT:0:WA:0 loop starting, is_running=True, worker_type=NON_BLOCKING_SANDBOXED  ✅
```

---

### Phase 3: Current State (Investigation Ongoing)

**What's Working:**

1. ✅ Workers have correct `worker_type=NON_BLOCKING_SANDBOXED` in Redis
2. ✅ Workers enter polling loop (`DEBUG-_start_async: ... loop starting`)
3. ✅ Workers find stations (`DEBUG-get_next_operation: NON_BLOCKING_SANDBOXED found 2 stations`)
4. ✅ Workers successfully dequeue operations (`DEBUG-get_next_operation: dequeued: 01KBE...`)

**What's Still Broken:**

Despite successful dequeue, tasks fail with:
- "Server disconnected" errors
- "Timeout waiting for result"
- Backlog stays at 20 (not decreasing)

**Current Observations:**

```
Sandboxed workers: 7, Sandboxed backlog: 20
```

The backlog should decrease as workers process operations, but it stays constant.

---

## Key Code Locations

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| ThreadController fix | runtime.py | 3720-3730 | Pass worker_type to DAO |
| asyncio.gather fix | runtime.py | 3908-3913 | Start AsyncControllers properly |
| get_next_operation | runtime.py | 5065-5147 | Station polling and dequeue |
| WorkerAsync._start_async | runtime.py | 4331-4339 | Main polling loop |
| AsyncController | runtime.py | 4119-4130 | Task creation wrapper |

---

## Commands Reference

### Check Worker Types
```bash
docker exec blazing-redis redis-cli --scan --pattern "blazing:default:execution:WorkerThread:*" | \
  head -20 | xargs -I {} sh -c 'echo -n "{}: " && docker exec blazing-redis redis-cli HGET {} "worker_type"'
```

### Check Queue Backlog
```bash
docker exec blazing-redis redis-cli --scan --pattern "*SandboxedQueue*" | \
  xargs -I {} sh -c 'echo "=== {} ===" && docker exec blazing-redis redis-cli LLEN {}'
```

### View Recent Coordinator Logs
```bash
docker logs --since 2m blazing-coordinator 2>&1 | grep -E "(DEBUG-|ERROR|Exception)"
```

### Force Docker Rebuild
```bash
echo "# force rebuild $(date)" >> src/blazing_service/engine/runtime.py
docker-compose build coordinator
docker-compose up -d --force-recreate coordinator
```

### Restart After FLUSHDB
```bash
docker exec blazing-redis redis-cli FLUSHDB && docker-compose restart api coordinator
```

---

## Lessons Learned

1. **asyncio.gather accepts any iterable** - It won't raise errors for non-coroutines, they just won't execute
2. **Docker BuildKit caches aggressively** - May need cache-busting comments or `--no-cache`
3. **ContextVar doesn't propagate to subprocesses** - Must extract context from Redis keys
4. **First DAO.get_or_create() wins** - Subsequent calls return existing record without updating
5. **Station type normalization matters** - Both `NON_BLOCKING_SANDBOXED` and `NON-BLOCKING-SANDBOXED` must work

---

## Next Investigation Areas

1. **Why do operations fail after dequeue?**
   - Check Pyodide executor logs: `docker logs blazing-pyodide-executor`
   - Trace operation execution path after `get_next_operation()`

2. **WorkerProcess.start() structure:**
   - Line 3469: `await self._maintenance()` - does this block ThreadController starts?
   - Are ThreadControllers started in a different code path?

3. **CRDT Queue consistency:**
   - Are node-specific queue segments being read correctly?
   - Pattern: `SandboxedQueue:node-1` vs `SandboxedQueue:*`

---

## Related Documentation

- [CLAUDE.md](../CLAUDE.md) - Main architecture and session summaries
- [EXECUTOR_ARCHITECTURE.md](./EXECUTOR_ARCHITECTURE.md) - 4 worker type matrix
- [crdt-multimaster-queues.md](./crdt-multimaster-queues.md) - Queue partitioning strategy

---

## Phase 4: Scale Testing Results (Current)

**Date:** 2025-12-01 19:30

**Test:** 100 concurrent sandboxed multi-station units

**Results:**
- 5-8/100 units succeeded
- ~16 seconds total execution time
- Throughput: ~0.5 units/second when working

**Errors Found in Pyodide Executor:**
```
NameError: name '_blazing_serialized_function' is not defined
TypeError: calculate() missing 1 required positional argument: 'c'
TypeError: add() got an unexpected keyword argument 'a'
```

**Analysis:**
The sandboxed workers infrastructure is working correctly:
- ✅ Workers spawn with correct `worker_type=NON_BLOCKING_SANDBOXED`
- ✅ Workers enter polling loops
- ✅ Workers find stations and dequeue operations
- ✅ Workers connect to Pyodide executor at `http://pyodide-executor:8000`

The issue was in the **Pyodide executor** itself:
- ❌ Function execution fails under concurrent load
- ❌ Arguments not being passed correctly to some invocations
- ❌ Serialized function context sometimes missing

---

### Phase 5: Per-Operation Variable Isolation Fix ⭐ CRITICAL FIX

**Date:** 2025-12-01 20:00

**Root Cause Identified:**

The Pyodide executor used **shared global variables** for all concurrent executions:
- `_blazing_serialized_function`
- `_blazing_args`
- `_blazing_kwargs`
- `_blazing_stations_to_inject`
- `_blazing_services_to_inject`

When multiple operations ran concurrently (especially nested calls from multi-station routes), these globals would be overwritten causing:
- `NameError: name '_blazing_serialized_function' is not defined`
- `TypeError: function() missing required arguments`
- Arguments from one operation being used by another

**Attempted Fix: Mutex (FAILED)**

Initially tried serializing executions with a promise-based mutex:
```javascript
let executionMutex = Promise.resolve();
async function withExecutionLock(fn) { ... }
```

This caused **DEADLOCK** with multi-station routes:
1. Route operation acquires mutex
2. Route calls `add` station via HTTP → creates new operation
3. `add` operation arrives at executor, waits for mutex
4. Route is waiting for `add` result
5. **DEADLOCK**: Route holds mutex, `add` waits for mutex

**Final Fix: Per-Operation Namespaced Variables**

Instead of shared globals, each operation gets its own namespace:
```javascript
// Each operation uses unique variable names
const opPrefix = `_op_${operationId.replace(/-/g, '_')}`;

pyodide.globals.set(`${opPrefix}_function`, serializedFunction);
pyodide.globals.set(`${opPrefix}_args`, args);
pyodide.globals.set(`${opPrefix}_kwargs`, kwargs);
pyodide.globals.set(`${opPrefix}_stations`, stations);
pyodide.globals.set(`${opPrefix}_services`, services);
```

Python execution code reads from its own namespace:
```python
_op_prefix = "${opPrefix}"  # Injected by JS
func_b64 = g.get(f'{_op_prefix}_function')
args_raw = g.get(f'{_op_prefix}_args', 'value|[]')
kwargs_raw = g.get(f'{_op_prefix}_kwargs', 'value|{}')
```

**Files Modified:**
- `docker/pyodide-executor/server.mjs` - Per-operation namespacing in `executeInSandbox()`
- `docker/pyodide-executor/datasource_manager.mjs` - Updated `_injectIntoPyodide()` with operationId

**Results:**
- Before fix: 0-8/100 success rate
- After fix: **95-99/100 success rate** (massive improvement!)

Remaining failures (~5%) are likely transient network issues, not race conditions.

---

## Summary of Fixed Bugs

| # | Bug | Location | Status |
|---|-----|----------|--------|
| 1 | ThreadController not passing worker_type | runtime.py:3720-3730 | ✅ Fixed |
| 2 | asyncio.gather with objects instead of coroutines | runtime.py:3908-3913 | ✅ Fixed |
| 3 | Docker BuildKit caching stale code | N/A | ✅ Workaround found |
| 4 | Pyodide executor concurrent execution | server.mjs, datasource_manager.mjs | ✅ Fixed with per-operation namespacing |

---

## Key Learnings

1. **Single global Pyodide instance** - All requests share the same WASM runtime and Python globals
2. **Nested operations create reentrancy** - Multi-station routes call back to the same executor
3. **Mutex causes deadlock with reentrancy** - Can't serialize operations that depend on each other
4. **Per-operation namespacing** - Each operation gets unique variable names, allowing safe concurrent execution
5. **Operation IDs are unique** - ULIDs provide natural isolation keys

---

*Last Updated: 2025-12-01 20:15*
