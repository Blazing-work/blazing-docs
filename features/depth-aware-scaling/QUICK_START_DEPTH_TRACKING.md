# Quick Start: Depth-Aware Scaling

**TL;DR:** Blazing now tracks call chain depth and will use it to prevent deadlocks and optimize resource allocation.

---

## What's New?

### Automatic Depth Tracking ✅ (Active Now)

Every operation now tracks:
- **Call depth**: How deep in the call chain (0 = root, 1 = first child, etc.)
- **Parent operation**: What created this operation
- **Root operation**: Entry point of the call chain
- **Depth by worker type**: Breakdown of depth per worker type

**Example:**
```
Route (depth=0)
  → Station A (depth=1, BLOCKING)
    → Station B (depth=2, BLOCKING)
      → Station C (depth=3, NON_BLOCKING)
```

Result: `depth_by_worker_type = {"BLOCKING": 2, "NON_BLOCKING": 1}`

### MAX_CALL_DEPTH Enforcement ✅ (Active Now)

**Hard limit: 50 levels deep**

If your code tries to recurse deeper than 50 levels:
```python
RecursionError: Maximum call depth 50 exceeded
(current depth: 51, parent operation: 01ABC...)
```

**Why:** Prevents infinite recursion and resource exhaustion

### Depth Statistics API ✅ (Active Now)

**Endpoint:** `GET /v1/metrics/depth`

```bash
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/v1/metrics/depth
```

**Response:**
```json
{
  "BLOCKING": {
    "max": 15,      // Deepest call chain
    "p95": 12,      // 95th percentile
    "avg": 5.2,     // Average depth
    "count": 150    // Operations tracked
  },
  "NON_BLOCKING": {...},
  "BLOCKING_SANDBOXED": {...},
  "NON_BLOCKING_SANDBOXED": {...}
}
```

---

## Coming Soon (Phases 3-6)

### Phase 3: Dynamic Pilot Light ⏸️
**Status:** Not active yet (set `DEPTH_AWARE_PILOT_LIGHT_ENABLED=true` to enable)

**What it does:**
- Calculates minimum workers based on actual call depth
- If max_depth=20 for BLOCKING → needs 21+ workers (not just 2)
- Prevents deadlocks from deep call chains
- Optimizes resource usage

### Phase 4: Chokepoint Detection ⏸️
**Status:** Not active yet (set `STALL_DETECTION_ENABLED=true` to enable)

**What it does:**
- Detects when queues stall (workers exist, queue has work, nothing dequeues)
- Identifies root cause (depth exhaustion, cross-type deadlock, etc.)
- Logs warnings and alerts

### Phase 5: Auto-Resolution ⏸️
**Status:** Not active yet (set `STALL_AUTO_RESOLUTION_ENABLED=true` to enable)

**What it does:**
- Automatically resolves detected stalls
- Rebalances workers within node
- Emergency mode for critical stalls

### Phase 6: Node Scaling ⏸️
**Status:** Not active yet (set `NODE_SCALING_ENABLED=true` to enable)

**What it does:**
- Triggers horizontal scaling when single node exhausted
- Integrates with Kubernetes HPA, AWS Auto Scaling
- Webhook for custom orchestrators

---

## Configuration

### Current (Safe Defaults)

```bash
# Active Features
DEPTH_TRACKING_ENABLED=true               # ✅ Collecting depth data
MAX_CALL_DEPTH=50                         # ✅ Enforcing recursion limit

# Not Active Yet (Phase 3+)
DEPTH_AWARE_PILOT_LIGHT_ENABLED=false    # ⏸️ Dynamic minimums
STALL_DETECTION_ENABLED=false             # ⏸️ Chokepoint detection
STALL_AUTO_RESOLUTION_ENABLED=false      # ⏸️ Auto-resolution
NODE_SCALING_ENABLED=false                # ⏸️ Horizontal scaling
```

### To Enable Dynamic Pilot Light (Phase 3)

```bash
# Enable depth-aware worker minimums
export DEPTH_AWARE_PILOT_LIGHT_ENABLED=true

# Optional: Tune safety margins
export DEPTH_SAFETY_MARGIN=1              # +1 workers above max_depth
export DEPTH_EMERGENCY_BUFFER=2           # Extra when queue growing

# Restart coordinator
docker-compose restart coordinator
```

---

## Monitoring

### View Depth Statistics

```bash
# Via API
curl -H "Authorization: Bearer test-token" \
     http://localhost:8000/v1/metrics/depth | jq .

# Via coordinator logs
docker logs blazing-coordinator | grep "depth_stats"

# Via worker mix logs
docker exec blazing-coordinator cat /app/worker_mix.log | grep "depth_stats"
```

### Check for RecursionErrors

```bash
# Search logs for depth limit exceeded
docker logs blazing-coordinator | grep "RecursionError"
docker logs blazing-executor | grep "Maximum call depth"
```

### Monitor Max Depth Trend

```bash
# Watch max depth over time
watch -n 5 'curl -s -H "Authorization: Bearer test-token" \
  http://localhost:8000/v1/metrics/depth | jq ".BLOCKING.max"'
```

---

## Troubleshooting

### High Depth Warning (max > 30)

**Symptom:** `depth_stats` shows max depth > 30

**Causes:**
- Deep recursive workflows
- Nested routes calling routes
- Chain of step → step → step

**Solutions:**
1. Review workflows for excessive nesting
2. Refactor to iterative approaches
3. Increase MAX_CALL_DEPTH if intentional
4. Add depth limits to workflows

### RecursionError

**Symptom:** Operations fail with "Maximum call depth 50 exceeded"

**Causes:**
- Infinite recursion bug
- Legitimate deep recursion (>50 levels)

**Solutions:**
1. Check for circular dependencies (A calls B calls A)
2. Increase MAX_CALL_DEPTH if needed:
   ```bash
   export MAX_CALL_DEPTH=100
   docker-compose restart coordinator
   ```
3. Refactor to avoid deep recursion

### Queue Stall (Phase 4+)

**Symptom:** Queue has work, workers exist, but nothing processes

**Causes:**
- Depth exhaustion (max_depth >= worker_count)
- Cross-type deadlock
- External bottleneck

**Solutions:**
- Enable `STALL_DETECTION_ENABLED=true`
- Check depth stats: max_depth vs worker counts
- Enable `STALL_AUTO_RESOLUTION_ENABLED=true` for auto-fix

---

## FAQs

### Q: Will this slow down my operations?
**A:** No. Depth tracking adds <1% overhead (tested with benchmarks).

### Q: Do I need to change my code?
**A:** No. Depth tracking is automatic and 100% backward compatible.

### Q: What if I disable depth tracking?
**A:** Set `DEPTH_TRACKING_ENABLED=false`. System falls back to static pilot light (no depth awareness).

### Q: Can I see depth in operation logs?
**A:** Yes. Look for `depth=X` in coordinator logs:
```
DEBUG-execute_operation: exec_result success=True, depth=5
```

### Q: What's a "good" max depth?
**A:**
- **0-10:** Normal (most workflows)
- **11-30:** High (complex workflows, acceptable)
- **31-40:** Very high (review for optimization)
- **41-50:** Extreme (approaching limit, risky)

### Q: Can depth limits cause failures?
**A:** Only if your workflow legitimately needs >50 levels of recursion. You can increase MAX_CALL_DEPTH if needed.

---

## Example: Debugging Deep Recursion

**Scenario:** You get RecursionError after deploying new workflow

**Step 1: Check depth stats**
```bash
curl -H "Authorization: Bearer test-token" \
     http://localhost:8000/v1/metrics/depth

# Output shows:
{
  "BLOCKING": {"max": 52, ...}  // Over limit!
}
```

**Step 2: Find deep operations**
```bash
# Check coordinator logs for depth
docker logs blazing-coordinator | grep "depth=" | grep -E "depth=(4[0-9]|5[0-9])"

# Output:
DEBUG-execute_operation: depth=52, parent=01ABC...
```

**Step 3: Trace call chain**
```bash
# Look up parent operation recursively
# parent → grandparent → ... → root
# This shows the full call stack
```

**Step 4: Fix**
- Option A: Refactor workflow to be less deep
- Option B: Increase MAX_CALL_DEPTH if legitimate
- Option C: Add explicit depth limits in code

---

## For Developers

### Adding Depth Limits to Workflows

```python
from blazing import Blazing

app = Blazing(...)

@app.step
async def recursive_step(n: int, depth: int = 0, services=None) -> int:
    # Add your own depth limit
    if depth > 20:
        raise ValueError(f"Custom depth limit exceeded: {depth}")

    if n <= 0:
        return 1

    return n * await recursive_step(n - 1, depth + 1, services=services)
```

### Querying Depth via API

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get(
        "http://localhost:8000/v1/metrics/depth",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = response.json()

    # Check if approaching limit
    max_depth = max(
        data['BLOCKING']['max'],
        data['NON_BLOCKING']['max'],
        data['BLOCKING_SANDBOXED']['max'],
        data['NON_BLOCKING_SANDBOXED']['max']
    )

    if max_depth > 40:
        print(f"⚠️ Warning: Max depth {max_depth}/50 (approaching limit)")
```

---

## Next Steps

1. **Deploy and Monitor** (Week 1-2)
   - Deploy with `DEPTH_TRACKING_ENABLED=true`
   - Monitor depth statistics
   - Validate no performance impact

2. **Enable Dynamic Pilot Light** (Week 3-4)
   - Set `DEPTH_AWARE_PILOT_LIGHT_ENABLED=true`
   - Start with 10% of coordinators
   - Gradually increase to 100%

3. **Enable Chokepoint Detection** (Week 5)
   - Set `STALL_DETECTION_ENABLED=true`
   - Monitor stall events
   - Tune thresholds

4. **Enable Auto-Resolution** (Week 6)
   - Set `STALL_AUTO_RESOLUTION_ENABLED=true`
   - Monitor resolution success rate

5. **Enable Node Scaling** (Week 7+)
   - Set `NODE_SCALING_ENABLED=true`
   - Configure webhook
   - Pilot with select customers

---

**For questions or issues:** See full documentation in `/docs/DEPTH_AWARE_SCALING_*.md`

**Version:** 1.0 (Phases 1 & 2 Complete)
**Last Updated:** 2026-01-02
