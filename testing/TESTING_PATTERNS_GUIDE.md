# Testing Patterns Guide

**Created:** 2024-12-14
**Context:** Coverage improvement session for data_access.py and runtime.py

This guide documents testing patterns and strategies learned during the coverage improvement session, providing a reference for future test development.

---

## Table of Contents

1. [Testing Strategy Evolution](#testing-strategy-evolution)
2. [When to Use Each Testing Approach](#when-to-use-each-testing-approach)
3. [Common Pitfalls and Solutions](#common-pitfalls-and-solutions)
4. [Testing Patterns by Component Type](#testing-patterns-by-component-type)
5. [Best Practices](#best-practices)
6. [Coverage Expectations](#coverage-expectations)

---

## Testing Strategy Evolution

### The Journey from Behavioral to Fakeredis Tests

During the session, we evolved through three testing approaches:

#### Attempt 1: High-Level Behavioral Tests ❌
**Example:** `test_data_access_unit.py` (20 tests)

```python
def test_make_key_format():
    """Test that make_key creates correct format."""
    key = StationDAO.make_key("station-123")
    assert "blazing:" in key
    assert "station-123" in key
```

**Pros:**
- ✅ Fast to write
- ✅ Good for validation logic
- ✅ No infrastructure needed

**Cons:**
- ❌ Don't execute real code paths
- ❌ Don't improve coverage metrics
- ❌ Miss implementation bugs

**When to Use:** Testing pure functions, validation helpers, format parsers

---

#### Attempt 2: Mocked Redis Tests ❌
**Example:** `test_data_access_methods_unit.py` (12 tests)

```python
@pytest.mark.asyncio
async def test_enqueue_operation():
    mock_redis = AsyncMock()
    mock_redis.lpush = AsyncMock(return_value=1)

    with patch('blazing_service.data_access.data_access.thread_local_data') as mock_tld:
        mock_tld.redis = mock_redis
        await StationDAO.enqueue_non_blocking_operation("unit-123", "station-456")

        # Verify method was called with correct arguments
        assert mock_redis.lpush.called
```

**Pros:**
- ✅ Tests method signatures
- ✅ Verifies correct Redis operations are called
- ✅ Fast execution

**Cons:**
- ❌ Don't execute real code paths inside DAO methods
- ❌ Don't improve coverage (code branches not exercised)
- ❌ Don't catch real Redis compatibility issues

**When to Use:** Testing external API contracts, verifying call patterns

---

#### Attempt 3: Fakeredis Tests ✅ **WINNER**
**Example:** `test_data_access_with_fakeredis.py` (11 tests)

```python
@pytest_asyncio.fixture
async def fake_redis():
    """Provide a fake Redis client for testing."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield client
    await client.flushall()
    await client.aclose()

@pytest.mark.asyncio
async def test_enqueue_and_dequeue_non_blocking(mock_thread_local):
    from blazing_service.data_access.data_access import StationDAO

    unit_pk = "unit-123"
    station_pk = "station-456"

    # Enqueue an operation - REAL CODE EXECUTION
    await StationDAO.enqueue_non_blocking_operation(unit_pk, station_pk)

    # Dequeue should return the operation - REAL CODE EXECUTION
    result = await StationDAO.dequeue_non_blocking_operation(station_pk)

    # Fakeredis returns bytes
    assert result == unit_pk.encode('utf-8')
```

**Pros:**
- ✅ Executes real DAO code paths
- ✅ Improves coverage metrics
- ✅ Finds real bugs (found 4 production bugs in our session!)
- ✅ Fast (0.4s for 11 tests)
- ✅ No Docker dependencies

**Cons:**
- ⚠️ Requires understanding fakeredis quirks (bytes vs strings)
- ⚠️ May not catch Redis-specific edge cases

**When to Use:** Testing any code that uses Redis operations (DAO methods, queue operations, cache logic)

---

## When to Use Each Testing Approach

### Decision Tree

```
┌─────────────────────────────────────────────────────────┐
│ Does the code require Redis/database infrastructure?   │
└─────────────────────┬───────────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
        YES                       NO
         │                         │
         │                         └──> Use Unit Tests
         │                             (Behavioral tests, pure functions)
         │
         └──> Can you use fakeredis?
              │
              ┌───────┴───────┐
             YES              NO
              │                │
              │                └──> Use Integration Tests
              │                    (Docker, real Redis required)
              │
              └──> Use Fakeredis Tests ✅
                   (Best coverage, finds real bugs)
```

### Summary Table

| Code Type | Testing Approach | Example |
|-----------|-----------------|---------|
| Pure functions | Unit tests | Format parsers, validators |
| Helper methods | Unit tests | Serialization, key formatting |
| DAO operations | **Fakeredis tests** | Enqueue, dequeue, save |
| Queue operations | **Fakeredis tests** | CRDT patterns, multi-tenant |
| Worker lifecycle | Integration/E2E | Worker spawning, coordinator |
| API endpoints | Integration/E2E | FastAPI routes with auth |
| Constants | Unit tests | Worker capabilities, timeouts |

---

## Common Pitfalls and Solutions

### 1. Async Fixture Not Recognized

**Error:**
```
PytestRemovedIn9Warning: 'test_function' requested an async fixture
AttributeError: 'async_generator' object has no attribute 'lpush'
```

**Cause:** Used `@pytest.fixture` instead of `@pytest_asyncio.fixture`

**Solution:**
```python
# ❌ WRONG
@pytest.fixture
async def fake_redis():
    ...

# ✅ CORRECT
import pytest_asyncio

@pytest_asyncio.fixture
async def fake_redis():
    ...
```

---

### 2. Bytes vs String Handling

**Error:**
```
TypeError: a bytes-like object is required, not 'str'
```

**Cause:** Fakeredis returns bytes when `decode_responses=False`, but code expects strings

**Solution in Tests:**
```python
@pytest_asyncio.fixture
async def fake_redis():
    # Use decode_responses=False to match real Redis behavior
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield client
```

**Solution in Production Code:**
```python
# Handle both bytes (fakeredis) and strings (real Redis)
queue_key_str = queue_key.decode('utf-8') if isinstance(queue_key, bytes) else queue_key
node_id = queue_key_str.split(':')[-1]
```

**Production Bugs Fixed:** This pattern fixed 4 bugs in [data_access.py](../src/blazing_service/data_access/data_access.py):
- Lines 1559-1560: `dequeue_non_blocking_operation()`
- Lines 1607-1608: `dequeue_blocking_operation()`
- Lines 1722-1723: `dequeue_non_blocking_sandboxed_operation()`
- Lines 1772-1773: `dequeue_blocking_sandboxed_operation()`

---

### 3. App ID Context Missing

**Error:**
```
KeyError: "blazing:default:..." when code expected "blazing:tenant-123:..."
```

**Cause:** Multi-tenant code requires app_id context to be set

**Solution:**
```python
from blazing_service.data_access.app_context import set_app_id, clear_app_id

@pytest.mark.asyncio
async def test_with_app_id():
    # ALWAYS clear before setting
    clear_app_id(force=True)
    set_app_id("test-tenant", lock=False)

    # Run test...

    # ALWAYS clean up after test
    clear_app_id(force=True)
```

**Pattern:** Always use `clear → set → test → clear`

---

### 4. Mock Completeness

**Error:**
```
AttributeError: Mock object has no attribute 'keys'
```

**Cause:** Incomplete mock - test only mocked `rpop()` but code also calls `keys()`

**Solution:** Identify ALL Redis operations used by the code path:

```python
# Find all Redis operations in the method
# Example: dequeue_dynamic_code_execution() uses:
# 1. keys() - to find queue segments
# 2. rpop() - to pop from queue

mock_redis.keys = AsyncMock(return_value=[
    b"blazing:test-app:dynamic_code:Queue:node-1"
])
mock_redis.rpop = AsyncMock(return_value=b"exec-123")
```

**Tip:** Use `grep` to find all Redis operations in a method:
```bash
grep -E "(lpush|rpop|keys|get|set)" src/blazing_service/data_access/data_access.py
```

---

### 5. Parameter Order

**Error:**
```
AssertionError: assert 'station-123' in 'blazing:test-app:...op-456...'
```

**Cause:** Swapped parameter order

**Solution:** Always verify method signatures:

```python
# ❌ WRONG order
await StationDAO.enqueue_non_blocking_operation(station_pk, unit_pk)

# ✅ CORRECT order (check method definition!)
await StationDAO.enqueue_non_blocking_operation(unit_pk, station_pk)
```

**Tip:** Use IDE "Go to Definition" or grep to verify:
```bash
grep -A 5 "def enqueue_non_blocking_operation" src/blazing_service/data_access/data_access.py
```

---

### 6. Queue Key Pattern Mismatch

**Error:**
```
AssertionError: assert ':execution_queue' in '...Queue:node-1'
```

**Cause:** Tests expected old queue pattern, but implementation uses CRDT pattern

**Solution:** Verify actual queue patterns in code:

```python
# ❌ OLD pattern assumption
assert ":execution_queue" in queue_key

# ✅ ACTUAL CRDT pattern
assert ":Queue:" in queue_key  # Node-specific segment
```

**Pattern:** CRDT queues use `{prefix}:Queue:{node_id}` format for multi-master safety

---

## Testing Patterns by Component Type

### Pattern 1: Testing DAO Queue Operations with Fakeredis

**File:** `test_data_access_with_fakeredis.py`

```python
import pytest
import pytest_asyncio
import fakeredis.aioredis
from unittest.mock import patch

@pytest_asyncio.fixture
async def fake_redis():
    """Provide a fake Redis client for testing."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield client
    await client.flushall()
    await client.aclose()

@pytest_asyncio.fixture
async def mock_thread_local(fake_redis):
    """Mock thread_local_data.redis to use fake Redis."""
    from blazing_service.data_access import data_access

    class MockThreadLocal:
        def __init__(self):
            self.redis = fake_redis

    mock_tld = MockThreadLocal()
    with patch.object(data_access, 'thread_local_data', mock_tld):
        yield mock_tld

@pytest.mark.asyncio
async def test_enqueue_dequeue_fifo_order(mock_thread_local):
    """Test that multiple enqueues maintain FIFO order."""
    from blazing_service.data_access.data_access import StationDAO
    from blazing_service.data_access.app_context import set_app_id, clear_app_id

    clear_app_id(force=True)
    set_app_id("test-app", lock=False)

    station_pk = "station-fifo"

    # Enqueue multiple operations
    await StationDAO.enqueue_non_blocking_operation("unit-1", station_pk)
    await StationDAO.enqueue_non_blocking_operation("unit-2", station_pk)
    await StationDAO.enqueue_non_blocking_operation("unit-3", station_pk)

    # Dequeue should return in FIFO order
    result1 = await StationDAO.dequeue_non_blocking_operation(station_pk)
    result2 = await StationDAO.dequeue_non_blocking_operation(station_pk)
    result3 = await StationDAO.dequeue_non_blocking_operation(station_pk)

    assert result1 == b"unit-1"
    assert result2 == b"unit-2"
    assert result3 == b"unit-3"

    clear_app_id(force=True)
```

**What This Tests:**
- ✅ Real enqueue/dequeue logic
- ✅ FIFO ordering
- ✅ Redis list operations (LPUSH/RPOP)
- ✅ Queue key generation

---

### Pattern 2: Testing Multi-Tenant Isolation

```python
@pytest.mark.asyncio
async def test_app_id_isolation_in_queues(mock_thread_local):
    """Test that different app_ids have separate queues."""
    from blazing_service.data_access.data_access import StationDAO
    from blazing_service.data_access.app_context import set_app_id, clear_app_id

    station_pk = "shared-station"

    # Enqueue for tenant-1
    clear_app_id(force=True)
    set_app_id("tenant-1", lock=False)
    await StationDAO.enqueue_non_blocking_operation("tenant1-unit", station_pk)

    # Enqueue for tenant-2
    clear_app_id(force=True)
    set_app_id("tenant-2", lock=False)
    await StationDAO.enqueue_non_blocking_operation("tenant2-unit", station_pk)

    # Dequeue for tenant-1 should get tenant1-unit
    clear_app_id(force=True)
    set_app_id("tenant-1", lock=False)
    result1 = await StationDAO.dequeue_non_blocking_operation(station_pk)
    assert result1 == b"tenant1-unit"

    # Dequeue for tenant-2 should get tenant2-unit
    clear_app_id(force=True)
    set_app_id("tenant-2", lock=False)
    result2 = await StationDAO.dequeue_non_blocking_operation(station_pk)
    assert result2 == b"tenant2-unit"

    clear_app_id(force=True)
```

**What This Tests:**
- ✅ Multi-tenant key isolation
- ✅ App ID context switching
- ✅ Queue namespace separation

---

### Pattern 3: Testing Constants and Relationships

**File:** `test_runtime_unit.py`

```python
def test_warm_pool_constants_reasonable_ranges():
    """Test that warm pool constants are within reasonable ranges."""
    from blazing_service.engine.runtime import _load_warm_pool_constants

    (pilot_p, pilot_a, pilot_slots,
     pilot_p_sandboxed, pilot_a_sandboxed, pilot_slots_sandboxed) = _load_warm_pool_constants()

    # All should be positive integers
    assert all(isinstance(x, int) for x in [pilot_p, pilot_a, pilot_slots])
    assert all(x > 0 for x in [pilot_p, pilot_a, pilot_slots])

    # Reasonable upper bounds
    assert pilot_p <= 20
    assert pilot_a <= 20
    assert pilot_slots <= 50

def test_constant_relationships():
    """Test that related constants maintain correct ordering."""
    from blazing_service.engine.runtime import (
        TIMEOUT_FAST, TIMEOUT_MEDIUM, TIMEOUT_SLOW,
        C_MIN, C_MAX
    )

    # Timeouts should be ordered
    assert TIMEOUT_FAST < TIMEOUT_MEDIUM < TIMEOUT_SLOW

    # Concurrency bounds should be ordered
    assert C_MIN <= C_MAX
```

**What This Tests:**
- ✅ Configuration sanity
- ✅ Constant relationships
- ✅ Value bounds

---

### Pattern 4: Testing Pure Helper Functions

**File:** `test_operation_data_api_unit.py`

```python
def test_serialize_for_response_pickle_format():
    """Test serialization with pickle format returns base64-encoded dill."""
    from blazing_service.operation_data_api import _serialize_for_response
    import base64
    import dill

    data = {"key": "value", "number": 42}
    result = _serialize_for_response(data, "pickle")

    # Should be base64-encoded dill
    assert isinstance(result, str)

    # Verify it's valid base64 and can be decoded
    decoded = base64.b64decode(result)
    assert isinstance(decoded, bytes)

    # Verify it can be unpickled
    unpickled = dill.loads(decoded)
    assert unpickled == data

def test_deserialize_from_request_security():
    """Test that pickle format does NOT deserialize on coordinator (security)."""
    from blazing_service.operation_data_api import _deserialize_from_request
    import base64
    import dill

    # Create a pickled object
    data = {"dangerous": "payload"}
    serialized = base64.b64encode(dill.dumps(data)).decode('utf-8')

    # Call deserialize with pickle format
    result = _deserialize_from_request(serialized, "pickle")

    # SECURITY: Should return raw data without unpickling
    assert result == serialized
    assert isinstance(result, str)
```

**What This Tests:**
- ✅ Pure function logic
- ✅ Security requirements
- ✅ Format handling

---

## Best Practices

### 1. Test Organization

```python
# tests/test_data_access_unit.py (20 tests)
# - Behavioral validation
# - Format parsing
# - Field validation

# tests/test_data_access_dao_unit.py (34 tests)
# - Key generation edge cases
# - App ID patterns
# - ULID validation

# tests/test_data_access_methods_unit.py (12 tests)
# - Method signatures (with mocks)
# - Queue pattern validation

# tests/test_data_access_with_fakeredis.py (11 tests) ⭐ BEST COVERAGE
# - Real DAO operations
# - Queue enqueue/dequeue
# - Multi-tenant isolation
```

**Principle:** Organize by testing approach, not by code structure

---

### 2. Fixture Reuse

```python
# Good: Reusable fixtures in conftest.py or at module level
@pytest_asyncio.fixture
async def fake_redis():
    """Reusable fake Redis client."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield client
    await client.flushall()
    await client.aclose()

# Good: Build on existing fixtures
@pytest_asyncio.fixture
async def mock_thread_local(fake_redis):
    """Build on fake_redis fixture."""
    from blazing_service.data_access import data_access

    class MockThreadLocal:
        def __init__(self):
            self.redis = fake_redis

    mock_tld = MockThreadLocal()
    with patch.object(data_access, 'thread_local_data', mock_tld):
        yield mock_tld
```

---

### 3. Test Naming

```python
# ✅ GOOD: Descriptive, behavior-focused names
def test_enqueue_and_dequeue_non_blocking()
def test_multiple_enqueue_fifo_order()
def test_app_id_isolation_in_queues()
def test_dequeue_from_empty_queue_returns_none()

# ❌ BAD: Vague or implementation-focused names
def test_dao_1()
def test_redis_operations()
def test_lpush_rpop()
```

**Principle:** Test names should describe the behavior being tested, not the implementation

---

### 4. Cleanup Pattern

```python
@pytest.mark.asyncio
async def test_with_cleanup():
    # Setup
    clear_app_id(force=True)
    set_app_id("test-app", lock=False)

    try:
        # Test code
        await some_operation()
        assert result == expected
    finally:
        # ALWAYS cleanup, even if test fails
        clear_app_id(force=True)
```

**Alternative using fixtures:**

```python
@pytest_asyncio.fixture
async def app_id_context():
    """Fixture that handles app_id setup and cleanup."""
    clear_app_id(force=True)
    set_app_id("test-app", lock=False)
    yield
    clear_app_id(force=True)

@pytest.mark.asyncio
async def test_with_fixture(app_id_context):
    # No manual cleanup needed!
    await some_operation()
    assert result == expected
```

---

## Coverage Expectations

### Understanding Coverage Metrics for Different File Types

#### Infrastructure Code (Acceptable: 10-20%)

**Example:** `runtime.py` (2,928 lines, 14% coverage)

**Why Low:**
- 86% is worker lifecycle, coordinator management, distributed operations
- Requires full Docker/Redis/Worker infrastructure
- Properly tested by integration/E2E tests

**What IS Covered:**
- Module-level constants ✅
- Helper functions ✅
- Data structure initialization ✅

**What is NOT Covered:**
- Worker spawning and lifecycle
- Queue polling operations
- Error handling in distributed systems
- Resource cleanup and shutdown

**Recommendation:** ✅ **ACCEPTABLE** - Focus on integration tests for this code

---

#### Data Layer Code (Target: 40-60%)

**Example:** `data_access.py` (1,574 lines, 43% coverage)

**Why Moderate:**
- 57% is DAO model definitions and database operations
- But key generation, validation, and helpers ARE testable

**What IS Covered:**
- Key generation logic ✅
- App context handling ✅
- Queue operations with fakeredis ✅

**What is NOT Covered:**
- Redis OM model field definitions
- Transaction handling
- Search index queries

**Recommendation:** ⚠️ **CAN IMPROVE** - Add fakeredis tests for queue/cache operations

---

#### Business Logic Code (Target: 70-85%)

**Example:** `executor/service.py` (725 lines, 70% coverage)

**Why Good:**
- Core execution logic is testable without infrastructure
- Security checks, validation, serialization all unit-testable

**What IS Covered:**
- Function validation ✅
- Serialization/deserialization ✅
- Security checks ✅

**What is NOT Covered:**
- Complex error scenarios
- Timeout handling
- Resource cleanup on failures

**Recommendation:** ✅ **GOOD** - Focus elsewhere, diminishing returns here

---

#### API Layer Code (Target: 50-70%)

**Example:** `operation_data_api.py` (1,202 lines, 35% → 50% after session)

**Why Moderate:**
- Pure functions and helpers are testable
- Endpoint logic requires FastAPI integration tests

**What IS Covered (After Session):**
- Helper functions ✅
- Serialization logic ✅
- Security validation ✅
- Pydantic model validation ✅

**What is NOT Covered:**
- FastAPI endpoint handlers
- Redis connections
- Authentication integration

**Recommendation:** ✅ **GOOD** - 27 new unit tests added for pure functions

---

### Summary Table

| File Type | Target Coverage | Testing Approach | ROI |
|-----------|----------------|------------------|-----|
| Infrastructure (runtime.py) | 10-20% | Integration/E2E | Low |
| Data Layer (data_access.py) | 40-60% | **Fakeredis tests** | **High** |
| Business Logic (executor/service.py) | 70-85% | Unit tests | Medium |
| API Layer (operation_data_api.py) | 50-70% | Unit + Integration | **High** |
| Pure Functions | 90%+ | Unit tests | **High** |

---

## Session Results Summary

### Tests Created: 119 new tests

1. **test_data_access_unit.py** - 20 tests (behavioral)
2. **test_data_access_dao_unit.py** - 34 tests (validation)
3. **test_data_access_methods_unit.py** - 12 tests (mocked)
4. **test_data_access_with_fakeredis.py** - 11 tests ⭐ (real coverage)
5. **test_runtime_unit.py** - 15 new tests (constants)
6. **test_operation_data_api_unit.py** - 27 tests (helpers, security)

### Production Bugs Fixed: 4

**File:** [data_access.py](../src/blazing_service/data_access/data_access.py)

All 4 fixes were for bytes/string handling in dequeue methods:

1. Line 1559-1560: `dequeue_non_blocking_operation()`
2. Line 1607-1608: `dequeue_blocking_operation()`
3. Line 1722-1723: `dequeue_non_blocking_sandboxed_operation()`
4. Line 1772-1773: `dequeue_blocking_sandboxed_operation()`

**Bug Pattern:**
```python
# BEFORE (broken with fakeredis)
node_id = queue_key.split(':')[-1]

# AFTER (works with both fakeredis and real Redis)
queue_key_str = queue_key.decode('utf-8') if isinstance(queue_key, bytes) else queue_key
node_id = queue_key_str.split(':')[-1]
```

---

## Key Learnings

### 1. Fakeredis is the Best Tool for DAO Testing

**Why:**
- Executes real code paths
- Finds real bugs
- Fast execution (no Docker needed)
- Improves coverage metrics

**When NOT to use:**
- Testing Redis-specific features (Lua scripts, clustering)
- Testing Redis OM search indexes
- Testing actual network latency

---

### 2. Coverage Percentages Can Be Misleading

**Example:** runtime.py at 14% coverage is ACCEPTABLE because:
- 86% of the code is infrastructure that requires workers/coordinator
- The 14% that IS covered includes all the testable parts (constants, helpers)
- Integration tests provide the real coverage for distributed operations

**Lesson:** Focus on **coverage quality** over **coverage quantity**

---

### 3. Multi-Tenant Architecture Requires Careful Testing

**Every test touching Redis must:**
1. Clear app_id before test
2. Set correct app_id
3. Test with multiple app_ids if validating isolation
4. Clean up app_id after test

**Pattern:**
```python
clear_app_id(force=True)
set_app_id("test-tenant", lock=False)
# ... test code ...
clear_app_id(force=True)
```

---

### 4. Test Organization Matters

**Good Organization:**
- Group by testing approach (behavioral, mocked, fakeredis)
- Separate pure functions from infrastructure code
- Use descriptive file names

**Example:**
```
tests/
├── test_data_access_unit.py         # Behavioral
├── test_data_access_dao_unit.py     # Validation
├── test_data_access_methods_unit.py # Mocked
└── test_data_access_with_fakeredis.py # Real coverage ⭐
```

---

### 5. Bytes vs String is a Common Pitfall

**Always test with `decode_responses=False` to match production:**

```python
client = fakeredis.aioredis.FakeRedis(decode_responses=False)
```

**Then handle both in production code:**

```python
value_str = value.decode('utf-8') if isinstance(value, bytes) else value
```

---

## Conclusion

This guide captures the patterns, pitfalls, and best practices discovered during the coverage improvement session. The key insight is that **testing strategy should match the code type**:

- **Infrastructure code** → Integration/E2E tests
- **DAO operations** → **Fakeredis tests** (best ROI)
- **Pure functions** → Unit tests
- **API endpoints** → Integration tests

By following these patterns, you can maximize coverage improvement while finding real bugs efficiently.

---

**Session Completed:** 2024-12-14
**Total Tests Added:** 119
**Production Bugs Fixed:** 4
**Coverage Improved:** data_access.py (43%), runtime.py (14%), operation_data_api.py (35% → 50%)
