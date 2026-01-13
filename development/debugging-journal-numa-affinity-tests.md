# NUMA/CPU Affinity Test Failures - Debugging Journal

**Date:** 2025-12-23
**Status:** RESOLVED ✅

## Overview

Three tests were failing due to a mismatch between expected CPU assignments and the actual behavior of the reserved core logic.

## Root Cause

The CPU affinity code now implements **reserved core support**:

- `CORE_RESERVED_SHARED_COUNT` (default=1) reserves cores 0..N-1 for system/API processes
- Workers are assigned to cores starting from the reserved count
- Example with 8 cores and `CORE_RESERVED_SHARED_COUNT=1`:
  - Reserved: core 0 (for API/system)
  - Available for workers: cores 1-7
  - Worker 0 → core 1 (not core 0!)
  - Worker 6 → core 7
  - Worker 7 → core 1 (wraps around available cores, not total cores)

The tests were written before this reserved core logic was added and expect the **old behavior**:
- Worker 0 → core 0
- Worker N → core N % total_cores

## Failing Tests

### 1. `test_get_worker_cpu_fallback_on_empty_node`

**File:** `tests/test_numa_affinity.py:261-273`

**Error:**
```
assert cpu == 5 % 8
E   assert 6 == (5 % 8)
```

**Expected:** Worker 5 → CPU 5 (old behavior: `worker_id % cpu_count`)
**Actual:** Worker 5 → CPU 6 (new behavior: `available_cores[worker_id % len(available_cores)]` where available = [1,2,3,4,5,6,7])

**Why:** With 8 cores and 1 reserved, available cores are [1,2,3,4,5,6,7] (7 cores).
Worker 5 → `available[5 % 7]` = `available[5]` = core 6

### 2. `test_setup_worker_single_node_uses_simple_affinity`

**File:** `tests/test_numa_affinity.py:362-384`

**Error:**
```
assert result['pinned_cpu'] == 2
E   assert 3 == 2
```

**Expected:** Worker 2 → CPU 2
**Actual:** Worker 2 → CPU 3 (because core 0 is reserved, so worker 2 maps to available[2] = core 3)

### 3. `test_round_robin_strategy`

**File:** `tests/test_pact_affinity.py:127-143`

**Error:**
```
assert call[0][1] == {expected_cpu}
E   AssertionError: assert {1} == {0}
```

**Expected:** Worker 0 → CPU 0, Worker 1 → CPU 1, etc.
**Actual:** Worker 0 → CPU 1, Worker 1 → CPU 2, etc. (due to reserved core 0)

## Solution

The fix was to mock `get_reserved_core_count()` to return 0 in these specific tests, preserving the original test logic without requiring recalculation of expected values.

**Key Insight:** Environment variable patching (`patch.dict(os.environ, ...)`) doesn't work because the value is imported at module load time. Instead, we must patch the function that reads the configuration:

```python
# This does NOT work (value already imported):
with patch.dict(os.environ, {'CORE_RESERVED_SHARED_COUNT': '0'}):
    ...

# This WORKS (patches the function that returns the value):
with patch('blazing_service.numa_affinity.get_reserved_core_count', return_value=0):
    ...
```

## Files Modified

- `tests/test_numa_affinity.py` - Lines 268-273, 366-384
- `tests/test_pact_affinity.py` - Lines 131-143, 148-156, 425-431, 533-540

## Verification

All 6 tests now pass:

```
tests/test_numa_affinity.py::TestNUMAAffinity::test_get_worker_cpu_fallback_on_empty_node PASSED
tests/test_numa_affinity.py::TestNUMAManager::test_setup_worker_single_node_uses_simple_affinity PASSED
tests/test_pact_affinity.py::TestSetCpuAffinity::test_round_robin_strategy PASSED
tests/test_pact_affinity.py::TestSetCpuAffinity::test_auto_detect_cpu_count PASSED
tests/test_pact_affinity.py::TestGetNumaAwareCpu::test_single_node_fallback PASSED
tests/test_pact_affinity.py::TestAffinityEdgeCases::test_large_worker_index PASSED
```
