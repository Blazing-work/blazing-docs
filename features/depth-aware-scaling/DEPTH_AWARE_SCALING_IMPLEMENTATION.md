# Depth-Aware Dynamic Scaling Implementation Plan

**Version:** 1.0
**Date:** 2026-01-02
**Status:** Draft
**Owner:** Engineering Team

---

## Executive Summary

This document describes the implementation of **depth-aware dynamic scaling** for the Blazing workflow engine. The system will track call chain depth per operation, use depth statistics to calculate dynamic pilot light minimums, detect chokepoint scenarios (queue stalls), and make intelligent horizontal scaling decisions.

**Key Goals:**
1. **Prevent deadlocks** from deep recursive call chains
2. **Optimize resource allocation** based on actual call depth patterns
3. **Detect and resolve chokepoints** automatically
4. **Scale horizontally** when single-node capacity is exhausted
5. **Maintain 100% backward compatibility** with existing deployments

**Estimated Scope:**
- **Code Changes:** ~2,500 lines (net new)
- **Test Code:** ~15,000 lines (530 tests)
- **Timeline:** 12 weeks (6 phases)
- **Risk Level:** High (touches critical execution paths)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Schema Changes](#schema-changes)
3. [Implementation Phases](#implementation-phases)
4. [Test Plan](#test-plan)
5. [Deployment Strategy](#deployment-strategy)
6. [Rollback Plan](#rollback-plan)
7. [Success Metrics](#success-metrics)
8. [Risk Mitigation](#risk-mitigation)

---

## Architecture Overview

### Current System (Static Pilot Light)

```
┌─────────────────────────────────────────────────────────┐
│ Current: Static Pilot Light (Fixed Minimums)           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  BLOCKING:           2 workers (fixed)                  │
│  NON_BLOCKING:       3 workers (fixed)                  │
│  BLOCKING_SANDBOXED: 1 worker  (fixed)                  │
│  NON_BLOCKING_SANDBOXED: 2 workers (fixed)              │
│                                                         │
│  Total: 8 workers minimum regardless of depth          │
│                                                         │
│  Problem: Deep call chains (depth=20) can deadlock     │
│  with only 2 BLOCKING workers available                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### New System (Depth-Aware Dynamic)

```
┌─────────────────────────────────────────────────────────┐
│ New: Depth-Aware Dynamic Scaling                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. Track call depth per operation:                    │
│     - parent_operation_pk: "01ABC..."                  │
│     - call_depth: 15                                   │
│     - depth_by_worker_type: {"BLOCKING": 10, "NON": 5} │
│                                                         │
│  2. Collect depth statistics (every maintenance tick): │
│     - max_depth per worker type                        │
│     - p95_depth per worker type                        │
│     - avg_depth per worker type                        │
│                                                         │
│  3. Calculate dynamic minimums:                        │
│     min_workers = max(                                  │
│         max_depth + 1 (safety margin),                 │
│         static_pilot_light,                            │
│         +2 if queue growing (emergency buffer)         │
│     )                                                   │
│                                                         │
│  4. Detect chokepoints (stalls):                       │
│     - backlog > 0                                      │
│     - workers > 0                                       │
│     - delta_dequeued == 0 for 3+ ticks                 │
│                                                         │
│  5. Auto-resolution:                                   │
│     - Rebalance workers if depth < N                   │
│     - Scale horizontally if depth >= N                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Call Depth Propagation Flow

```
┌────────────────────────────────────────────────────────────────┐
│ Example: Route → Service → Station → Station Call Chain       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Client calls route (depth=0)                              │
│     ├─ operation_pk: "ROOT"                                   │
│     ├─ parent_operation_pk: ""                                │
│     ├─ call_depth: 0                                          │
│     └─ depth_by_worker_type: {"NON_BLOCKING": 0}              │
│                                                                │
│  2. Route calls service method (depth=1)                      │
│     ├─ operation_pk: "OP1"                                    │
│     ├─ parent_operation_pk: "ROOT"                            │
│     ├─ call_depth: 1                                          │
│     └─ depth_by_worker_type: {"NON_BLOCKING": 1}              │
│                                                                │
│  3. Service calls station A (depth=2)                         │
│     ├─ operation_pk: "OP2"                                    │
│     ├─ parent_operation_pk: "OP1"                             │
│     ├─ call_depth: 2                                          │
│     └─ depth_by_worker_type: {                                │
│           "NON_BLOCKING": 1,  # from parent                   │
│           "BLOCKING": 1        # current operation            │
│        }                                                       │
│                                                                │
│  4. Station A calls station B (depth=3)                       │
│     ├─ operation_pk: "OP3"                                    │
│     ├─ parent_operation_pk: "OP2"                             │
│     ├─ call_depth: 3                                          │
│     └─ depth_by_worker_type: {                                │
│           "NON_BLOCKING": 1,                                  │
│           "BLOCKING": 2        # incremented                  │
│        }                                                       │
│                                                                │
│  Result: System knows it needs:                               │
│    - At least 2 BLOCKING workers                              │
│    - At least 1 NON_BLOCKING worker                           │
│    - Plus safety margins (+1 each)                            │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Depth Statistics Collection

```python
# Maintenance loop (every ~5 seconds)
depth_stats = {
    'BLOCKING': {
        'max': 15,      # Maximum depth across all operations
        'p95': 12,      # 95th percentile
        'avg': 5.2,     # Average depth
        'count': 150    # Number of operations tracked
    },
    'NON_BLOCKING': {
        'max': 8,
        'p95': 6,
        'avg': 3.1,
        'count': 250
    },
    'BLOCKING_SANDBOXED': {...},
    'NON_BLOCKING_SANDBOXED': {...}
}
```

### Dynamic Minimum Calculation

```python
def calculate_depth_aware_minimums(depth_stats, queue_context):
    minimums = {}

    for worker_type in ['BLOCKING', 'NON_BLOCKING',
                        'BLOCKING_SANDBOXED', 'NON_BLOCKING_SANDBOXED']:
        # Get depth statistics
        max_depth = depth_stats[worker_type]['max']  # e.g., 15

        # Base minimum: max_depth + 1 (safety margin)
        min_workers = max_depth + 1  # = 16

        # Emergency buffer if queue growing
        if queue_is_growing(queue_context, worker_type):
            min_workers += 2  # = 18

        # Never go below static pilot light
        static_min = get_static_pilot_light(worker_type)  # e.g., 2
        min_workers = max(min_workers, static_min)  # = 18

        # Cap at 50% of total N (prevent starvation)
        max_allowed = N // 2  # e.g., 32 / 2 = 16
        min_workers = min(min_workers, max_allowed)  # = 16

        minimums[worker_type] = 16  # Final result

    return minimums
```

### Chokepoint Detection (Queue Stall)

```python
# Stall condition detection
def detect_stall(queue_context, worker_counts):
    for worker_type in WORKER_TYPES:
        backlog = queue_context[worker_type]['backlog']
        workers = worker_counts[worker_type]
        dequeued = queue_context[worker_type]['delta_dequeued']

        # CHOKEPOINT CONDITIONS (all must be true):
        # 1. Work exists (backlog > 0)
        # 2. Capacity exists (workers > 0)
        # 3. No progress (dequeued == 0)

        if backlog > 0 and workers > 0 and dequeued == 0:
            stall_tracker[worker_type]['ticks'] += 1

            if stall_tracker[worker_type]['ticks'] >= 3:
                # STALL DETECTED - trigger resolution
                return {
                    'stalled': True,
                    'worker_type': worker_type,
                    'backlog': backlog,
                    'workers': workers,
                    'ticks_stalled': stall_tracker[worker_type]['ticks'],
                    'severity': 'CRITICAL' if ticks >= 5 else 'WARNING'
                }
```

### Node Scaling Decision Logic

```python
def should_scale_nodes(depth_stats, stalls, queue_context, worker_counts):
    # TRIGGER 1: Cross-type deadlock (multiple types stalled)
    stalled_types = [wt for wt, s in stalls.items() if s['stalled']]
    if len(stalled_types) >= 2:
        return {
            'should_scale': True,
            'reason': 'cross_type_deadlock',
            'recommended_nodes': 1,
            'details': f"Types stalled: {stalled_types}"
        }

    # TRIGGER 2: Depth exhaustion (required workers > N)
    total_depth_required = sum(
        depth_stats[wt]['max'] + 1 for wt in WORKER_TYPES
    )
    if total_depth_required > N:
        nodes_needed = math.ceil(total_depth_required / N)
        return {
            'should_scale': True,
            'reason': 'depth_exhaustion',
            'recommended_nodes': nodes_needed - 1,  # Already have 1 node
            'details': f"Need {total_depth_required} workers, have {N}"
        }

    # TRIGGER 3: Saturation (utilization > 90% + high backlog)
    total_backlog = sum(q['backlog'] for q in queue_context.values())
    utilization = sum(worker_counts.values()) / N
    if utilization > 0.9 and total_backlog > MAX_CONCURRENT_TASKS:
        return {
            'should_scale': True,
            'reason': 'saturation',
            'recommended_nodes': 1,
            'details': f"Utilization {utilization:.0%}, backlog {total_backlog}"
        }

    # No scaling needed
    return {'should_scale': False, 'reason': 'rebalancing_sufficient'}
```

---

## Schema Changes

### 1. OperationDAO Additions

**File:** `src/blazing_service/data_access/data_access.py`

```python
class OperationDAO(HashModel):
    # ... existing fields ...

    # NEW FIELDS (v2.1.0)
    parent_operation_pk: str = Field(
        default="",
        index=False,
        description="Primary key of the parent operation that created this operation"
    )

    root_operation_pk: str = Field(
        default="",
        index=False,
        description="Primary key of the root operation (entry point of call chain)"
    )

    call_depth: int = Field(
        default=0,
        index=False,
        description="Depth in the call chain (0 = root, 1 = first child, etc.)"
    )

    depth_by_worker_type: str = Field(
        default="{}",
        index=False,
        description="JSON string mapping worker_type to depth count, e.g. '{\"BLOCKING\": 3, \"NON_BLOCKING\": 2}'"
    )

    class Meta:
        model_key_prefix = "blazing"
        database = thread_local_data.redis
```

**Migration Strategy:**
- Backward compatible: all new fields have defaults
- Existing operations will have `call_depth=0`, `parent_operation_pk=""`
- No data migration required (gradual adoption as new operations created)

### 2. New Configuration Constants

**File:** `src/blazing_service/worker_config.py`

```python
# Maximum recursion depth allowed (hard limit)
MAX_CALL_DEPTH = _env_int('MAX_CALL_DEPTH', 50)

# Depth-aware pilot light configuration
DEPTH_AWARE_PILOT_LIGHT_ENABLED = _env_bool('DEPTH_AWARE_PILOT_LIGHT', True)
DEPTH_SAFETY_MARGIN = _env_int('DEPTH_SAFETY_MARGIN', 1)  # +1 above max_depth
DEPTH_EMERGENCY_BUFFER = _env_int('DEPTH_EMERGENCY_BUFFER', 2)  # When queue growing

# Chokepoint detection configuration
STALL_DETECTION_ENABLED = _env_bool('STALL_DETECTION_ENABLED', True)
STALL_THRESHOLD_TICKS = _env_int('STALL_THRESHOLD_TICKS', 3)  # 3 ticks = ~15 seconds
STALL_CRITICAL_TICKS = _env_int('STALL_CRITICAL_TICKS', 5)

# Node scaling configuration
NODE_SCALING_ENABLED = _env_bool('NODE_SCALING_ENABLED', False)  # Feature flag
NODE_SCALING_WEBHOOK_URL = os.getenv('NODE_SCALING_WEBHOOK_URL', '')
NODE_SCALING_COOLDOWN_SECONDS = _env_int('NODE_SCALING_COOLDOWN_SECONDS', 300)
```

---

## Implementation Phases

### Phase 1: Schema Changes & Basic Depth Tracking (Week 1-2)

**Goal:** Add depth tracking infrastructure without changing behavior

**Tasks:**
1. Add new fields to OperationDAO schema
2. Implement depth calculation logic in executor step wrappers
3. Propagate depth context through operation creation
4. Add MAX_CALL_DEPTH enforcement (hard limit = 50)
5. Add depth logging for debugging

**Files Modified:**
- `src/blazing_service/data_access/data_access.py` - Schema
- `src/blazing_executor/service.py` - Step wrapper depth calculation
- `src/blazing_executor_pyodide/server.mjs` - Pyodide wrapper depth
- `src/blazing/blazing.py` - Client-side depth initialization
- `src/blazing_service/worker_config.py` - Constants

**Tests Required (80 tests):**
- Schema validation (15 tests)
- Depth calculation logic (25 tests)
- Context propagation (20 tests)
- MAX_CALL_DEPTH enforcement (10 tests)
- Backward compatibility (10 tests)

**Success Criteria:**
- ✓ All operations have depth fields populated
- ✓ Depth increments correctly through call chains
- ✓ MAX_CALL_DEPTH=50 enforced, raises RecursionError
- ✓ Zero regressions in existing tests
- ✓ Performance overhead <1% (measured via benchmark)

**Feature Flag:** `DEPTH_TRACKING_ENABLED=true` (default: true)

---

### Phase 2: Metrics & Observability (Week 3)

**Goal:** Collect and expose depth statistics

**Tasks:**
1. Implement `_collect_depth_statistics()` in maintenance loop
2. Add depth metrics to Prometheus export
3. Add depth visualization to dashboards
4. Add depth alerts (depth > threshold)
5. Add depth tracing in logs

**Files Modified:**
- `src/blazing_service/engine/runtime.py` - Stats collection
- `src/blazing_service/metrics.py` - Prometheus metrics
- `docs/monitoring.md` - Dashboard examples

**Tests Required (40 tests):**
- Stats collection logic (25 tests)
- Metrics export (10 tests)
- Performance (5 tests)

**New Metrics:**
```
# Gauge: Maximum depth per worker type
blazing_call_depth_max{worker_type="BLOCKING"} 15

# Gauge: P95 depth per worker type
blazing_call_depth_p95{worker_type="BLOCKING"} 12

# Gauge: Average depth per worker type
blazing_call_depth_avg{worker_type="BLOCKING"} 5.2

# Counter: Operations exceeding depth threshold
blazing_call_depth_threshold_exceeded_total{worker_type="BLOCKING"} 5

# Histogram: Depth distribution
blazing_call_depth_distribution{worker_type="BLOCKING", le="10"} 120
blazing_call_depth_distribution{worker_type="BLOCKING", le="20"} 145
blazing_call_depth_distribution{worker_type="BLOCKING", le="50"} 150
```

**Success Criteria:**
- ✓ Depth stats collected every maintenance tick (~5s)
- ✓ Stats accurate (matches actual operation depth)
- ✓ Stats collection <100ms for 10,000 operations
- ✓ Metrics visible in Grafana dashboards
- ✓ Alerts fire when depth exceeds thresholds

---

### Phase 3: Dynamic Pilot Light (Week 4-5)

**Goal:** Use depth stats to calculate dynamic worker minimums

**Tasks:**
1. Implement `_calculate_depth_aware_minimums()`
2. Integrate with `_calculate_worker_mix()`
3. Enforce dynamic minimums during worker creation
4. Add hysteresis for minimum changes (prevent oscillation)
5. Add depth minimum metadata to API responses

**Files Modified:**
- `src/blazing_service/engine/runtime.py` - Dynamic minimums
- `src/blazing_service/worker_mix_enhancements.py` - Hysteresis
- `src/blazing_service/server.py` - API metadata

**Tests Required (120 tests):**
- Minimum calculation (30 tests)
- Worker mix integration (40 tests)
- Hysteresis (20 tests)
- Edge cases (30 tests)

**Algorithm:**
```python
def _calculate_depth_aware_minimums(self, depth_stats, queue_context):
    minimums = {}

    for worker_type in WORKER_TYPES:
        # Base: max depth + safety margin
        max_depth = depth_stats.get(worker_type, {}).get('max', 0)
        min_workers = max_depth + DEPTH_SAFETY_MARGIN

        # Emergency buffer if queue growing
        if self._is_queue_growing(queue_context, worker_type):
            min_workers += DEPTH_EMERGENCY_BUFFER

        # Never below static pilot light
        static_min = self._get_static_pilot_light(worker_type)
        min_workers = max(min_workers, static_min)

        # Cap at 50% of N (prevent starvation)
        min_workers = min(min_workers, self.N // 2)

        minimums[worker_type] = min_workers

    return minimums
```

**Success Criteria:**
- ✓ Dynamic minimums calculated correctly
- ✓ Worker count increases when depth increases
- ✓ Worker count decreases when depth decreases (with hysteresis)
- ✓ Never deadlocks on deep call chains
- ✓ Resource usage optimized (fewer idle workers)

**Feature Flag:** `DEPTH_AWARE_PILOT_LIGHT_ENABLED=true`

---

### Phase 4: Chokepoint Detection (Week 6)

**Goal:** Detect when queues stall despite workers existing

**Tasks:**
1. Implement `_detect_queue_stalls()`
2. Add stall tracker (persistent across ticks)
3. Add stall severity classification (WARNING, CRITICAL)
4. Add stall metrics and alerts
5. Add stall logging with context

**Files Modified:**
- `src/blazing_service/engine/runtime.py` - Stall detection
- `src/blazing_service/metrics.py` - Stall metrics

**Tests Required (100 tests):**
- Stall detection logic (30 tests)
- Stall root cause (30 tests)
- Stall tracking (20 tests)
- Edge cases (20 tests)

**Stall Detection Algorithm:**
```python
def _detect_queue_stalls(self, queue_context, worker_counts):
    stalls = {}

    for worker_type in WORKER_TYPES:
        backlog = queue_context[worker_type]['backlog']
        workers = worker_counts[worker_type]
        dequeued = queue_context[worker_type]['delta_dequeued']

        # Stall conditions (all must be true)
        has_work = backlog > 0
        has_workers = workers > 0
        not_dequeuing = dequeued == 0

        if has_work and has_workers and not_dequeuing:
            self._stall_tracker[worker_type]['ticks'] += 1
            stalled = True
        else:
            self._stall_tracker[worker_type]['ticks'] = 0
            stalled = False

        stalls[worker_type] = {
            'stalled': stalled,
            'backlog': backlog,
            'workers': workers,
            'ticks_stalled': self._stall_tracker[worker_type]['ticks'],
            'severity': 'CRITICAL' if ticks >= 5 else 'WARNING'
        }

    return stalls
```

**New Metrics:**
```
# Gauge: Current stall status per worker type
blazing_queue_stalled{worker_type="BLOCKING"} 1  # 1=stalled, 0=ok

# Gauge: Stall duration in ticks
blazing_queue_stall_duration_ticks{worker_type="BLOCKING"} 7

# Counter: Total stalls detected
blazing_queue_stalls_total{worker_type="BLOCKING", severity="CRITICAL"} 3
```

**Success Criteria:**
- ✓ Stalls detected within 3 ticks (~15 seconds)
- ✓ No false positives (slow drain != stall)
- ✓ Stall root cause logged for debugging
- ✓ Alerts fire for CRITICAL stalls
- ✓ Stall data exported for analysis

**Feature Flag:** `STALL_DETECTION_ENABLED=true`

---

### Phase 5: Auto-Resolution (Week 7-8)

**Goal:** Automatically resolve stalls via rebalancing

**Tasks:**
1. Implement stall resolution logic
2. Integrate with worker mix calculation
3. Add emergency mode (bypass hysteresis on CRITICAL stalls)
4. Add resolution metrics
5. Add resolution logging

**Files Modified:**
- `src/blazing_service/engine/runtime.py` - Resolution logic
- `src/blazing_service/worker_mix_enhancements.py` - Emergency mode

**Tests Required (60 tests):**
- Resolution logic (30 tests)
- Integration with worker mix (20 tests)
- Edge cases (10 tests)

**Resolution Algorithm:**
```python
def _resolve_stalls(self, stalls, depth_stats, queue_context):
    for worker_type, stall_info in stalls.items():
        if not stall_info['stalled']:
            continue

        # Root cause analysis
        max_depth = depth_stats[worker_type]['max']
        current_workers = stall_info['workers']

        if max_depth >= current_workers:
            # CAUSE: Depth exhaustion
            # FIX: Increase workers to max_depth + safety margin
            recommended_workers = max_depth + DEPTH_SAFETY_MARGIN

            if recommended_workers > self.N:
                # Single node can't handle it → trigger node scaling
                self._trigger_node_scaling('depth_exhaustion', worker_type)
            else:
                # Rebalance within node
                self._force_worker_creation(worker_type, recommended_workers)

        elif stall_info['severity'] == 'CRITICAL':
            # CAUSE: Unknown (possibly deadlock, resource exhaustion)
            # FIX: Emergency intervention
            logger.critical(f"CRITICAL STALL: {worker_type}, investigating...")

            # Emergency: bypass hysteresis, force rebalancing
            self._emergency_rebalance(worker_type)
```

**Success Criteria:**
- ✓ 95% of stalls auto-resolved within 60 seconds
- ✓ No cascading failures from resolution attempts
- ✓ Resolution doesn't disrupt healthy operations
- ✓ Manual intervention needed <5% of time
- ✓ Resolution cost-effective (minimal resource waste)

---

### Phase 6: Node Scaling (Week 9-10)

**Goal:** Trigger horizontal scaling when single node exhausted

**Tasks:**
1. Implement `_should_scale_nodes()`
2. Add scaling decision metrics
3. Integrate with Kubernetes HPA / AWS Auto Scaling
4. Add scaling cooldown (prevent thrashing)
5. Add scaling documentation

**Files Modified:**
- `src/blazing_service/engine/runtime.py` - Scaling logic
- `src/blazing_service/scaling.py` - External integrations
- `docs/scaling.md` - Operator guide

**Tests Required (80 tests):**
- Scaling triggers (25 tests)
- Scaling calculations (25 tests)
- Integration tests (20 tests)
- Edge cases (10 tests)

**Scaling Decision Algorithm:**
```python
def _should_scale_nodes(self, depth_stats, stalls, queue_context, worker_counts):
    # TRIGGER 1: Cross-type deadlock
    stalled_types = [wt for wt, s in stalls.items() if s['stalled']]
    if len(stalled_types) >= 2:
        return {
            'should_scale': True,
            'reason': 'cross_type_deadlock',
            'recommended_nodes': 1
        }

    # TRIGGER 2: Depth exhaustion
    total_depth_required = sum(
        depth_stats[wt]['max'] + 1 for wt in WORKER_TYPES
    )
    if total_depth_required > self.N:
        nodes_needed = math.ceil(total_depth_required / self.N)
        return {
            'should_scale': True,
            'reason': 'depth_exhaustion',
            'recommended_nodes': nodes_needed - 1
        }

    # TRIGGER 3: Saturation
    total_backlog = sum(q['backlog'] for q in queue_context.values())
    utilization = sum(worker_counts.values()) / self.N
    if utilization > 0.9 and total_backlog > MAX_CONCURRENT_TASKS:
        return {
            'should_scale': True,
            'reason': 'saturation',
            'recommended_nodes': 1
        }

    return {'should_scale': False}
```

**Integration Options:**
1. **Kubernetes HPA:** POST to HPA API with desired replica count
2. **AWS Auto Scaling:** Update Auto Scaling Group desired capacity
3. **Webhook:** POST to custom endpoint with scaling recommendation
4. **Manual:** Log recommendation, operator scales manually

**Success Criteria:**
- ✓ Scaling triggered correctly (no false positives)
- ✓ Scaling recommendations accurate (right node count)
- ✓ Scaling cooldown prevents thrashing (5 min minimum)
- ✓ Integration with at least 2 platforms (K8s, AWS)
- ✓ Graceful degradation if scaling fails

**Feature Flag:** `NODE_SCALING_ENABLED=false` (default: off)

---

## Test Plan

### Test Coverage Summary

| Category | Unit | Integration | E2E | Total |
|----------|------|-------------|-----|-------|
| **Phase 1: Depth Tracking** | 60 | 20 | 10 | 90 |
| **Phase 2: Metrics** | 30 | 10 | 5 | 45 |
| **Phase 3: Dynamic Pilot Light** | 90 | 30 | 15 | 135 |
| **Phase 4: Chokepoint Detection** | 70 | 20 | 10 | 100 |
| **Phase 5: Auto-Resolution** | 40 | 15 | 10 | 65 |
| **Phase 6: Node Scaling** | 50 | 20 | 15 | 85 |
| **TOTAL** | **340** | **115** | **65** | **520** |

### Test Files Structure

```
tests/
├── unit/
│   ├── test_depth_tracking.py           (60 tests)
│   ├── test_depth_statistics.py         (30 tests)
│   ├── test_dynamic_pilot_light.py      (90 tests)
│   ├── test_chokepoint_detection.py     (70 tests)
│   ├── test_stall_resolution.py         (40 tests)
│   └── test_node_scaling.py             (50 tests)
│
├── integration/
│   ├── test_depth_integration.py        (50 tests)
│   ├── test_dynamic_pilot_integration.py (30 tests)
│   ├── test_stall_resolution_integration.py (15 tests)
│   └── test_scaling_integration.py      (20 tests)
│
├── e2e/
│   ├── test_z_depth_tracking_e2e.py     (20 tests)
│   ├── test_z_dynamic_scaling_e2e.py    (25 tests)
│   └── test_z_production_scenarios_e2e.py (20 tests)
│
└── fixtures/
    ├── depth_scenarios.py
    ├── stall_scenarios.py
    ├── scaling_mocks.py
    └── multi_coordinator.py
```

### Test Execution Strategy

**Per-Phase Testing:**
- Each phase must achieve 100% test coverage before proceeding
- No phase can be merged without passing all tests
- Regression suite runs on every commit

**CI/CD Pipeline:**
```
┌─────────────────────────────────────────────────────┐
│ CI/CD Test Pipeline                                  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. Pre-commit:                                     │
│     - Unit tests (340 tests, ~5 min)               │
│     - Linting, type checking                       │
│                                                      │
│  2. Pull Request:                                   │
│     - Unit tests                                    │
│     - Integration tests (115 tests, ~15 min)       │
│     - Backward compatibility tests                  │
│                                                      │
│  3. Main branch:                                    │
│     - Full test suite (520 tests, ~30 min)         │
│     - E2E tests (65 tests, ~45 min)                │
│     - Performance regression tests                  │
│                                                      │
│  4. Nightly:                                        │
│     - Full suite + stress tests                     │
│     - Multi-coordinator tests                       │
│     - Chaos engineering tests                       │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Performance Benchmarks

**Critical Path Performance Targets:**

| Operation | Baseline | With Depth Tracking | Max Overhead |
|-----------|----------|---------------------|--------------|
| Create operation | 2ms | 2.1ms | +5% |
| Depth calculation | N/A | 0.05ms | N/A |
| Stats collection (10k ops) | N/A | 80ms | <100ms |
| Dynamic minimum calc | N/A | 1ms | <5ms |
| Stall detection | N/A | 0.5ms | <1ms |
| Full maintenance tick | 100ms | 105ms | +5% |

### Backward Compatibility Tests

**Critical Tests (25 tests):**
1. Old operations (no depth fields) work correctly
2. Old coordinator + new operations (graceful degradation)
3. New coordinator + old operations (backward compatible)
4. Mixed deployment (some coordinators upgraded, others not)
5. Schema migration (add fields to existing operations)
6. Feature flag disabled → zero overhead
7. Depth tracking disabled → static pilot light used
8. All existing E2E tests pass unchanged
9. Performance benchmarks within 5% of baseline
10. API responses backward compatible
11. Metrics backward compatible (old metrics still exported)
12. Dashboards work with old + new metrics
13. Alerts backward compatible
14. Documentation updated
15. Upgrade guide provided
16. Rollback tested
17. Data migration tested (if needed)
18. Multi-version coordinator cluster tested
19. Client library compatibility
20. Executor compatibility (Docker, Pyodide, External)
21. Service compatibility
22. Connector compatibility
23. Multi-tenant compatibility
24. CRDT queue compatibility
25. Arrow Flight compatibility

---

## Deployment Strategy

### Rollout Phases

**Phase 1: Shadow Mode (Week 11)**
- Deploy depth tracking with `DEPTH_AWARE_PILOT_LIGHT_ENABLED=false`
- Collect depth statistics but don't use them for decisions
- Validate metrics accuracy
- Monitor performance impact
- Run A/B test: depth tracking vs baseline

**Phase 2: Gradual Rollout (Week 12)**
- Enable depth-aware pilot light for 1% of coordinators
- Monitor stall rate, resource usage, performance
- Increase to 10% → 50% → 100% over 2 weeks
- Rollback if any issues detected

**Phase 3: Chokepoint Detection (Week 13)**
- Enable stall detection for 10% → 100%
- Monitor false positive rate
- Tune thresholds based on production data

**Phase 4: Auto-Resolution (Week 14)**
- Enable auto-resolution for 10% → 100%
- Monitor resolution success rate
- Refine resolution strategies

**Phase 5: Node Scaling (Week 15+)**
- Enable node scaling for pilot customers only
- Webhook integration initially (manual approval)
- Auto-scaling after 2 weeks of successful pilot

### Feature Flags

```python
# Progressive rollout flags
DEPTH_TRACKING_ENABLED = true           # Always on (low risk)
DEPTH_AWARE_PILOT_LIGHT_ENABLED = true  # Week 12+
STALL_DETECTION_ENABLED = true          # Week 13+
STALL_AUTO_RESOLUTION_ENABLED = true    # Week 14+
NODE_SCALING_ENABLED = false            # Week 15+ (pilot)

# Percentage rollout (0.0 - 1.0)
DEPTH_AWARE_ROLLOUT_PERCENTAGE = 1.0    # 100% after validation
```

### Monitoring & Alerting

**Key Metrics to Monitor:**
1. Depth statistics (max, p95, avg per worker type)
2. Dynamic minimum values (per worker type)
3. Stall events (count, duration, severity)
4. Resolution success rate
5. Scaling events (count, reason, nodes added)
6. Performance overhead (operation latency)
7. Resource usage (CPU, memory per coordinator)
8. Error rates (RecursionError, stalls unresolved)

**Critical Alerts:**
1. `DepthExhaustion`: max_depth > N (P1 - immediate action)
2. `CriticalStall`: stall duration > 60s (P1)
3. `AutoResolutionFailed`: stall persists after resolution (P1)
4. `DepthLimitExceeded`: RecursionError rate > 1% (P2)
5. `PerformanceRegression`: overhead > 10% (P2)
6. `MemoryLeak`: coordinator memory growth (P2)

**Dashboards:**
1. **Depth Overview**: Max/P95/Avg depth per worker type, trends
2. **Stall Dashboard**: Active stalls, resolution time, root causes
3. **Scaling Dashboard**: Scaling events, node count, utilization
4. **Performance Dashboard**: Latency, overhead, throughput

---

## Rollback Plan

### Immediate Rollback (< 5 minutes)

**Trigger Conditions:**
- P1 incident (customer-impacting outage)
- Performance regression > 20%
- Stall rate increase > 50%
- Memory leak detected

**Rollback Steps:**
1. Set feature flags to disable: `DEPTH_AWARE_PILOT_LIGHT_ENABLED=false`
2. Redeploy coordinator with previous version (tagged release)
3. Restart all coordinators (rolling restart)
4. Monitor metrics for 30 minutes
5. Post-mortem: identify root cause

**Rollback Testing:**
- Practiced in staging every week
- Automated rollback scripts ready
- Runbook for on-call engineers

### Partial Rollback (< 30 minutes)

**Trigger Conditions:**
- Feature works but has edge case bugs
- Performance acceptable but not optimal
- Customer complaints but no outage

**Rollback Steps:**
1. Reduce rollout percentage: `DEPTH_AWARE_ROLLOUT_PERCENTAGE=0.1` (10%)
2. Disable specific features: `STALL_AUTO_RESOLUTION_ENABLED=false`
3. Monitor affected coordinators
4. Fix bugs in next release
5. Gradually re-enable

### Data Rollback

**Not Required:**
- Depth fields in OperationDAO have defaults
- Disabling features reverts to static pilot light
- No data migration needed for rollback
- No Redis schema changes required

---

## Success Metrics

### Primary KPIs

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| **Deadlock Rate** | 0.5% (stalls/operations) | <0.1% | Stall events / total operations |
| **Resource Efficiency** | 60% avg utilization | 75% | Active workers / total workers |
| **Auto-Resolution Rate** | N/A | >95% | Stalls resolved / stalls detected |
| **Scaling Accuracy** | N/A | >90% | Scaling events needed / triggered |
| **Performance Overhead** | 0% | <5% | (new latency - baseline) / baseline |

### Secondary KPIs

| Metric | Target | Measurement |
|--------|--------|-------------|
| Test Coverage | 100% | Line coverage (unit tests) |
| Documentation Coverage | 100% | All features documented |
| Zero Regressions | 100% | All existing tests pass |
| Incident Rate | <1 P1/month | Production incidents |
| MTTR (Mean Time to Recovery) | <5 minutes | Rollback time |

---

## Risk Mitigation

### High-Risk Areas

**1. Performance Regression**
- **Risk:** Depth tracking adds overhead to critical path
- **Mitigation:**
  - Benchmark every commit
  - Feature flag to disable if needed
  - Optimize hot paths (batched Redis reads)
  - Cache depth stats between ticks

**2. Deadlock Introduction**
- **Risk:** Dynamic minimums miscalculated, causes deadlock
- **Mitigation:**
  - Never go below static pilot light
  - Cap minimum at 50% of N (prevent starvation)
  - Emergency mode bypasses hysteresis on CRITICAL stalls
  - Extensive testing (100+ edge cases)

**3. Scaling Thrashing**
- **Risk:** Node scaling oscillates (scale up, scale down, repeat)
- **Mitigation:**
  - Cooldown period (5 minutes minimum)
  - Hysteresis for scaling decisions
  - Require 3+ ticks before triggering
  - Alert on rapid scaling events

**4. Data Inconsistency**
- **Risk:** Depth stats don't match actual operations
- **Mitigation:**
  - Validation tests (compare stats to actual scan)
  - Alert on inconsistency detected
  - Self-healing: re-scan if discrepancy > 10%

**5. Memory Leak**
- **Risk:** Depth tracking increases memory usage unbounded
- **Mitigation:**
  - Depth stats stored in-memory but bounded (1 value per worker type)
  - Stall tracker bounded (4 worker types × 1 state each)
  - No unbounded queues or caches introduced
  - Memory profiling in tests

### Testing Rigor

**Code Coverage Targets:**
- Unit tests: 100% line coverage
- Integration tests: 95% path coverage
- E2E tests: Critical paths only

**Review Process:**
- All PRs require 2 approvals
- Architecture review for Phase 1, 3, 6
- Security review for Phase 6 (node scaling)
- Performance review before each phase merge

---

## Timeline

```
┌────────────────────────────────────────────────────────────────┐
│ Implementation Timeline (12 weeks)                             │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Week 1-2:  Phase 1 - Schema & Depth Tracking                 │
│             └─ 90 tests, schema changes, depth propagation    │
│                                                                │
│  Week 3:    Phase 2 - Metrics & Observability                 │
│             └─ 45 tests, Prometheus, dashboards               │
│                                                                │
│  Week 4-5:  Phase 3 - Dynamic Pilot Light                     │
│             └─ 135 tests, dynamic minimums, hysteresis        │
│                                                                │
│  Week 6:    Phase 4 - Chokepoint Detection                    │
│             └─ 100 tests, stall detection, root cause         │
│                                                                │
│  Week 7-8:  Phase 5 - Auto-Resolution                         │
│             └─ 65 tests, resolution logic, emergency mode     │
│                                                                │
│  Week 9-10: Phase 6 - Node Scaling                            │
│             ��─ 85 tests, scaling decisions, integrations      │
│                                                                │
│  Week 11:   Shadow Mode Deployment                            │
│             └─ Production validation, A/B testing             │
│                                                                │
│  Week 12:   Gradual Rollout                                   │
│             └─ 1% → 10% → 50% → 100%                          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Appendix

### A. Code Examples

See implementation sections in each phase for detailed code examples.

### B. API Changes

**GET /v1/workers/metrics**
```json
{
  "depth_stats": {
    "BLOCKING": {"max": 15, "p95": 12, "avg": 5.2},
    "NON_BLOCKING": {"max": 8, "p95": 6, "avg": 3.1},
    ...
  },
  "dynamic_minimums": {
    "BLOCKING": 16,
    "NON_BLOCKING": 9,
    ...
  },
  "stalls": {
    "BLOCKING": {"stalled": false, "ticks": 0},
    ...
  },
  "scaling_recommendation": {
    "should_scale": false,
    "reason": "rebalancing_sufficient"
  }
}
```

### C. Migration Guide

**For Operators:**
1. Upgrade coordinator to v2.1.0
2. Enable `DEPTH_TRACKING_ENABLED=true` (default)
3. Monitor dashboards for 24 hours
4. Enable `DEPTH_AWARE_PILOT_LIGHT_ENABLED=true`
5. Monitor for 1 week before enabling auto-resolution

**For Developers:**
1. Update to latest SDK (v2.1.0+)
2. No code changes required (fully backward compatible)
3. Optional: Add depth limits to workflows (via decorators)
4. Optional: Monitor depth metrics in custom dashboards

### D. Troubleshooting

**Common Issues:**

1. **High depth detected**
   - Check for recursive patterns in workflows
   - Consider refactoring to iterative approaches
   - Add depth limits via decorators

2. **Stalls not resolving**
   - Check stall logs for root cause
   - Verify worker types are correct
   - Check for external bottlenecks (database, API)

3. **Scaling not triggering**
   - Verify `NODE_SCALING_ENABLED=true`
   - Check webhook URL is reachable
   - Review scaling cooldown period

---

**Document Version:** 1.0
**Last Updated:** 2026-01-02
**Next Review:** After Phase 1 completion
