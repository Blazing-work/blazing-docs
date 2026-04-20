# Debugging Journal: Service Invoke Timeout Issue

**Date Started:** 2025-11-30
**Status:** IN PROGRESS
**Test:** `test_service_invocation_pyodide`

## Problem Statement

When sandboxed Pyodide code calls a service method (e.g., `services['MathService'].calculate()`), the call times out after 5 minutes. The NON-BLOCKING workers are not picking up the service invoke operation despite it being enqueued correctly.

## Current State

### What Works ✅
1. Pyodide executor receives and executes sandboxed code
2. Sandboxed code calls `services['MathService'].calculate()`
3. Pyodide JS bridge makes POST to `/v1/services/MathService/invoke`
4. API receives the POST request (logged in API logs)
5. API creates `__service_invoke__` station with `station_type=NON_BLOCKING`
6. API creates operation with `operation_type=NON_BLOCKING`
7. API enqueues operation to `Queue:node-1` (NOT SandboxedQueue)
8. Queue key exists: `blazing:default:workflow_definition:Station:{pk}:Queue:node-1`
9. Queue has 1 item (LLEN = 1)

### What Doesn't Work ❌
1. Coordinator shows `async_work=False (backlog=0, total=0)` - doesn't see the queue work
2. NON-BLOCKING workers (13 of them) are not picking up the operation
3. The API times out waiting for the operation to complete (5 minute timeout)

## Key Evidence

### Coordinator Logs
```
PILOT-LIGHT-CHECK:
  async_work=False (backlog=0, total=0),           <-- WRONG! Queue has 1 item
  blocking_work=False (backlog=0, total=0),
  async_sandboxed_work=True (backlog=1, total=1),  <-- Correct
  blocking_sandboxed_work=False (backlog=0, total=0),
  workers: NON-BLOCKING=13, BLOCKING=0, NON_BLOCKING_SANDBOXED=1, BLOCKING_SANDBOXED=0
```

### Redis State
```bash
# Queue key exists and matches NON_BLOCKING_QUEUE_PATTERN
$ docker exec blazing-redis redis-cli KEYS "blazing:*:workflow_definition:Station:*:Queue:*"
blazing:default:workflow_definition:Station:01KBAVXHVXTSAC9JQP1XHBMQ2R:Queue:node-1

# Queue has 1 item
$ docker exec blazing-redis redis-cli LLEN "blazing:default:workflow_definition:Station:01KBAVXHVXTSAC9JQP1XHBMQ2R:Queue:node-1"
1

# Station details
$ docker exec blazing-redis redis-cli HGETALL "blazing:default:workflow_definition:Station:01KBAVXHVXTSAC9JQP1XHBMQ2R"
pk                 01KBAVXHVXTSAC9JQP1XHBMQ2R
name               __service_invoke__
station_type       NON_BLOCKING
priority           100.0
serialized_function  (empty - no function needed)
```

### API Logs
```
INFO: 172.18.0.3:34070 - "POST /v1/services/MathService/invoke HTTP/1.1" 200 OK
```
Note: The IP `172.18.0.3` is the Pyodide executor container.

### Pyodide Executor Logs
```
[ServiceClient] Calling MathService.calculate() with args=[2,3,7], kwargs={}, priority=0
[ServiceClient] POST http://api:8000/v1/services/MathService/invoke (timeout=300000ms)
ServiceTimeoutError: Service call timeout after 300000ms for MathService.calculate()
```

## Queue Patterns

### Defined in runtime.py
```python
# TRUSTED WORKERS
BLOCKING_QUEUE_PATTERN = "blazing:*:workflow_definition:Station:*:BlockingQueue:*"
NON_BLOCKING_QUEUE_PATTERN = "blazing:*:workflow_definition:Station:*:Queue:*"

# SANDBOXED WORKERS
BLOCKING_SANDBOXED_QUEUE_PATTERN = "blazing:*:workflow_definition:Station:*:BlockingSandboxedQueue:*"
NON_BLOCKING_SANDBOXED_QUEUE_PATTERN = "blazing:*:workflow_definition:Station:*:SandboxedQueue:*"
```

The queue key `blazing:default:workflow_definition:Station:01KBAVXHVXTSAC9JQP1XHBMQ2R:Queue:node-1` should match `NON_BLOCKING_QUEUE_PATTERN`.

## Investigation Steps

### 1. ✅ Verified queue key format matches pattern
The queue key format is correct.

### 2. 🔍 INVESTIGATING: Why does coordinator's _compute_depth() return 0?

The `_compute_depth()` function uses SCAN with the pattern and LLEN on each key:

```python
async def _compute_depth(pattern):
    total = 0
    samples = {}
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
        if keys:
            async with redis_client.pipeline(transaction=False) as pipeline:
                for key in keys:
                    pipeline.llen(key)
                lengths = await pipeline.execute()
            for key, length in zip(keys, lengths):
                length = int(length or 0)
                total += length
                # ...
        if cursor == 0:
            break
    return total, samples
```

**Hypotheses:**
1. The SCAN is not returning the key (different Redis database?)
2. The SCAN pattern matching is failing somehow
3. The coordinator is connected to a different Redis instance

### 3. TODO: Test SCAN from coordinator container

Need to verify the coordinator container can see the queue key.

### 4. TODO: Add debug logging to _compute_depth()

Add logging to see what keys SCAN returns.

## Code Locations

- **Service invoke endpoint:** `src/blazing_service/server.py:1490-1620`
- **Queue depth computation:** `src/blazing_service/engine/runtime.py:1220-1260`
- **Queue patterns:** `src/blazing_service/engine/runtime.py:131-140`
- **enqueue_non_blocking_operation:** `src/blazing_service/data_access/data_access.py:1405-1422`

## Timeline

| Time | Event |
|------|-------|
| T+0 | Test starts, creates route station with `NON_BLOCKING_SANDBOXED` type |
| T+1s | Job created, unit enqueued to sandboxed queue |
| T+2s | Pyodide executor picks up sandboxed operation |
| T+3s | Pyodide executes sandboxed code, calls service |
| T+4s | Pyodide JS bridge POSTs to API `/v1/services/MathService/invoke` |
| T+5s | API creates `__service_invoke__` station and operation |
| T+6s | API enqueues to `Queue:node-1` |
| T+7s | API starts polling for operation completion... |
| T+307s | **TIMEOUT** - Worker never picked up the operation |

## Next Steps

1. [ ] Check if coordinator SCAN can see the queue key
2. [ ] Add debug logging to `_compute_depth()` to see what keys are returned
3. [ ] Verify coordinator and API are using same Redis connection parameters
4. [ ] Check if there's a timing issue (queue depth calculated before enqueue)
