# Blazing Testing Guide

This guide summarises the automated and manual tests that keep Blazing’s worker mix optimiser and runtime predictable under load. Use it to run smoke checks before releases, reproduce adaptive workload tests, and interpret the resulting telemetry.

---

## Test Strategy Overview

Blazing’s test suite covers three layers:

1. **Unit tests** – deterministic checks for DAO operations, worker mix calculations, and utility helpers.
2. **Integration tests** – exercise the Coordinator/Worker loop against synthetic workloads.
3. **Scenario tests** – long-running adaptive workloads that validate hysteresis, urgency overrides, and backlog recovery.

This guide focuses on the integration and scenario tests because they are most relevant to operations teams and product demos.

---

## Prerequisites

- Python 3.11+ with project dependencies installed via `uv sync`.
- Redis or KeyDB accessible to the tests (default `localhost:6380`).
- Optional: Go runtime if you want to replay the synthetic time-series API (`go run tests/helpers/timeseries_api.go`).
- Ensure `worker_mix.log` is writable in the repository root (tests rotate this file).

---

## Core Test Suites

| Test Module | Purpose | Duration | Workload Mix |
|-------------|---------|----------|--------------|
| `test_extended_throughput.py` | Baseline async throughput & queue stability | ~3 min | 100% async |
| `test_mixed_workload.py` | Fixed blend (50% async, 30% blocking, 20% hybrid) | ~6 min | Mixed |
| `test_adaptive_workload.py` | Adaptive load with Poisson spikes & urgency overrides | ~6 min | Mixed, rate-controlled |
| `test_hysteresis_states.py` | Verifies state machine transitions | ~2 min | Synthetic |

All tests spin up Coordinator and worker processes in-process, then tear everything down when complete.

---

## Quick Start

```bash
# Clean up residual sessions (recommended between runs)
src/blazing/scripts/cleanup_tests.sh

# Run the adaptive workload scenario
uv run pytest tests/test_adaptive_workload.py -v -s

# Tail worker mix decisions while the test runs
tail -f worker_mix.log | grep "worker_mix_applied"
```

Expected adaptive workload output:

- Measurement window completes in ~5 minutes.
- 1 400–1 600 tasks processed with >95 % success rate.
- Worker mix log shows 10–15 configuration changes and urgency overrides when backlog exceeds thresholds.

---

## Running the Full Regression Suite

```bash
uv run pytest \
  tests/test_extended_throughput.py \
  tests/test_mixed_workload.py \
  tests/test_adaptive_workload.py \
  tests/test_hysteresis_states.py \
  -v
```

Add `-s` for real-time log output. The suite takes 15–20 minutes depending on hardware.

---

## Interpreting Telemetry

During each maintenance loop, the Coordinator writes a JSON payload to `worker_mix.log`. Key fields:

- `mix_before` / `mix_after`: Counts for blocking workers (`P`), async workers (`A`), and async concurrency (`C`).
- `score_delta`: Predicted throughput improvement for the applied change.
- `hysteresis_state`: Current state of the decision process (`stable`, `evaluating`, `transitioning`, `settling`).
- `urgency`: Pressure score derived from queue backlog; values >3.0 bypass dwell timers.
- `queues`: Aggregate backlog and enqueue/dequeue deltas per queue type.

For ad‑hoc analysis use:

```bash
# Count mix transitions
grep -c "mix_after" worker_mix.log

# Inspect urgency spikes
jq '.payload.urgency' worker_mix.log | tail

# Visualise backlog trends
python -m blazing.monitor_coordinator_charts
```

---

## Customising Scenarios

- **Workload ratios**: Override environment variables (`ASYNC_RATIO`, `BLOCKING_RATIO`, `HYBRID_RATIO`) before running scripts.
- **Backlog target**: Set `TARGET_BACKLOG` to tune the controller’s baseline queue depth.
- **Task volume**: Adjust `MEASUREMENT_TASKS` for longer or shorter runs.
- **Spikes**: Disable Poisson spikes by exporting `ENABLE_SPIKES=false`.

Example:

```bash
export ASYNC_RATIO=70
export BLOCKING_RATIO=10
export HYBRID_RATIO=20
export TARGET_BACKLOG=400
uv run pytest tests/test_adaptive_workload.py -v -s
```

---

## Troubleshooting

- **Port conflicts**: Tests bind to Redis, Arrow Flight, and worker control ports. If a previous run crashed, `src/blazing/scripts/cleanup_tests.sh` removes residual processes and data.
- **Redis connection errors**: Ensure the Redis container or service is running and accessible. Tests default to `localhost:6380`.
- **Hanging tests**: Tail `worker_mix.log`—if logs stop updating, gather stack traces with `py-spy top --pid <coordinator_pid>`.
- **Low throughput**: Verify your machine meets baseline requirements (8+ logical cores, SSD). High CPU steal indicates competing workloads.

---

## Success Criteria Checklist

After running `test_adaptive_workload.py`, confirm:

- Runtime duration between 4–6 minutes for default settings.
- Success rate ≥95 %.
- Urgency overrides triggered when backlog >500.
- Pilot-light invariants maintained (`P ≥ 1`, `A ≥ 1`, `A·C ≥ 3` whenever respective workloads exist).
- Hysteresis state transitions visible (no oscillation between `evaluating` and `settling` for prolonged periods).

Document anomalies in the pull request or incident report, attaching relevant slices of `worker_mix.log`.

---

## Related Resources

- [Benchmarking Guide](benchmarking.md)
- [Worker Mix Optimiser Deep Dive](worker-mix-optimizer.md)
- `src/blazing/scripts/run_adaptive_workload.sh` – 5-minute wrapper around the adaptive scenario.
- `src/blazing/scripts/run_long_test.sh` – Extended run for endurance testing.

Reach out to the Blazing core team for enterprise-scale soak tests or bespoke workload modelling.
