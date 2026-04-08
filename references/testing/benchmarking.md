# Blazing Benchmarking Guide

This guide explains how to evaluate Blazing’s performance, reproduce the framework comparison suite, and interpret the results when stacked against Celery and Dask.

---

## Objectives

- Measure end-to-end throughput and latency for representative workloads.
- Compare Blazing with Celery and Dask under identical worker counts.
- Stress-test worker mix optimisation under sustained and bursty load.

Benchmarks target automated pipelines rather than micro-benchmarks; results focus on pipeline completion time, queue behaviour, and stability.

---

## Prerequisites

- Python 3.11+ managed with `uv sync`.
- Redis or KeyDB accessible on `localhost:6380` (use `docker run -d --name redis-bench -p 6380:6379 redis/redis-stack`).
- Optional comparison frameworks: `uv pip install celery dask distributed`.
- Go toolchain if you plan to run the synthetic time-series API: `go run tests/helpers/timeseries_api.go`.

---

## Quick Start

```bash
# 1. Install extras (optional but recommended)
uv pip install celery dask distributed

# 2. Start Redis (if not already running)
docker run -d --name redis-bench -p 6380:6379 redis/redis-stack

# 3. Launch the synthetic API used by the benchmarks
go run tests/helpers/timeseries_api.go &

# 4. Execute the main comparison suite
uv run pytest tests/test_performance.py::TestPerformanceComparison::test_framework_comparison -v -s
```

The test harness spins up Blazing’s HQ, Coordinator, and worker processes automatically, then runs equivalent workloads through Celery and Dask with matched worker counts.

---

## Running Individual Benchmarks

| Scenario | Command |
|----------|---------|
| Full framework comparison | `uv run pytest tests/test_performance.py::TestPerformanceComparison::test_framework_comparison -v -s` |
| Blazing-only throughput profile | `uv run pytest tests/test_performance.py::TestPerformanceComparison::test_blazing_baseline -v` |
| Latency distribution capture | `uv run pytest tests/test_performance.py::TestPerformanceComparison::test_latency_histogram -v` |

Programmatic access is available via helper classes in `tests/helpers/benchmark_comparison.py`. Each helper normalises worker counts using constants defined in `benchmark_config.py`.

---

## Ensuring Fair Comparisons

1. **Equal workers**: All frameworks must run with the same number of worker processes. Defaults live in `tests/helpers/benchmark_config.py` (`STANDARD_NUM_WORKERS`, `BLAZING_NUM_PROCESSES`, `CELERY_CONCURRENCY`, `DASK_NUM_WORKERS`).
2. **Warm up**: Allow each framework to process a short run before collecting metrics. Warm-up tasks prime connection pools and caches.
3. **Isolate resources**: Avoid running other CPU-intensive processes during comparisons.
4. **Repeat runs**: Take the mean of at least three runs when publishing figures externally.

The comparison harness logs worker configuration at the start of each run; review the pytest output to confirm parity.

---

## Metrics Captured

The suite records the following metrics for every framework:

- **Throughput**: Completed tasks per second over the measurement window.
- **P50 / P95 latency**: Time from task submission to completion.
- **Resource utilisation**: Process-level CPU and memory consumption sampled periodically.
- **Queue backlog**: Outstanding tasks at fixed intervals (Blazing exposes this via Redis counters; Celery and Dask rely on their respective APIs).
- **Error rate**: Tasks that failed or timed out.

Results are rendered as structured dictionaries in the pytest output and can be exported to JSON for further analysis.

---

## Interpreting Results

- **Blazing** typically excels on mixed workloads that reuse connections and require async + blocking orchestration. Expect slightly higher start-up overhead than Celery for trivial workloads because worker mix analysis kicks in after the warm-up phase.
- **Celery** often leads on simple, CPU-bound microtasks due to lower framework overhead, provided broker/network latency remains low.
- **Dask** prioritises dataframe and array workloads; in this comparison it serves as a baseline for Python task execution with distributed scheduling overhead included.

When reporting results externally, accompany throughput numbers with latency percentiles and specify task complexity.

---

## Customising Benchmarks

- **Worker counts**: Override `STANDARD_NUM_WORKERS` via environment variable `BENCHMARK_WORKERS`. The helper script will propagate the value to each framework.
- **Task mix**: Modify payload generators in `tests/helpers/task_generators.py` to emulate your own workload (API-heavy, CPU-heavy, mixed).
- **Duration**: Adjust `STANDARD_MEASUREMENT_DURATION` or run the stress tests (`test_extended_duration`) for longer observation windows.
- **Framework selection**: Update `get_available_frameworks()` to disable Celery or Dask if they are not installed.

---

## Troubleshooting

- **Celery workers missing**: Start them manually with `celery -A tests.helpers.benchmark_comparison worker -l info`.
- **Dask cluster startup errors**: Reduce `DASK_NUM_WORKERS` or disable threading by setting `DASK_DISTRIBUTED__WORKER__THREADS=1`.
- **Blazing coordinator conflicts**: Ensure no previous benchmark processes are running; `pkill -f start_test_coordinator` cleans residual workers.
- **Redis connection refused**: Verify the Redis container is running and reachable on `localhost:6380`.

Logs for each framework are stored under `tests/.benchmarks/` and can be inspected after a run.

---

## Next Steps

- Use the [Testing Guide](testing.md) to validate worker mix behaviour under adaptive workloads.
- Dive into [Worker Mix Optimiser](worker-mix-optimizer.md) to understand how throughput gains are achieved.
- Review [Framework Comparisons](comparisons.md) for positioning guidance when presenting benchmark results to stakeholders.

For bespoke benchmarking assistance or deeper competitive analysis, contact the Blazing product team.
