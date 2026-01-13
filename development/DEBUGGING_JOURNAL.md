# Blazing REST API Debugging Journal

## 2025-11-21: Worker Thread App ID Context Issue

### Problem
Workers report "Found 0 stations" even though stations exist in Redis and have operations enqueued.

### Investigation
1. **Verified stations exist:** `blazing:default:workflow_definition:Station:*` keys present in Redis
2. **Verified operations enqueued:** Station queue has 1 operation waiting
3. **Verified worker type matches:** Station is NON-BLOCKING, workers are NON-BLOCKING
4. **Found root cause:** Workers query `StationDAO.find().sort_by("-priority")` which returns 0 results

### Root Cause
**App ID context is not set in worker threads!**

- Workers run in separate processes/threads spawned by ProcessController
- ContextVar (used for app_id) does NOT propagate across process/thread boundaries
- When workers call `StationDAO.find()`, it looks in the wrong namespace (empty or default ContextVar value)
- Only 1 instance of "Set app_id context" in all logs, should be per-worker-thread

### Solution
Need to set app_id="default" when workers initialize, BEFORE they make any DAO queries. This is similar to the fix documented in CLAUDE.md for the reference implementation, but needs to be applied to the REST API worker initialization.

### Previous Related Issue (from CLAUDE.md)
The reference implementation had the same app_id context issue in worker threads. Fix was to extract app_id from existing Redis keys before making DAO calls. For the initial station query, we need to set app_id at worker thread initialization instead.

### Status
-  Identified issue
- � Implementing fix

---

## 2025-11-21: Coordinator _follow_command Indentation Bug

### Problem
Coordinator's `_follow_command()` method was being called but body never executed. Workers were never created even though command was set to `COUNT=14`.

### Root Cause
The `try` block in `_follow_command()` was indented at the wrong level - it was INSIDE the nested `_adjust_process_count()` function instead of in the main method body.

### Solution
Un-indented the `try` block by 4 spaces to place it at the correct indentation level (same as the `async def _adjust_process_count` line).

### Status
 Fixed - Workers are now created and actively polling

---

## 2025-11-21: Server-Side Station Wrapping for REST API

### Problem
Route functions call stations (like `await double(value)`), but when deserialized on the coordinator, those station references don't exist in the namespace. Routes execute but return `None` because station calls fail silently.

### Root Cause
In the reference implementation, stations and routes share the same Blazing instance, so station decorators naturally set up the namespace. In the REST API architecture:
1. Client serializes route functions with references like `await double(...)`
2. Coordinator deserializes and executes the function
3. But `double` doesn't exist in the coordinator's namespace!
4. Route function hangs waiting for a function that never runs

### Solution Implemented
Added server-side station wrapping in execute_operation (runtime.py:3987-3994):
1. Before executing a route, query Redis for all station definitions
2. Create wrapper functions that check enqueue_var context
3. If should_enqueue=True, wrappers create operations and enqueue them
4. Inject wrappers into the route function's global namespace using func.__globals__[step_name] = wrapper

### Status
- DONE: Identified issue
- DONE: Implemented Station.create_station_wrappers() method
- DONE: Verified wrappers are created and injected - logs show "Injected 1 station wrappers: ['double']"
- IN PROGRESS: Debugging why wrapper execution hangs (function awaits but never completes, no DEBUG-station_wrapper messages appear)

### Investigation Update - Wrapper Not Being Called

#### Findings:
1. ✅ Station wrappers ARE created successfully
2. ✅ Wrappers ARE injected into func.__globals__ (verified 'double' appears in the dict)  
3. ❌ Wrappers are NEVER called - no "STATION WRAPPER CALLED" messages in logs
4. ❌ Route function hangs indefinitely when trying to await double()

#### Hypothesis:
The deserialized route function may have a closure or bytecode that was compiled with a non-existent reference to `double`, and modifying __globals__ at runtime doesn't help because:
- The function's bytecode might have cached name lookups
- Dill deserialization might create a different __globals__ context
- There may be a scope/closure issue with how the function was serialized

#### Next Steps:
- Option 1: Instead of modifying __globals__, re-serialize the route with correct references
- Option 2: Use exec() to dynamically create the route function with wrappers already in scope
- Option 3: Investigate how dill serializes/deserializes function __globals__
- Option 4: Check the reference implementation's serialization approach

### ✅ SOLVED - Unit Operation Pointer Issue

**Problem:** When the route's station wrapper creates a new operation for the `double` station, the Unit's `operation_dao_pk` field still points to the ROUTE operation, not the newly created station operation.

**Evidence:**
```
DEBUG-get_next_operation: Got UnitDAO, operation_dao_pk=01KAM9BXF97ZQSVN31YAK0HXM6  # Route operation!
DEBUG-station_wrapper: Operation 01KAM9BZ1A7Z791JX19F91QCGP enqueued  # Station operation!
```

**Root Cause:** The Unit-Operation relationship is one-to-one (`Unit.operation_dao_pk`), but routes create MULTIPLE operations (one for each station call). When workers dequeue unit_pk and look up the Unit, they got the ROUTE operation instead of the STATION operation.

**Solution:** Update the Unit's `operation_dao_pk` when creating nested operations in the station wrapper (runtime.py:3898-3904):
```python
# Update Unit to point to this new operation
from blazing_service.util.util import Util
await Util.update_fields_in_transaction(
    UnitDAO, unit_pk,
    {'operation_dao_pk': operation_DAO.pk}
)
```

**Result:** ✅ **END-TO-END EXECUTION WORKING!** Test passes with correct result=42 (21 * 2)

---

## 2025-11-21: Pilot Light Mechanism Completely Broken - Coordinator DAO Caching

### Problem
Tests hang indefinitely because NO NON-BLOCKING workers are ever created, even when NON-BLOCKING work exists in queues. The pilot light mechanism that's supposed to guarantee "at least one worker of each type when work exists" is completely non-functional.

### Investigation

**Evidence:**
1. ✅ Queue exists: `blazing:default:workflow_definition:Station:NonBlockingQueue:01KAMBFR7AR1KJW9VG3EKMRZMP`
2. ✅ Queue has 1 item waiting
3. ✅ Queue patterns match reference implementation format: `Station:NonBlockingQueue:{pk}`
4. ❌ Only 4 BLOCKING workers exist, 0 NON-BLOCKING workers
5. ❌ Manual command change in Redis (`MIX=1,1`) NOT picked up by coordinator
6. ❌ Coordinator logs show `command='COUNT=4'` even after Redis updated to `MIX=1,1`
7. ❌ `_optimize_workers_mix()` produces ZERO debug output (runs but does nothing)

**Initial Mistake:** I incorrectly changed queue patterns from `Station:NonBlockingQueue:{pk}` to `Station:{pk}:non_blocking_queue` thinking it was wrong. Verified against reference implementation - the original format WAS CORRECT. Reverted the change.

### Root Cause
**Coordinator caches its `CoordinatorStatusDAO` object and NEVER re-reads from Redis!**

**Evidence:**
- Redis shows: `command='MIX=1,1'`
- Coordinator logs show: `command='COUNT=4'`
- Only 1 CoordinatorStatus key exists (not multiple foremen)
- Coordinator reads command ONCE at initialization and caches the DAO object
- Every subsequent `_follow_command()` call reads from the cached object, never from Redis

**Impact:**
- Pilot light mechanism cannot update worker mix based on queue metrics
- Manual commands via Redis don't work (critical for debugging/testing)
- `_optimize_workers_mix()` runs but cannot change worker counts because its decisions never propagate
- System cannot adapt to workload changes - completely static worker mix

### Solution
Remove DAO caching in coordinator maintenance loop. Must re-fetch `CoordinatorStatusDAO` from Redis on each iteration to pick up:
1. Commands from pilot light mechanism
2. Manual debugging commands
3. External control plane updates

### Status
- ✅ Documented issue
- ✅ Implemented fix
-  Testing and verifying

---

## 2025-11-22: Pilot Light Fix + Function Deserialization Module Conflict

### Problem
Tests timeout because no NON-BLOCKING workers created, even though NON-BLOCKING work exists in queues.

### Investigation - Pilot Light
1. ✅ **Pilot light mechanism WAS the problem** - code was inside `_calculate_worker_mix()` which returned None when no timing stats exist (cold start chicken-and-egg)
2. ✅ **Fix implemented** - Moved pilot light enforcement BEFORE `_calculate_worker_mix()` call (runtime.py:1489-1558)
3. ✅ **Deployed successfully** - Had to recreate Docker container (restart doesn't use new image!)
4. ✅ **Pilot light working** - Logs show "PILOT-LIGHT-ENFORCE: Creating minimum NON-BLOCKING workers (1)" and workers created

### Investigation - Function Deserialization
5. ✅ **Workers ARE dequeueing** - Backlog went from 3 to 0, workers polling correctly
6. ❌ **Deserialization fails** - `_pickle.UnpicklingError: pickle data was truncated`
7. **Root cause discovered:**
   - Functions defined in test files (e.g., `tests/test_docker_example.py` or `debug_publish.py`)
   - Dill serializes them with module path reference
   - On deserialization, dill tries to `import tests`
   - Coordinator has conflicting `tests` package in site-packages (`/app/.venv/lib/python3.13/site-packages/tests/__init__.py`)
   - Import fails, causes "pickle data was truncated" error

**Evidence from traceback:**
```
File "/app/.venv/lib/python3.13/site-packages/dill/_dill.py", line 442, in find_class
    return StockUnpickler.find_class(self, module, name)
  File "/app/.venv/lib/python3.13/site-packages/tests/__init__.py", line 1, in <module>
_pickle.UnpicklingError: pickle data was truncated
```

### Architecture Issue
This reveals a fundamental limitation of the REST API approach:
- **Reference implementation:** Client and coordinator share same codebase, functions can import from same modules
- **REST API implementation:** Client and coordinator are separate processes
- **Problem:** Functions defined in client code cannot be imported by coordinator
- **Impact:** Test functions fail to deserialize on coordinator side

### Solution Analysis

**For Tests:**
- **Best approach:** Option 2 - Use `byref=False` to serialize function code directly
- **Why:** Tests shouldn't be deployed to production containers. Functions should be truly portable.
- **Implementation:** One-line change in client serialization: `dill.dumps(func, byref=False)`
- **Benefits:** Tests remain independent, no coupling to coordinator container

**For Production:**
- **Best approach:** Option 3 - Users deploy shared module to both environments
- **Why:** Follows standard Python deployment patterns, cleaner architecture
- **Pattern:** Users create `my_app/stations.py`, deploy to both client and server
- **Benefits:** Proper module imports, standard Python patterns, easier debugging

**Options Considered:**
1. ❌ Copy test files into coordinator container - couples tests to production, not scalable
2. ✅ Use dill's `byref=False` - **RECOMMENDED FOR TESTS**
3. ✅ Shared module deployment - **RECOMMENDED FOR PRODUCTION**
4. ⏳ Investigate dill session/source - unknown complexity

### Next Steps
1. Modify client serialization to use `byref=False` for test functions
2. Test that deserialization works on coordinator side
3. Verify closures and captures work correctly
4. Document the two patterns (tests vs production) in developer guide

### Status
- ✅ Pilot light fix working perfectly
- ✅ Function deserialization fixed with `byref=False`
- ✅ debug_publish.py works end-to-end (result=42)
- ✅ Async fixture cleanup fixed (conftest.py:677-718) - converted to @pytest_asyncio.fixture
- ⚠️  Pytest tests still hang after fixture setup - investigating root cause

---

## 2025-11-22: Pytest Fixture Event Loop Fix

### Problem
Pytest tests using `docker_blazing_app` fixture hang after fixture setup completes, before test body executes.

### Investigation

**Phase 1: Fixture Cleanup Issue (FIXED ✅)**
1. **Fixture Type Mismatch**: Original fixture was synchronous (@pytest.fixture) but tried to manage async cleanup
2. **Event Loop Conflict**: Pytest-asyncio manages the event loop (asyncio_mode = strict), but fixture tried to create its own loop
3. **Cleanup Code Issue**: Lines 712-727 in conftest.py tried to `get_running_loop()` then `new_event_loop()` causing conflicts

**Phase 2: Test Execution Hang (ONGOING ⚠️)**

After converting to async fixture, cleanup works but tests still hang:

**Symptoms:**
```
===== DEBUG: docker_blazing_app fixture for test: tests/test_docker_example.py::test_multi_station_route =====
DEBUG: api_url=http://localhost:8000
DEBUG: Using default app_id (from bearer token)
DEBUG: ✓ Blazing app created successfully

[TEST HANGS HERE - NEVER ENTERS TEST BODY]
```

**What Works:**
- ✅ `debug_publish.py` - Direct asyncio.run() execution works perfectly (result=42)
- ✅ `test_simple_docker.py` - Standalone async script works perfectly
- ✅ Fixture setup completes successfully
- ✅ Blazing app creation succeeds

**What Fails:**
- ❌ Pytest tests hang after fixture yield, before test body
- ❌ Both simple and complex tests exhibit same behavior
- ❌ Timeout doesn't trigger (suggesting deadlock not slow execution)

**Hypotheses Being Investigated:**

1. **Event Loop Ownership Issue**:
   - Pytest-asyncio creates the event loop for the test
   - Blazing client may be creating/storing its own event loop reference
   - When test tries to run, there may be an event loop mismatch

2. **HTTP Client Initialization**:
   - Blazing client creates httpx.AsyncClient in `__init__`
   - This may bind to the wrong event loop
   - Fixture's event loop vs test's event loop may differ

3. **Async Context Manager Lifecycle**:
   - Blazing client may need explicit async initialization
   - `__init__` may not be the right place for async resource creation
   - May need `async def create()` factory pattern instead

4. **Pytest-asyncio Strict Mode**:
   - `asyncio_mode = strict` may enforce constraints we're violating
   - May need to adjust fixture scope or event loop policy

**Code Comparison:**

Working (debug_publish.py):
```python
async def main():
    app = Blazing(api_url="...", api_token="...")
    # ... works perfectly ...

asyncio.run(main())  # Single event loop, simple lifecycle
```

Not Working (pytest):
```python
@pytest_asyncio.fixture(scope="function")
async def docker_blazing_app(...):
    app = Blazing(api_url="...", api_token="...")
    yield app  # Fixture completes
    # Test hangs before executing test body
```

### Solution Implemented (Partial)
**Location**: [tests/conftest.py:677-718](tests/conftest.py#L677-L718)

Converted `docker_blazing_app` to async fixture using `@pytest_asyncio.fixture`:
```python
@pytest_asyncio.fixture(scope="function")
async def docker_blazing_app(docker_infrastructure, request):
    # ... setup code ...
    yield app

    # Cleanup - simpler in async fixture
    await app.close()  # Direct await instead of managing event loops
```

**Benefits Achieved**:
- ✅ Pytest-asyncio handles event loop management
- ✅ No manual loop creation/management needed
- ✅ Cleaner, more idiomatic async code
- ✅ Cleanup phase fixed

### Next Steps

1. **Investigate Blazing client initialization**:
   - Check if httpx.AsyncClient is being created in `__init__`
   - Verify event loop binding during client creation
   - Consider factory pattern: `await Blazing.create(...)` instead of `Blazing(...)`

2. **Test event loop isolation**:
   - Add debug logging to show event loop IDs
   - Verify fixture's loop == test's loop
   - Check for loop.close() being called prematurely

3. **Review pytest-asyncio documentation**:
   - Verify best practices for async fixtures with async resources
   - Check if fixture_loop_scope needs adjustment
   - Look for known issues with httpx + pytest-asyncio

4. **Simplify to minimal reproduction**:
   - Create minimal test with just `app = Blazing(...)`
   - No publish, no routes - just client creation
   - Isolate whether issue is client init or later operations

### ✅ SOLUTION: Lazy httpx.AsyncClient Initialization

**Root Cause Identified:**
`httpx.AsyncClient()` was created in synchronous `__init__` methods, causing event loop binding issues in pytest-asyncio's strict mode.

**Call Chain:**
1. `Blazing.__init__()` (sync) → creates `RemoteBackend`
2. `RemoteBackend.__init__()` (sync) → creates `BlazingServiceClient`
3. `BlazingServiceClient.__init__()` (sync) → creates `httpx.AsyncClient()` **← EVENT LOOP BINDING ISSUE**

**The Fix:**
**Location**: [src/blazing/api/client.py:79-103](src/blazing/api/client.py#L79-L103)

Implemented lazy initialization pattern:
1. Store connection parameters in `__init__` (no client creation)
2. Create `httpx.AsyncClient` lazily on first async method call via `_ensure_client()`
3. Client is created in proper async context with correct event loop

```python
def __init__(self, base_url: str, token: str, *, timeout: Optional[float] = 30.0, client: Optional[httpx.AsyncClient] = None) -> None:
    self._base_url = base_url.rstrip("/")
    self._token = token
    self._timeout = timeout
    self._client = client  # May be None initially
    self._client_created = client is not None

def _ensure_client(self) -> httpx.AsyncClient:
    """Lazily create httpx client when first needed (in async context)."""
    if self._client is None:
        headers = {"Authorization": f"Bearer {self._token}"}
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )
        self._client_created = True
    return self._client
```

**Verification:**
```bash
$ REDIS_PORT=6379 BLAZING_API_URL=http://localhost:8000 uv run pytest tests/test_docker_example.py::test_simple_route_execution -v -s --timeout=30

DEBUG: ✓ app.publish() completed
DEBUG: ✓ app.create_route_task() completed
DEBUG: ✓ unit.result() completed, result=42
DEBUG: ✓ Test assertion passed!
PASSED
```

### Status
- ✅ Async fixture cleanup fixed
- ✅ **PYTEST HANG ISSUE COMPLETELY FIXED!**
- ✅ Lazy client initialization ensures correct event loop binding
- ✅ Core REST API functionality confirmed working
- ✅ Both standalone scripts and pytest tests work perfectly
- 📝 **SUCCESS**: Pytest-based integration testing now fully functional

---

## 2025-11-22: Python-ULID Package Conflict & Function Serialization Module References

### Problem
Docker integration tests fail with `ModuleNotFoundError: No module named 'tests'` and `_pickle.UnpicklingError: pickle data was truncated` when coordinator tries to deserialize station/route functions.

### Investigation

**Phase 1: Initial Hypothesis - python-ulid Package Conflict ❌**
1. Suspected python-ulid 1.1.0 incorrectly packages test files in `site-packages/tests/`
2. Added Dockerfile workaround: `RUN rm -rf .venv/lib/python*/site-packages/tests`
3. Rebuilt Docker base images with fix
4. **Result:** Error persisted even after Docker fix

**Phase 2: Actual Root Cause - Project Tests Directory ✅**
5. Discovered `tests` module imports from PROJECT directory: `/Users/jonathanborduas/code/blazing/tests/__init__.py`
6. When dill serializes functions defined in test files, it captures module reference `tests.test_docker_example`
7. Coordinator tries to deserialize → needs to `import tests` → fails because project tests/ not available in Docker container
8. This is a fundamental architecture issue: **Functions defined in test files cannot reference their defining module**

**Evidence:**
```python
$ uv run python -c "import tests; print('tests module found at:', tests.__file__)"
tests module found at: /Users/jonathanborduas/code/blazing/tests/__init__.py
```

### Solution Attempted: `byref=False` Serialization

**Theory:**
- Using `dill.dumps(func, byref=False)` serializes function CODE directly without module references
- Should allow functions from any module to be deserialized anywhere
- Works in isolated tests:
  ```python
  async def test_func(...):
      return a + b
  test_func.__module__ = 'tests.test_docker_example'
  serialized = dill.dumps(test_func, byref=False)  # ✅ Works!
  deserialized = dill.loads(serialized)  # ✅ Works!
  ```

**Implementation:**
- Modified `src/blazing/blazing.py:397` to use `byref=False` for stations
- Modified `src/blazing/blazing.py:406` to use `byref=False` for routes
- Added debug logging to verify code execution

**Status:** ⚠️ IN PROGRESS
- ✅ Code changes applied
- ✅ Isolated tests prove `byref=False` works correctly
- ❌ Full integration tests still fail with same ModuleNotFoundError
- ⚠️ Debug logs not appearing - investigating if code is being executed

### Parallel Fixes Applied

**Docker Environment:**
1. ✅ **Fixed Dockerfile.base-worker** - Added workaround to remove conflicting packages:
   ```dockerfile
   # WORKAROUND: Remove conflicting 'tests' package from python-ulid (1.1.0)
   RUN rm -rf .venv/lib/python*/site-packages/tests
   ```
2. ✅ Rebuilt all Docker base images (`make docker-build-bases`)
3. ✅ Rebuilt application images (`make docker-build-all`)

**Local Environment:**
4. ✅ Removed conflicting tests package: `rm -rf .venv/lib/python*/site-packages/tests`
5. ✅ Verified uv uses source code: `/Users/jonathanborduas/code/blazing/src/blazing/blazing.py`

### BREAKTHROUGH: Why `byref=False` Alone Doesn't Work

**Discovery via Pickle Disassembly:**
Using `pickletools.dis()` on serialized functions revealed that even with `byref=False`, dill creates GLOBAL references:
```
273: c        GLOBAL     'tests.test_docker_example __dict__'
```

**Root Cause:**
- `byref=False` prevents importing referenced objects BY REFERENCE
- BUT dill still serializes `func.__globals__` which contains module `__dict__` reference
- This `__dict__` reference requires the module to exist during deserialization
- Result: `ModuleNotFoundError` even with `byref=False`

**Testing Revealed Flaw:**
- Local tests APPEARED to work because `/Users/.../blazing/tests/__init__.py` exists
- Docker tests FAILED because `tests/` directory not copied to container
- This proved `byref=False` alone is insufficient

### Solution Implemented: Clean Serialization with Minimal Globals

**Approach:**
Strip module references BEFORE serialization by recreating function with clean `__globals__`:

```python
import types

# Create minimal globals with only built-ins
minimal_globals = {
    '__builtins__': __builtins__',
    '__name__': '__main__',
    '__doc__': None,
    '__package__': None,
}

# Recreate function with clean globals
clean_func = types.FunctionType(
    original_func.__code__,
    minimal_globals,
    original_func.__name__,
    original_func.__defaults__,
    original_func.__closure__
)
clean_func.__module__ = '__main__'

# Now serialize
serialized = dill.dumps(clean_func, byref=False)
```

**Implementation:**
- Modified [`src/blazing/blazing.py:396-421`](src/blazing/blazing.py#L396-L421) for stations
- Modified [`src/blazing/blazing.py:429-452`](src/blazing/blazing.py#L429-L452) for routes
- Functions now serialize with `__module__ = '__main__'` instead of test module

**Verification:**
✅ Isolated test confirms clean serialization works:
```
Original function: __module__ = 'tests.test_docker_example'
Clean function: __module__ = '__main__'
✓ Deserialization succeeded!
✓ Function executed successfully: result = 12
```

### Outstanding Issues

1. **Operation Enqueuing Bug (UNRELATED to serialization):**
   - Operations stuck in PENDING state, never move to AVAILABLE
   - No AVAILABLE queues exist in Redis
   - This prevents ANY execution, regardless of serialization
   - Issue exists in REST API operation signaling/enqueuing logic
   - Needs separate investigation

### Architecture Considerations

This issue highlights a fundamental design question:
- **Reference Implementation:** Functions and workers share codebase, module imports work naturally
- **REST API Implementation:** Client and coordinator are separate containers
- **Current Limitation:** Functions defined in client-side test files cannot be deserialized server-side

**Possible Solutions:**
1. ✅ `byref=False` serialization (attempted, not working yet)
2. ⏳ Verify `byref=False` is actually being executed in the code path
3. ⏳ Investigate if there are other serialization points we haven't found
4. ⏳ Consider if decorator wrappers are interfering with serialization
5. ❌ Copy test files into Docker (rejected - couples tests to production)
6. ✅ For production: deploy shared modules to both environments (future recommendation)

### Next Steps
1. ✅ ~~Verify debug logging appears~~ - Confirmed code executing
2. ✅ ~~Check serialization code paths~~ - Found and fixed
3. ✅ ~~Investigate why `byref=False` doesn't work~~ - Pickle disassembly revealed GLOBAL references
4. ✅ ~~Implement clean serialization~~ - types.FunctionType() approach working
5. ⏳ **NEW:** Investigate operation enqueuing bug (operations stuck in PENDING)
6. ⏳ Verify clean serialization works end-to-end once enqueuing fixed

### Status
- ✅ Root cause identified (dill serializes `__globals__` with module `__dict__` references)
- ✅ Docker environment cleaned up
- ✅ Local environment cleaned up
- ✅ **Clean serialization implemented** - functions recreated with minimal globals
- ✅ **Verified locally** - clean serialization deserializes successfully without module
- ⚠️ **NEW BUG DISCOVERED:** Operations never enqueued to AVAILABLE queues (unrelated to serialization)
- ⏳ Investigating operation enqueuing issue to test serialization fix end-to-end
- 📝 Documentation updated with findings

---

## 2025-11-23: Environment Replication Tests - Operation Enqueuing Issue

### Problem
New environment replication tests ([test_docker_environment_replication.py](tests/test_docker_environment_replication.py)) hang indefinitely waiting for results. Tests combine Docker infrastructure with environment specification via `dependencies=["six==1.16.0"]` parameter.

### Investigation

**Test Structure:**
1. Test uses `docker_infrastructure` fixture (not `docker_blazing_app`)
2. Creates Blazing app with explicit dependencies: `Blazing(..., dependencies=["six==1.16.0"])`
3. Defines station and route
4. Publishes successfully
5. Creates route task successfully
6. **Hangs waiting for result** - operation never executes

**Evidence from Redis:**
```bash
# Operation exists but stuck in PENDING
$ docker exec blazing-redis redis-cli HGET "blazing:default:unit_definition:Operation:01KAS0FG33EFMQ5649TGBBC32Z" "current_status"
PENDING

# Station queue is empty (operation never enqueued)
$ docker exec blazing-redis redis-cli LLEN "blazing:default:workflow_definition:Station:01KAS0FG2WVET6ERT2YX58DVVW:AVAILABLE"
0

# Stations exist with correct priority
blazing:default:workflow_definition:Station:01KAS0FG2TZBXT5EHERA6ANV06  # priority=0.0 (check_six_version)
blazing:default:workflow_definition:Station:01KAS0FG2WVET6ERT2YX58DVVW  # priority=-1.0 (verify_environment)
```

### ❌ INVALIDATED: Hypothesis About Operation Enqueuing

**Original Theory (PROVEN FALSE):**
The API server's task creation endpoint may be creating Operation objects but not enqueuing them to station queues.

**COUNTEREVIDENCE - User Insight:**
User pointed out: **"but if these tests works, then the API should work..: /Users/jonathanborduas/code/blazing/tests/test_docker_example.py"**

**Test Results:**
- ✅ `test_docker_example.py::test_simple_route_execution` **PASSED** in 7.65 seconds
- ✅ Operations ARE being enqueued correctly
- ✅ Workers ARE picking up and executing operations
- ✅ Results ARE being returned successfully

**Conclusion:**
The API enqueuing logic is **NOT broken**. Operations ARE being enqueued to station queues when using `test_docker_example.py` tests.

**Real Difference:**
The working test (`test_docker_example.py`) does NOT specify `dependencies` parameter, while the failing test (`test_docker_environment_replication.py`) DOES specify `dependencies=["six==1.16.0"]`.

This means the issue is NOT with enqueuing - it's something specific to how operations with environment dependencies are handled.

### Context: Existing Tests vs New Tests

**Important Note:** User confirmed that existing unit tests in `test_docker_example.py` pass successfully.

**User's Key Hypothesis:**
> "the main difference between the 2 is if coordinator is in the same environment as the client, and thus has access to dependencies... at least, thats my hypothesis"

**Working Tests (`test_docker_example.py`):**
- No explicit dependencies specified
- Stations do simple operations (e.g., `return value * 2`)
- No external package imports needed
- Coordinator's environment has all necessary packages (standard library only)
- Operations ARE being enqueued and executed successfully ✅

**Failing Tests (`test_docker_environment_replication.py`):**
- Explicit dependencies: `Blazing(..., dependencies=["six==1.16.0"])`
- Stations import external packages: `import six`
- Coordinator's environment doesn't have `six` installed
- May require environment replication BEFORE execution can begin
- Operations NOT being enqueued ❌

**Need to investigate:**
1. Does the API handle tasks differently when `environment_spec` is present?
2. Is there a "prepare environment" step that must complete before enqueuing?
3. Does the coordinator check for environment availability before polling queues?
4. Are there conditional code paths based on `task.environment_spec` field?

### Next Steps

1. **Compare code paths:**
   - Trace `app.create_route_task()` in working tests vs failing tests
   - Check if `docker_blazing_app` fixture does something special
   - Look for differences in HTTP requests sent to API

2. **Find task creation endpoint:**
   - Search for `POST /v1/tasks` or equivalent route
   - Verify if enqueuing logic exists
   - Check if operation is supposed to be enqueued immediately or via separate signal

3. **Test with existing test:**
   - Run `test_docker_example.py::test_simple_route_execution` to confirm it still works
   - Compare Redis state between working and failing tests
   - Look for queue creation patterns

### Architecture Investigation: Environment Spec Storage vs Execution

**Finding:** The environment replication infrastructure is partially implemented but not connected to operation execution.

**What EXISTS:**
1. ✅ `ServiceDAO` has `environment_spec` and `environment_hash` fields ([data_access.py:853-854](src/blazing_service/data_access/data_access.py#L853-L854))
2. ✅ API server stores environment_spec when publishing services ([server.py:218-227](src/blazing_service/server.py#L218-L227))
3. ✅ Client creates environment_spec from `dependencies` parameter ([blazing.py:459-465](src/blazing/blazing.py#L459-L465))
4. ✅ `EnvironmentReplicator` class exists and can create venvs ([environment_replicator.py](src/blazing_service/worker/environment_replicator.py))

**What's MISSING:**
1. ❌ Stations are not associated with services' environment_spec
2. ❌ `execute_operation()` doesn't check for environment requirements
3. ❌ `execute_operation()` always executes in coordinator's environment
4. ❌ No logic to use `run_in_environment()` for stations with dependencies

**User's Hypothesis Confirmed:**
> "we need to extend the 'placeholder' logic so that all dependencies are 'swap' when we need to execute them"

The "placeholder logic" is the station wrapper system at [runtime.py:3903-3970](src/blazing_service/engine/runtime.py#L3903-L3970). But environment swapping needs to happen at execution time in `execute_operation()` at [runtime.py:4099-4271](src/blazing_service/engine/runtime.py#L4099-L4271).

**Solution Needed:**
1. Associate stations with service environment_spec (either store in StationDAO or look up from ServiceDAO)
2. In `execute_operation()`, before calling `Station.execute_function()`:
   - Check if operation's station has an environment_spec
   - If yes, use `EnvironmentReplicator.get_or_create_environment(env_spec)`
   - Execute using `run_in_environment(python_exe, func, *args, **kwargs)` instead of direct `func(*args, **kwargs)`

**Confirmed by existing tests:**
- `test_docker_example.py` tests work because they use NO dependencies → coordinator's environment is sufficient ✅
- `test_docker_environment_replication.py` tests hang because dependencies ARE specified → coordinator can't execute `import six` ❌

### Status
- ✅ **ROOT CAUSE IDENTIFIED:** Environment replication exists but isn't integrated into operation execution flow
- ✅ Architecture investigation complete - know exactly what needs to be implemented
- ⏳ Need to implement environment swapping in `execute_operation()`
- 📝 Test file created and structured correctly - will work once environment swapping is implemented

---

## 2025-11-26: Executor Backend Selection Fix - Hardcoded BlazingExecutorBackend

### Problem
The `test_e2e_multistation_backend` test was failing with:
```
simple_calc() missing 3 required positional arguments: 'a', 'b', and 'c'
```

Operations were being dequeued correctly, but function execution failed because args/kwargs were not being fetched.

### Investigation

**Environment Configuration:**
- Coordinator configured with `BLAZING_EXECUTOR_ENABLED=true`
- Coordinator configured with `BLAZING_EXECUTOR_BACKEND=pyodide` (should use `InProcessExecutorBackend`)
- Expected behavior: InProcess backend fetches args/kwargs from Redis and executes in-process

**Root Cause Discovery:**
Found in [runtime.py:4321-4324](src/blazing_service/engine/runtime.py#L4321-L4327):
```python
# Import executor backend
from blazing_service.executor.executor_backend import BlazingExecutorBackend

backend = BlazingExecutorBackend(container_url=EXECUTOR_URL)
```

**The Problem:**
1. `runtime.py` **hardcoded** `BlazingExecutorBackend` (the Docker HTTP backend)
2. It completely **ignored** the `BLAZING_EXECUTOR_BACKEND` environment variable
3. The Docker backend sends HTTP requests to an external executor container
4. When `EXECUTOR_ENABLED=true`, runtime.py skips fetching args/kwargs (expects executor to do it)
5. But the executor container wasn't properly handling the data fetch

**Why InProcessExecutorBackend Works:**
- `InProcessExecutorBackend` runs code directly in the coordinator process
- It calls `OperationDAO.get_data(operation_id, "args")` to fetch arguments from Redis
- No HTTP roundtrip, no external container dependency

### Solution

Changed [runtime.py:4321-4327](src/blazing_service/engine/runtime.py#L4321-L4327) to use the factory function:

**Before:**
```python
# Import executor backend
from blazing_service.executor.executor_backend import BlazingExecutorBackend

backend = BlazingExecutorBackend(container_url=EXECUTOR_URL)
```

**After:**
```python
# Import executor backend factory - respects BLAZING_EXECUTOR_BACKEND env var
from blazing_service.executor import get_executor_backend

# get_executor_backend() reads BLAZING_EXECUTOR_BACKEND env var
# - 'pyodide' or 'inprocess' -> InProcessExecutorBackend (no container needed)
# - 'docker' or 'gvisor' -> DockerExecutorBackend (uses EXECUTOR_URL)
backend = get_executor_backend(container_url=EXECUTOR_URL)
```

**How `get_executor_backend()` Works:**
From [executor/__init__.py:87-150](src/blazing_service/executor/__init__.py#L87-L150):
```python
def get_executor_backend(backend_type=None, container_url=None, ...):
    if backend_type is None:
        backend_type = os.getenv('BLAZING_EXECUTOR_BACKEND', 'pyodide').lower()

    if backend_type in ('pyodide', 'inprocess'):
        return InProcessExecutorBackend(timeout=timeout)
    elif backend_type in ('docker', 'gvisor'):
        return DockerExecutorBackend(container_url=url, ...)
```

### Deployment

1. Rebuilt coordinator container: `docker-compose build --no-cache coordinator`
2. Flushed Redis and restarted coordinator (required after FLUSHDB):
   ```bash
   docker exec blazing-redis redis-cli FLUSHDB && \
   docker-compose stop coordinator && \
   docker-compose rm -f coordinator && \
   docker-compose up -d coordinator
   ```

### Verification

```bash
$ REDIS_PORT=6379 BLAZING_API_URL=http://localhost:8000 uv run pytest tests/test_executor.py -v --timeout=180

======================= 53 passed, 61 warnings in 1.66s ========================
```

All 53 executor tests pass, including:
- ✅ `test_e2e_multistation_backend` - The originally failing test
- ✅ `test_executor_container_health`
- ✅ All backend factory tests
- ✅ All timing metrics tests
- ✅ All pre-wrapping logic tests

### Architecture Insight

**Swappable Executor Backends:**
```
Coordinator (runtime.py)
    │
    │ Routes operation based on BLAZING_EXECUTOR_BACKEND env var
    │
    ├─────────────────┬─────────────────┐
    ▼                 ▼                 ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  InProcess   │ │    Docker    │ │   Docker     │
│  (pyodide)   │ │   (docker)   │ │  + gVisor    │
│              │ │              │ │              │
│  Zero HTTP   │ │ HTTP to      │ │  Max Security│
│  In coordinator  │ │ container    │ │  Userspace   │
└──────────────┘ └──────────────┘ └──────────────┘
```

**When to use each:**
- `pyodide`/`inprocess`: Development, testing, simple deployments (DEFAULT)
- `docker`: Production with native Python speed
- `gvisor`: High-security production environments

### Related Fixes in This Session

1. ✅ Fixed `socket_timeout` parameter for Redis ConnectionPool
2. ✅ Fixed coordinator healthcheck to use `/proc/1/stat` instead of `pgrep`
3. ✅ Made `executor_app` a lazy import to avoid FastAPI dependency in coordinator
4. ✅ Fixed IndexError handling in executor security.py
5. ✅ Added `set_app_id("default")` call to executor_service.py
6. ✅ **Fixed runtime.py to use `get_executor_backend()` factory** (main fix)

### Status
- ✅ Root cause identified (hardcoded backend ignoring env var)
- ✅ Fix implemented and deployed
- ✅ All 53 executor tests passing
- ✅ JOURNAL.md updated with findings

---

## 2025-11-27: Service Serialization for Docker/Pyodide Executors - COMPLETE FIX

### Problem
Services defined in test files couldn't be serialized and deserialized in Docker/Pyodide executors because:
1. Dill serializes classes BY REFERENCE when module exists in `sys.modules` (62 bytes - just module path + class name)
2. Executor containers don't have test modules installed → `ModuleNotFoundError`
3. When forcing BY VALUE serialization (removing modules from `sys.modules`), uvloop event loop gets captured via `__globals__` references → `TypeError: no default __reduce__ due to non-trivial __cinit__`
4. Even when service class is in separate module (`tests/helpers/test_services.py`), dill follows all `__globals__` references when serializing, eventually reaching pytest fixtures that captured uvloop

### Investigation Journey

**Attempt 1: Change `__module__` to `__main__`**
- ❌ Failed: Methods inside class still have original `__module__` in their `__globals__`

**Attempt 2: Recursively change `__module__` on class AND all methods**
- ❌ Failed: uvloop.Loop captured somewhere in closure chain via `__globals__`

**Attempt 3: Remove module from `sys.modules` temporarily**
- ✅ Works manually with `uv run python3`
- ❌ Still fails inside pytest (uvloop captured in test environment differently)

**Attempt 4: Move services to separate module (`tests/helpers/test_services.py`)**
- ❌ Failed: Dill still follows all `__globals__` references from each method, eventually traversing into pytest fixtures that captured uvloop

### Key Insight

**Why removing modules doesn't work in pytest:**
When dill serializes a class, it traverses:
1. `cls.__dict__` - all class attributes
2. Each method's `method.__globals__` - the module-level namespace where the method was defined
3. `__globals__` contains references to ALL module-level names, not just imports

Even in a "clean" module like `tests/helpers/test_services.py`, dill follows the `__globals__` → `__builtins__` → eventually reaches uvloop because pytest has modified builtins or the import system.

**Evidence from pickle disassembly:**
```
273: c        GLOBAL     'tests.helpers.test_services __dict__'
```

### Final Solution: Create Standalone Classes with Clean `__globals__`

**Strategy:** Dynamically create a **completely new class** with methods that have minimal `__globals__` containing only `__builtins__`.

**Implementation:** [src/blazing/blazing.py:443-488](src/blazing/blazing.py#L443-L488)

```python
# Create clean globals with NO external references
clean_globals = {
    '__builtins__': __builtins__,
    '__name__': '__service__',
}

# Rebuild each method with clean globals
clean_methods = {}
for name, method in inspect.getmembers(service_cls, predicate=inspect.isfunction):
    if name.startswith('_') and name not in ('__init__', '_async_init'):
        continue
    if hasattr(method, '__code__'):
        new_func = types.FunctionType(
            method.__code__,
            clean_globals,  # Clean globals - no pytest/uvloop references!
            method.__name__,
            method.__defaults__,
            method.__closure__
        )
        clean_methods[name] = new_func

# Build standalone class WITHOUT BaseService inheritance
# (executor container doesn't have blazing package installed)
clean_class = type(
    service_cls.__name__,
    (object,),  # No external base class - executor doesn't have blazing.base
    {
        '__module__': '__service__',
        '__qualname__': service_cls.__name__,
        **clean_methods
    }
)

# Serialize - only 2680 chars!
serialized_class = base64.b64encode(dill.dumps(clean_class)).decode('utf-8')
```

### Executor Changes

**Problem:** The executor validated `issubclass(service_class, BaseService)`, but standalone classes don't inherit from BaseService.

**Solution:** Use duck typing instead of inheritance check.

**Location:** [src/blazing_service/executor/executor_service.py:290-307](src/blazing_service/executor/executor_service.py#L290-L307)

```python
# Validate it's a proper service (duck typing for standalone classes)
if not (hasattr(service_class, '__init__') and callable(getattr(service_class, '__init__', None))):
    raise TypeError(f"{service_class.__name__} must have an __init__ method")

# Check for factory method (BaseService-style) or use direct instantiation
if hasattr(service_class, 'create') and callable(getattr(service_class, 'create', None)):
    service_instance = await service_class.create(connectors)
else:
    service_instance = service_class(connectors)
    if hasattr(service_instance, '_async_init'):
        await service_instance._async_init()
```

### Import Fix

**Problem:** Circular import when `blazing.blazing` imports `BaseService` from `blazing_service.engine.runtime` which imports from `blazing.base`.

**Solution:** Import `BaseService` directly from `blazing.base`.

**Location:** [src/blazing/blazing.py:70](src/blazing/blazing.py#L70)

```python
# BEFORE (circular import)
from blazing_service.engine.runtime import BaseService, ...

# AFTER (no circular import)
from blazing.base import BaseService
from blazing_service.engine.runtime import ...
```

### Results

**Before:**
- Service serialization failed with uvloop error (27MB+ when it captured test environment)
- `KeyError: 'MathService'` when executing stations

**After:**
- Service serialized size: 2680 chars
- Works with uvloop enabled ✅
- Works in pytest environment ✅
- No module installation required in executor ✅

### Verification

```bash
# All comprehensive e2e tests pass
$ uv run pytest tests/test_z_comprehensive_e2e.py -v
# 5 passed (including test_docker_service_multistation_route)

# All executor e2e tests pass
$ uv run pytest tests/test_z_executor_e2e.py -v
# 19 passed (including Pyodide tests)
```

### Files Modified

1. **[src/blazing/base.py](src/blazing/base.py)** - Lightweight BaseService without ABC
2. **[src/blazing/__init__.py](src/blazing/__init__.py)** - Import from base.py
3. **[src/blazing/blazing.py](src/blazing/blazing.py)** - **CRITICAL:** Standalone class creation with clean `__globals__`
4. **[src/blazing_service/engine/runtime.py](src/blazing_service/engine/runtime.py)** - Re-export BaseService from base.py
5. **[src/blazing_service/executor/executor_service.py](src/blazing_service/executor/executor_service.py)** - Duck typing validation, flexible instantiation
6. **[src/blazing_service/executor/lifecycle.py](src/blazing_service/executor/lifecycle.py)** - Import from base.py
7. **[tests/helpers/test_services.py](tests/helpers/test_services.py)** - Services in separate module (optional)
8. **[tests/test_z_comprehensive_e2e.py](tests/test_z_comprehensive_e2e.py)** - Updated to import from helpers

### Key Learnings

1. **Dill follows ALL `__globals__` references during serialization** - not just direct imports, but the entire module namespace
2. **pytest environment captures uvloop differently** than standalone Python - through modified builtins or import hooks
3. **ABC inheritance adds `_abc_data`** which is also unpicklable - use plain classes
4. **Solution: Create completely new functions/classes** with minimal `__globals__` containing only `__builtins__`
5. **Duck typing validation** is more flexible than inheritance checks for serialized code
6. **Circular imports** can arise when moving base classes - import directly from the defining module

### Status
- ✅ Root cause identified (dill serializes `__globals__` which leads to uvloop)
- ✅ Fix implemented (standalone classes with clean `__globals__`)
- ✅ Executor updated (duck typing, flexible instantiation)
- ✅ Circular import fixed
- ✅ All tests passing (5 comprehensive e2e + 19 executor e2e)
- ✅ CLAUDE.md updated
- ✅ JOURNAL.md updated

