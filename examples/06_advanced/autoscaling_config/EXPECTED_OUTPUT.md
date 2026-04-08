# Expected Output

## Configuration

Set environment variables before starting the Blazing server:

```bash
# Enable AIMD autoscaling
export AIMD_ENABLED=true

# Configure capacity bounds
export AIMD_REDIS_MIN=50
export AIMD_REDIS_MAX=1000
export AIMD_REDIS_INITIAL=500

# AIMD algorithm parameters
export AIMD_ALPHA=1.0       # Add 1 connection per healthy tick
export AIMD_BETA=0.7        # Reduce to 70% on unhealthy signal

# Health signal thresholds
export AIMD_P95_THRESHOLD_MS=500
export AIMD_P99_THRESHOLD_MS=1000
export AIMD_ERROR_RATE_THRESHOLD=0.05
export AIMD_TIMEOUT_RATE_THRESHOLD=0.02

# Hysteresis (prevent thrashing)
export AIMD_INCREASE_AFTER_TICKS=3
export AIMD_DECREASE_COOLDOWN_TICKS=5

# Demand gating
export AIMD_UTILIZATION_THRESHOLD=0.7

# Optional: Adaptive baseline learning
export AIMD_ADAPTIVE_MODE=true
export AIMD_ADAPTIVE_RATIO=1.7
```

## Running

```bash
python flow.py
```

## Output

```
Processing batch with AIMD autoscaling...
(Worker pool will adapt capacity based on load and health signals)

Processed 10 items in auto-scaled worker pool
Sample results: [
  {'item_id': 0, 'status': 'processed', 'worker': 'auto-scaled-pool'},
  {'item_id': 1, 'status': 'processed', 'worker': 'auto-scaled-pool'},
  {'item_id': 2, 'status': 'processed', 'worker': 'auto-scaled-pool'},
  {'item_id': 3, 'status': 'processed', 'worker': 'auto-scaled-pool'},
  {'item_id': 4, 'status': 'processed', 'worker': 'auto-scaled-pool'}
]
```

## Configuration Parameters

### Core Capacity Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AIMD_ENABLED` | bool | `false` | Master toggle for AIMD autoscaling |
| `AIMD_REDIS_MIN` | int | 50 | Minimum Redis pool connections |
| `AIMD_REDIS_MAX` | int | 1000 | Maximum Redis pool connections |
| `AIMD_REDIS_INITIAL` | int | 500 | Starting pool size |

### AIMD Algorithm

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AIMD_ALPHA` | float | 1.0 | Additive increase per healthy tick |
| `AIMD_BETA` | float | 0.5 | Multiplicative decrease factor (0.7 = 30% reduction) |

### Health Signal Thresholds

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AIMD_P95_THRESHOLD_MS` | float | 500.0 | p95 latency threshold (ms) |
| `AIMD_P99_THRESHOLD_MS` | float | 1000.0 | p99 latency threshold (ms) |
| `AIMD_ERROR_RATE_THRESHOLD` | float | 0.05 | Error rate threshold (5%) |
| `AIMD_TIMEOUT_RATE_THRESHOLD` | float | 0.02 | Timeout rate threshold (2%) |
| `AIMD_EVENT_LOOP_LAG_MS` | float | 50.0 | Event loop lag threshold (ms) |

### Hysteresis Controls

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AIMD_INCREASE_AFTER_TICKS` | int | 3 | Healthy ticks before increase |
| `AIMD_DECREASE_COOLDOWN_TICKS` | int | 5 | Ticks to wait after decrease |
| `AIMD_UTILIZATION_THRESHOLD` | float | 0.7 | Minimum utilization to allow increase (70%) |

### Adaptive Mode (Optional)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AIMD_ADAPTIVE_MODE` | bool | `false` | Enable adaptive baseline learning |
| `AIMD_ADAPTIVE_RATIO` | float | 1.7 | Trigger if 70% above baseline |
| `AIMD_ADAPTIVE_DEVIATION` | float | 6.0 | Standard deviations for trigger |
| `AIMD_ADAPTIVE_WARMUP_TICKS` | int | 20 | Ticks before adaptive activates |

## Notes

- **AIMD** = Additive Increase Multiplicative Decrease (same algorithm as TCP congestion control)
- **Additive Increase**: When all signals healthy, add `alpha` capacity every `increase_after_ticks` ticks
- **Multiplicative Decrease**: When any signal exceeds threshold, multiply capacity by `beta` (e.g., 0.7 = reduce by 30%)
- Autoscaling applies to:
  - Redis connection pools
  - HTTP client connection pools
  - Worker thread pools
  - Concurrency limits
- AIMD observes 5 health signals:
  - p95 latency
  - p99 latency
  - Error rate
  - Timeout rate
  - Event loop lag
- **Demand gating** prevents over-provisioning: only increases capacity if utilization >= threshold
- **Cooldown** prevents thrashing: waits N ticks after decrease before allowing another decrease
- **Adaptive mode** learns baseline from observed metrics (recommended for production)
- All configuration is via environment variables (no code changes needed)
- Changes require service restart to take effect
