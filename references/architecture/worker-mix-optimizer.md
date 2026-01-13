# Worker Mix Optimiser Deep Dive

Blazing’s worker mix optimiser keeps pipelines responsive by continuously rebalancing blocking and asynchronous capacity. This document distils the algorithm, safety guardrails, telemetry schema, and planned enhancements so you can explain the system to customers and diagnose behaviour in production.

---

## Problem Statement

Given a fixed pool of worker processes (`N`), Blazing must decide:

- How many processes run in blocking mode (`P`).
- How many processes run in async mode (`A`).
- How many concurrent coroutines each async process should host (`C`).

The goal is to maximise throughput while ensuring:

1. Blocking workloads always have at least one worker (pilot light).
2. Async workloads retain sufficient concurrency (`A ≥ 1`, `A·C ≥ 3`).
3. Total in-flight work respects the global capacity cap (`P + A·C ≤ MAX_CONCURRENT_TASKS_PER_COORDINATOR`, default 200).
4. Reconfigurations are amortised—no oscillation or thrashing under noisy workloads.

---

## Inputs Collected Each Maintenance Tick

The Coordinator samples metrics every second:

- **Timing statistics** (`T_b`, `T_p`, `T_s`): Exponentially weighted averages of blocking task duration, async processing time, and async span (processing + I/O).
- **Workload mix**: Ratio of blocking vs async operations observed in the latest window (default 10 000 operations).
- **Queue pressure**: Aggregate backlog, enqueue/dequeue deltas, and backlog growth rate for blocking and async queues.
- **Historical mix**: Previously applied configurations and dwell timers.

These inputs feed a scoring function that evaluates candidate mixes.

---

## Scoring Function

For each candidate `(P, A, C)` the optimiser computes:

```
λ_b = P / max(T_b, EPSILON_TIME)
λ_a = min(A / max(T_p, EPSILON_TIME),
          (A · C) / max(T_s, EPSILON_TIME))

score = w_b * λ_b + (1 - w_b) * λ_a
```

Where `w_b` blends the observed blocking ratio with queue pressure (50/50 weighting when queue data is available). The candidate with the highest `score` that satisfies safety constraints becomes the target mix.

### Constraints Applied (in priority order)

1. **Global capacity cap**: Clip `C`, then `A`, then `P` until `P + A·C ≤ MAX_CONCURRENT_TASKS_PER_COORDINATOR`.
2. **Pilot light**: Ensure `P ≥ 1` if blocking work exists; ensure `A ≥ 1` and `A·C ≥ 3` if async work exists.
3. **Hysteresis**: Require ≥10 % improvement to start evaluating and ≥8 % sustained improvement across 5 ticks to apply a change. Urgency overrides bypass hysteresis when backlog grows sharply.
4. **Dwell time**: Enforce a cool-down period (default 60 s) between changes unless urgency ≥3.0.
5. **Staged rollout**: Apply large changes gradually (see below) to avoid sudden spikes in resource usage.

---

## Staged Rollout Strategy

When transitioning from one mix to another, the optimiser applies staged rollouts:

1. Move one worker at a time from blocking to async (or vice versa), waiting for confirmation ticks between stages.
2. Adjust async concurrency (`C`) in increments to stay within readiness thresholds.
3. Record each intermediate stage and revert if throughput drops below the previous steady-state.

Staging prevents sudden load surges or drops when reconfiguring dozens of coroutines at once.

---

## Telemetry Schema

Each maintenance tick writes a JSON entry to `worker_mix.log`. Example payload:

```json
{
  "timestamp": "2025-01-10T12:34:56.789Z",
  "event": "worker_mix_evaluated",
  "payload": {
    "mix_before": {"P": 2, "A": 6, "C": 4},
    "mix_after": {"P": 1, "A": 8, "C": 5},
    "score_delta": 0.18,
    "urgency": 2.7,
    "hysteresis_state": "transitioning",
    "confirmation_ticks": 3,
    "queues": {
      "blocking": {"backlog": 42, "delta_enqueued": 120, "delta_dequeued": 105},
      "async": {"backlog": 310, "delta_enqueued": 820, "delta_dequeued": 760}
    }
  }
}
```

Key fields:

- `score_delta` – relative improvement from the new mix.
- `urgency` – backlog-derived pressure (≥3 bypasses hysteresis/dwell).
- `hysteresis_state` – one of `stable`, `evaluating`, `transitioning`, `settling`.
- `confirmation_ticks` – remaining confirmations before finalising the change.

Monitoring tools (`blazing.btop`, `monitor_coordinator_charts.py`) visualise these fields in real time.

---

## Safety Guarantees

The optimiser enforces:

- **Deadlock prevention**: Pilot light rules keep at least one worker ready for every active workload type.
- **Capacity guardrails**: Global cap aligns with file descriptor and upstream rate-limit constraints.
- **Graceful fallback**: If telemetry is missing or inconsistent, the optimiser keeps the previous mix and raises a warning in logs.
- **Manual override**: Operators can pin worker counts via environment variables (`BLAZING_FORCE_BLOCKING`, `BLAZING_FORCE_ASYNC`) for emergency scenarios; the optimiser honours overrides while still respecting capacity limits.

---

## Diagnostic Checklist

When investigating unexpected behaviour:

1. **Check urgency** – high urgency with stagnant mixes implies dwell or hysteresis thresholds are too conservative.
2. **Verify telemetry freshness** – stale `delta_enqueued` values indicate Redis lag or measurement gaps.
3. **Inspect staged transitions** – large changes should appear as multiple log entries with incremental mix adjustments.
4. **Confirm pilot light** – ensure `P` and `A` never drop to zero while the corresponding workload is active.
5. **Review resource caps** – if `P + A·C` repeatedly hits 200, consider increasing `MAX_CONCURRENT_TASKS_PER_COORDINATOR` (after verifying OS limits).

Logs can be parsed with `jq` or custom scripts; see the [Testing Guide](testing.md) for sample commands.

---

## Roadmap & Enhancements

The following improvements are planned:

1. **Adaptive transition costs** – learn empirical costs for converting workers between roles instead of using fixed estimates.
2. **Profile-based fast paths** – detect common workload signatures (CPU-heavy, IO-heavy) and apply pre-optimised mixes.
3. **Latency-aware scoring** – incorporate service-level objectives when prioritising blocking vs async throughput.
4. **Per-route quotas** – prevent a single noisy route from consuming all async concurrency.
5. **Telemetry API** – expose mix decisions via a structured endpoint for dashboards and alerting.

---

## Related Documentation

- [Architecture Overview](architecture.md) – runtime components and execution flow.
- [Testing Guide](testing.md) – how to reproduce adaptive workload scenarios and validate optimiser behaviour.
- [Benchmarking Guide](benchmarking.md) – measuring the impact of worker mix optimisation compared to other frameworks.

For customer briefings or technical deep dives, combine this document with live telemetry (`btop`) to demonstrate adaptive behaviour in action.

