"""AIMD Autoscaling Configuration Example

This example shows how to configure AIMD (Additive Increase Multiplicative Decrease)
autoscaling for Blazing worker pools using environment variables.

AIMD adapts capacity based on health signals (latency, error rate, etc.).

Documentation: https://blazing.work/docs/advanced/autoscaling
Related Examples: scheduling_workflow, cli_publish_deploy
"""

from blazing import Blazing
import asyncio


async def main():
    """
    Demonstrate AIMD configuration via environment variables.

    In production, set these environment variables before starting the Blazing server:

    # Enable AIMD autoscaling
    export AIMD_ENABLED=true

    # Configure capacity bounds
    export AIMD_REDIS_MIN=50          # Minimum Redis connections
    export AIMD_REDIS_MAX=1000        # Maximum Redis connections
    export AIMD_REDIS_INITIAL=500     # Starting capacity

    # AIMD algorithm parameters
    export AIMD_ALPHA=1.0             # Additive increase per healthy tick
    export AIMD_BETA=0.7              # Multiplicative decrease factor (30% reduction)

    # Health signal thresholds
    export AIMD_P95_THRESHOLD_MS=500          # p95 latency threshold
    export AIMD_P99_THRESHOLD_MS=1000         # p99 latency threshold
    export AIMD_ERROR_RATE_THRESHOLD=0.05     # 5% error rate threshold
    export AIMD_TIMEOUT_RATE_THRESHOLD=0.02   # 2% timeout rate threshold

    # Hysteresis (prevent thrashing)
    export AIMD_INCREASE_AFTER_TICKS=3        # Must be healthy for 3 ticks before increasing
    export AIMD_DECREASE_COOLDOWN_TICKS=5     # Wait 5 ticks after decrease

    # Demand gating
    export AIMD_UTILIZATION_THRESHOLD=0.7     # Only increase if >=70% utilized

    # Optional: Enable adaptive baseline learning
    export AIMD_ADAPTIVE_MODE=true
    export AIMD_ADAPTIVE_RATIO=1.7            # Trigger if 70% above baseline
    """

    app = Blazing()

    @app.step
    async def process_item(item_id: int, services=None):
        """Process a single item (simulates workload)."""
        # Simulate varying workload
        await asyncio.sleep(0.1)
        return {
            "item_id": item_id,
            "status": "processed",
            "worker": "auto-scaled-pool",
        }

    @app.workflow
    async def batch_processing(batch_size: int, services=None):
        """
        Process a batch of items using auto-scaled workers.

        The worker pool will automatically scale up during high load
        and scale down during idle periods based on AIMD configuration.
        """
        # Fan-out: process all items in parallel
        tasks = [
            process_item(i, services=services) for i in range(batch_size)
        ]
        results = await asyncio.gather(*tasks)

        return {
            "batch_size": batch_size,
            "processed": len(results),
            "results": results[:5],  # Return first 5 for brevity
        }

    await app.publish()

    # Execute workflow - worker pool will adapt based on load
    print("Processing batch with AIMD autoscaling...")
    print("(Worker pool will adapt capacity based on load and health signals)")
    print()

    result = await app.batch_processing(10).wait_result()
    print(f"Processed {result['processed']} items in auto-scaled worker pool")
    print(f"Sample results: {result['results']}")


if __name__ == "__main__":
    asyncio.run(main())
