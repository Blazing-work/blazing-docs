from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # =========================================================================
    # SANDBOXED STEPS - Runs in WASM (untrusted user code)
    # =========================================================================

    @app.step(sandboxed=True)
    async def user_transform(data: list, services=None):
        """
        USER-PROVIDED CODE - Runs in WASM sandbox.

        Security guarantees:
        ✓ NO network access (can't call external APIs)
        ✓ NO filesystem access (can't read secrets)
        ✓ NO subprocess spawning
        ✓ Complete memory isolation
        ✓ Can ONLY do pure Python computation
        """
        # User's transformation logic (safe)
        result = []
        for item in data:
            if item["value"] > 0:
                result.append(
                    {"value": item["value"] * 2, "category": item["category"].upper()}
                )
        return result

    @app.step(sandboxed=True)
    async def user_filter(data: list, threshold: float, services=None):
        """
        Another sandboxed step - filter data by threshold.

        Sandboxed code is ~2-3x slower than native Python due to WASM overhead,
        but provides complete security isolation.
        """
        return [item for item in data if item["value"] > threshold]

    @app.step(sandboxed=True)
    async def user_aggregate(data: list, services=None):
        """
        Sandboxed aggregation step.

        Even complex computations are safe - the code cannot
        access anything outside its memory space.
        """
        from collections import defaultdict

        category_sums = defaultdict(float)
        for item in data:
            category_sums[item["category"]] += item["value"]

        return {
            "category_totals": dict(category_sums),
            "item_count": len(data),
            "max_value": max((item["value"] for item in data), default=0),
        }

    # =========================================================================
    # TRUSTED STEP - Runs on normal workers (your infrastructure code)
    # =========================================================================

    @app.step  # Default: sandboxed=False (trusted)
    async def prepare_data(services=None):
        """
        YOUR CODE - Runs on trusted workers with full access.

        Use trusted steps for:
        ✓ Database queries
        ✓ External API calls
        ✓ File system operations
        ✓ Any infrastructure operations
        """
        # Simulate fetching from your database
        return [
            {"value": 10.5, "category": "alpha"},
            {"value": -5.2, "category": "beta"},
            {"value": 23.7, "category": "alpha"},
            {"value": 8.1, "category": "gamma"},
        ]

    # =========================================================================
    # WORKFLOW - Orchestrates trusted and sandboxed steps
    # =========================================================================

    @app.workflow
    async def process_user_data(threshold: float, services=None):
        """
        Workflow combining TRUSTED and SANDBOXED steps.

        Pattern:
        1. Trusted step fetches data from your infrastructure
        2. Sandboxed steps process the data (user code)
        3. Result returned (you can store with trusted step if needed)

        This is the RECOMMENDED pattern for multi-tenant platforms!
        """
        # Step 1: YOUR code fetches data (trusted)
        raw_data = await prepare_data(services=services)

        # Step 2: USER code transforms data (sandboxed - safe!)
        transformed = await user_transform(raw_data, services=services)

        # Step 3: USER code filters data (sandboxed - safe!)
        filtered = await user_filter(transformed, threshold, services=services)

        # Step 4: USER code aggregates data (sandboxed - safe!)
        aggregated = await user_aggregate(filtered, services=services)

        return aggregated

    await app.publish()

    # Execute the workflow
    print("Running workflow with sandboxed user code...")
    result = await app.process_user_data(threshold=15.0).wait_result()

    print("\nWorkflow complete (user code ran safely in WASM sandbox)!")
    print(f"  Category totals: {result['category_totals']}")
    print(f"  Items processed: {result['item_count']}")
    print(f"  Max value: {result['max_value']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
