# What's Next

## Completed (2025-12-01)

### ✅ Pyodide Executor Concurrent Execution Fix
Fixed critical race condition in Pyodide executor where shared global variables caused 92-100% failure rate under concurrent load.

**Root Cause:** Single global Pyodide instance with shared variables (`_blazing_args`, `_blazing_kwargs`, etc.) caused race conditions when:
1. Multiple operations ran concurrently
2. Multi-station routes called back to same executor (reentrancy)

**Fix:** Per-operation namespaced variables using operation ID:
```javascript
const opPrefix = `_op_${operationId.replace(/-/g, '_')}`;
pyodide.globals.set(`${opPrefix}_function`, serializedFunction);
```

**Results:** 0-8% → 95-99% success rate at 100 concurrent operations

---

## 🧪 CRITICAL: Unit Tests for Race Condition Detection

**Priority: HIGH**

The race condition we just fixed was extremely hard to catch because:
1. Only manifests under concurrent load
2. Symptoms vary (wrong args, missing function, type errors)
3. Transient - sometimes succeeds, sometimes fails
4. Deadlock variant was even harder to detect

**Need tests that:**
1. Simulate concurrent Pyodide executions with overlapping globals
2. Verify per-operation isolation works correctly
3. Test nested/reentrant execution (route → station → route)
4. Validate cleanup of namespaced variables
5. Stress test with 100+ concurrent operations

**Test file to create:** `tests/test_pyodide_concurrency.py`

---

## Remaining Gaps

### 1. Coordinator-side: Send scaling commands to executor
The coordinator currently has ProcessController running workers in-process (BAD). It needs to:
- Call POST /v1/executor/configure instead of spawning local workers
- Read queue depths and calculate scaling decisions
- Send those decisions to the executor

### 2. Client-side: sandboxed=True decorator parameter
Allow users to mark stations as sandboxed:
```python
@app.station(name="user_calc", station_type="NON_BLOCKING", sandboxed=True)
async def user_calculation(x, y, services=None):
    result = await services['MyService'].compute(x, y)
    return result
```

### 3. End-to-end test
Test the full flow: sandboxed station → service call → trusted worker → result

---

## Priority Order
1. **Unit tests for race conditions** - Prevent regressions of hard-to-catch bugs
2. Coordinator refactor - Remove in-process execution, send commands to executor
3. sandboxed=True decorator - Client-side support for marking stations
4. E2E test - Validate the service bridge works end-to-end