# Testing Phases 1 & 2: Depth Tracking & Metrics

**Status:** In Progress
**Date:** 2026-01-02
**Test Files Created:** 3
**Total Tests Created:** 50 (of 135 planned)

---

## Test Files Created

### 1. `tests/unit/test_depth_tracking_schema.py` ✅
**Tests:** 15 (complete)
**Purpose:** Schema validation for depth tracking fields

**Coverage:**
- Schema field presence and types
- Default values
- Serialization/deserialization
- Backward compatibility with old operations
- Edge cases (Unicode, special characters, large values)
- Redis round-trip preservation
- OperationDAO alias validation

### 2. `tests/unit/test_depth_statistics.py` ✅
**Tests:** 25 (complete)
**Purpose:** Depth statistics collection logic

**Coverage:**
- Empty queue returns zeros
- Single/multiple operation stats
- Max/P95/Avg calculation accuracy
- Status filtering (READY/PENDING/IN_PROGRESS only)
- Multi-tenant filtering
- Malformed JSON handling
- Performance (100, 1000 operations)
- Feature flag behavior

### 3. `tests/unit/test_depth_metrics_api.py` ✅
**Tests:** 10 (complete)
**Purpose:** Depth metrics API endpoint

**Coverage:**
- HTTP 200 response
- Response model validation
- Authentication/authorization
- Error handling
- JSON serialization
- Response time (<500ms)
- All worker types present

---

## Test Execution Commands

### Run All Depth Tests
```bash
# All depth-related tests
uv run pytest tests/unit/test_depth_tracking_schema.py \
              tests/unit/test_depth_statistics.py \
              tests/unit/test_depth_metrics_api.py \
              -xvs

# With coverage
uv run pytest tests/unit/test_depth_*.py --cov=src/blazing_service --cov-report=html
```

### Run Individual Test Suites
```bash
# Schema tests only
uv run pytest tests/unit/test_depth_tracking_schema.py -xvs

# Statistics tests only
uv run pytest tests/unit/test_depth_statistics.py -xvs

# API tests only
uv run pytest tests/unit/test_depth_metrics_api.py -xvs
```

### Run Specific Tests
```bash
# Single test
uv run pytest tests/unit/test_depth_tracking_schema.py::TestDepthTrackingSchema::test_schema_has_depth_fields -xvs

# Pattern matching
uv run pytest tests/unit/test_depth_*.py -k "depth_zero" -xvs
```

---

## Test Database Setup Pattern

All tests follow this pattern:

```python
class TestDepthFeature:
    """Test suite for depth feature."""

    def _setup_database(self):
        """Setup database connection before each test."""
        from aredis_om import get_redis_connection
        StepRunDAO.Meta.database = get_redis_connection()
        OperationDAO.Meta.database = get_redis_connection()

    @pytest.mark.asyncio
    async def test_something(self, docker_infrastructure):
        """Test description."""
        self._setup_database()  # Always call first

        # Test code here...
```

**Why This Pattern:**
- Uses `aredis_om.get_redis_connection()` (standard method)
- Matches existing test patterns in codebase
- Works with docker_infrastructure fixture
- Avoids async fixture issues

---

## Current Status

### Tests Created: 50 / 135 (37%)

| Phase | Category | Tests Created | Tests Planned | Status |
|-------|----------|---------------|---------------|--------|
| **Phase 1** | Schema | 15 | 15 | ✅ Complete |
| **Phase 1** | Depth Calculation | 0 | 25 | ⏸️ Pending |
| **Phase 1** | Context Propagation | 0 | 20 | ⏸️ Pending |
| **Phase 1** | MAX_CALL_DEPTH | 0 | 10 | ⏸️ Pending |
| **Phase 1** | Backward Compat | 0 | 10 | ⏸️ Pending |
| **Phase 1** | Edge Cases | 0 | 10 | ⏸️ Pending |
| **Phase 2** | Stats Collection | 25 | 25 | ✅ Complete |
| **Phase 2** | Metrics API | 10 | 10 | ✅ Complete |
| **Phase 2** | Performance | 0 | 5 | ⏸️ Pending |
| **Phase 2** | Integration | 0 | 5 | ⏸️ Pending |

### Next Steps

1. **Fix and run schema tests** (15 tests)
2. **Fix and run statistics tests** (25 tests)
3. **Fix and run API tests** (10 tests)
4. **Create remaining Phase 1 tests** (60 tests)
5. **Create remaining Phase 2 tests** (10 tests)

---

## Expected Test Results

### Schema Tests (15 tests)
All should PASS - basic field validation, no complex logic

### Statistics Collection Tests (25 tests)
Most should PASS, may need fixes for:
- Coordinator access (app.state.coordinator)
- Multi-tenant filtering logic
- Performance thresholds

### API Tests (10 tests)
Most should PASS, may need fixes for:
- Rate limiting enforcement
- Response time thresholds
- Coordinator availability

---

## Known Issues

### Issue 1: Coordinator Access in Unit Tests
**Problem:** Unit tests may not have coordinator instance available
**Solution:** Skip tests if coordinator not available, or use integration tests

### Issue 2: Multi-Tenant Filtering
**Problem:** Tests run with single app_id ("default")
**Solution:** Mock multiple app_ids for filtering tests

### Issue 3: Performance Tests
**Problem:** Creating 1000+ operations may be slow in tests
**Solution:** Use smaller datasets or mark as slow tests

---

## Integration Test Plan (Future)

After unit tests pass, create integration tests:

```python
# tests/integration/test_depth_e2e.py

@pytest.mark.asyncio
async def test_depth_tracking_end_to_end(docker_infrastructure):
    """Test complete depth flow: client → API → coordinator → executor → stats."""
    app = Blazing(api_url="http://localhost:8000", api_token="test-token")

    @app.step
    async def level_3(x: int) -> int:
        return x + 1

    @app.step
    async def level_2(x: int, services=None) -> int:
        return await level_3(x, services=services)

    @app.step
    async def level_1(x: int, services=None) -> int:
        return await level_2(x, services=services)

    @app.route
    async def level_0(x: int, services=None):
        return await level_1(x, services=services)

    await app.publish()
    result = await app.run("level_0", x=1)

    assert result == 4  # 1+1+1+1

    # Verify depth stats show max_depth = 3
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/v1/metrics/depth",
            headers={"Authorization": "Bearer test-token"}
        )
        data = response.json()

        # Should show depth up to 3
        assert data['BLOCKING']['max'] >= 3 or data['NON_BLOCKING']['max'] >= 3
```

---

## Test Execution Log

### Run 1: Schema Tests
```
Date: 2026-01-02
Command: uv run pytest tests/unit/test_depth_tracking_schema.py -xvs
Status: Running...
```

**Expected Output:**
```
tests/unit/test_depth_tracking_schema.py::TestDepthTrackingSchema::test_schema_has_depth_fields PASSED
tests/unit/test_depth_tracking_schema.py::TestDepthTrackingSchema::test_default_values_correct PASSED
...
======================== 15 passed, XX warnings in YY.XXs ======================
```

---

## Coverage Goals

### Unit Test Coverage
- **Target:** 100% line coverage for new code
- **Files to Cover:**
  - `src/blazing_service/data_access/data_access.py` (depth fields)
  - `src/blazing_service/engine/runtime.py` (_collect_depth_statistics)
  - `src/blazing_service/server.py` (depth metrics endpoint)
  - `src/blazing_executor/service.py` (depth calculation in wrappers)
  - `src/blazing_service/executor/base.py` (depth parameters)

### Integration Test Coverage
- **Target:** 95% path coverage
- **Critical Paths:**
  - Client → API → OperationDAO (depth saved)
  - OperationDAO → Coordinator → Executor (depth propagated)
  - Executor → StepWrapper → ChildOperation (depth incremented)
  - Maintenance loop → Stats collection → API endpoint

---

## Success Criteria

### All Tests Must Pass
- ✅ 15 schema tests
- ✅ 25 statistics tests
- ✅ 10 API tests
- **Total: 50 tests passing**

### Performance Benchmarks
- Collection <100ms for 1,000 operations
- API response <500ms
- Zero impact on operation execution

### No Regressions
- All existing tests still pass
- No breaking changes
- Backward compatibility verified

---

**Document Version:** 1.0
**Last Updated:** 2026-01-02
**Status:** Tests created, execution in progress
