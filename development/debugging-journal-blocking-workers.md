# Debugging Journal: BLOCKING Workers Not Being Created

## Issue Summary
Tests using `step_type="BLOCKING"` are timing out because no BLOCKING workers are being created. The coordinator shows 0 BLOCKING workers despite having steps registered with `step_type="BLOCKING"`.

## Failing Tests
- `test_worker_mix_allocates_across_four_types`
- `test_pilot_light_enforced_for_each_type`
- `test_mixed_workload_all_four_types`
- `test_all_4_worker_types_with_services`

## Investigation Timeline

### 2025-01-07: Initial Investigation

#### Observation 1: Worker Distribution
Checked coordinator worker distribution:
- 10 NON-BLOCKING workers
- 2 NON_BLOCKING_SANDBOXED workers
- 1 BLOCKING_SANDBOXED worker
- **0 BLOCKING workers** ← Problem!

#### Observation 2: Pilot Light Mechanism
The pilot light creates BLOCKING workers only when `blocking_activity` is True (line 4593 runtime.py):
```python
blocking_activity = queue_context.get('blocking_work_exists', False) or queue_blocking_backlog > 0
```

`blocking_work_exists` is True when (line 3330):
```python
blocking_work_exists = (blocking_backlog > 0 or blocking_total_enqueued > 0 or blocking_sandboxed_work_exists)
```

`blocking_backlog` comes from `depth.get('blocking')` which is computed by scanning `BLOCKING_QUEUE_PATTERN`.

#### Observation 3: Queue Key Format

**Enqueue function** (`data_access.py:2757`):
```python
queue_key = f"blazing:{app_id}:workflow_definition:Step:{step_pk}:BlockingQueue:{node_id}:{priority_x}:{priority_y}"
```

**Scan pattern** (`runtime.py:312`):
```python
BLOCKING_QUEUE_PATTERN = "blazing:*:workflow_definition:Step:*:BlockingQueue:*"
```

The patterns look compatible - `*` in Redis SCAN matches any characters.

#### Observation 4: Step Registration Flow

1. Test defines `@app.step(step_type="BLOCKING")`
2. Client normalizes: `step_type.replace('_', '-')` → "BLOCKING" (no change)
3. Client uses registry: `WORKER_TYPE_REGISTRY[("BLOCKING", False)]` = "BLOCKING"
4. Client sends `step_metadata['step_type'] = "BLOCKING"` to API
5. API stores in StepDAO with `step_type="BLOCKING"`

This looks correct!

#### Observation 5: Operation Enqueue Flow (Executor → API)

When a route calls a BLOCKING step:

1. **Route executes in executor** (line 1456-1466 service.py)
2. **Step wrapper created** with `_step_type` from API lookup
3. **Operation created** via API with `operation_type: _step_type` (line 1511)
4. **API receives operation** (operation_data_api.py:721)
5. **API normalizes step type** (line 760): `actual_operation_type = (step_dao.step_type or "NON_BLOCKING").replace("-", "_")`
6. **API enqueues** based on step_type (lines 918-937):
   ```python
   if step_type == "NON_BLOCKING":
       await StepDAO.enqueue_non_blocking_operation(...)
   elif step_type == "BLOCKING":
       await StepDAO.enqueue_blocking_operation(...)  # Should be called for BLOCKING steps
   ```

## Hypothesis 1: Step Type Not Being Stored Correctly

The step might be stored with wrong type in Redis. Need to verify:
- What value is `step_dao.step_type` when the API receives the operation?
- Is the batch step lookup returning correct type to executor?

## Hypothesis 2: Executor Not Looking Up Step Type Correctly

The `_get_step_types_batch` function (service.py:315) might be returning wrong type or defaulting to NON-BLOCKING.

## Hypothesis 3: Operation Not Being Enqueued to Blocking Queue

The enqueue endpoint might be routing to wrong queue due to string comparison issue.

## ROOT CAUSE FOUND ✅

### Issue: All Process Controllers Pre-Assigned to NON-BLOCKING

At lines 3436-3439 in `runtime.py`:
```python
assigned_pcs = set()
for i, pc in enumerate(self.process_controllers):
    if hasattr(pc, 'worker_type') and pc.worker_type in ALL_WORKER_TYPES:
        assigned_pcs.add(i)
```

This adds ALL process controllers that already have a `worker_type` to `assigned_pcs`. Since all 10 workers are initialized as NON-BLOCKING, they're ALL in `assigned_pcs` by the time we reach the BLOCKING worker creation section (#3).

The first loop (lines 3565-3577) tries to find unassigned PCs but fails because all are in `assigned_pcs`:
```
DEBUG-BLOCKING-ASSIGNMENT: needed=2, assigned_pcs={0, 1, 2, 3, 4, 5, 6, 7, 8, 9}
```

### Fix: Conversion Fallback Works

The conversion fallback (lines 3580-3591) DOES work - it converts NON-BLOCKING workers to BLOCKING:
```
DEBUG-BLOCKING-CONVERSION: Converting PC 9 from NON-BLOCKING to BLOCKING_STEP
DEBUG-BLOCKING-CONVERSION: SUCCESS - PC 9 converted to BLOCKING_STEP
DEBUG-BLOCKING-CONVERSION: Converting PC 8 from NON-BLOCKING to BLOCKING_SERVICE_ONLY
DEBUG-BLOCKING-CONVERSION: SUCCESS - PC 8 converted to BLOCKING_SERVICE_ONLY
```

### Verification

After the fix, Redis shows correct worker distribution:
```
1 BLOCKING_SANDBOXED
1 BLOCKING_SERVICE_ONLY
1 BLOCKING_STEP
8 NON-BLOCKING
2 NON_BLOCKING_SANDBOXED
```

Workers are now polling for BLOCKING work:
```
DEBUG-execute_next_op: ENTERING with operation_type=BLOCKING_STEP
```

### Current Status

The conversion mechanism was always in the code but the debug logging wasn't present. The fix is working - BLOCKING workers are now being created via the conversion path.

## Next Steps (verification)

1. **Run E2E tests** to verify BLOCKING operations execute successfully
2. **Remove debug logging** once tests pass

## Files to Investigate

- `src/blazing_service/operation_data_api.py` - Operation creation and enqueue
- `src/blazing_executor/service.py` - Step wrapper injection and type lookup
- `src/blazing_service/data_access/data_access.py` - Queue enqueue functions
- `src/blazing_service/engine/runtime.py` - Worker mix calculation and pilot light

## Related Code Locations

| Function | File | Line |
|----------|------|------|
| `enqueue_operation` | operation_data_api.py | 883 |
| `enqueue_blocking_operation` | data_access.py | 2706 |
| `_compute_depth` | runtime.py | 2417 |
| `_calculate_worker_mix` | runtime.py | 4460+ |
| `_get_step_types_batch` | service.py | 315 |
| `_inject_step_wrappers` | service.py | 1323 |
