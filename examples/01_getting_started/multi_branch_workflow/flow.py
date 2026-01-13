import asyncio

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def calculate_mean(numbers: list, services=None):
        """Calculate mean."""
        return sum(numbers) / len(numbers)

    @app.step
    async def calculate_median(numbers: list, services=None):
        """Calculate median."""
        sorted_nums = sorted(numbers)
        mid = len(sorted_nums) // 2
        return sorted_nums[mid]

    @app.workflow
    async def get_statistics(numbers: list, services=None):
        """Calculate multiple statistics in parallel."""
        mean, median = await asyncio.gather(
            calculate_mean(numbers, services=services),
            calculate_median(numbers, services=services),
        )
        return {"mean": mean, "median": median, "count": len(numbers)}

    await app.publish()

    # Execute workflow using the simplest one-liner pattern
    result = await app.get_statistics(numbers=[1, 2, 3, 4, 5]).wait_result()
    print(result)  # {"mean": 3.0, "median": 3, "count": 5}


# ==============================================================================
# SYNC API - For learning and prototyping only
# NOTE: For production, we strongly recommend using the async Blazing class above
# ==============================================================================


def main_sync():
    """Synchronous version using SyncBlazing - for learning/prototyping only."""
    import asyncio as _asyncio

    from blazing import SyncBlazing

    # SyncBlazing is great for learning, but use async Blazing for production
    app = SyncBlazing()

    @app.step
    async def calculate_mean(numbers: list, services=None):
        """Calculate mean."""
        return sum(numbers) / len(numbers)

    @app.step
    async def calculate_median(numbers: list, services=None):
        """Calculate median."""
        sorted_nums = sorted(numbers)
        mid = len(sorted_nums) // 2
        return sorted_nums[mid]

    @app.workflow
    async def get_statistics(numbers: list, services=None):
        """Calculate multiple statistics in parallel."""
        mean, median = await _asyncio.gather(
            calculate_mean(numbers, services=services),
            calculate_median(numbers, services=services),
        )
        return {"mean": mean, "median": median, "count": len(numbers)}

    # No await, no asyncio.run()!
    app.publish()
    result = app.get_statistics(numbers=[1, 2, 3, 4, 5])
    print(result)  # {"mean": 3.0, "median": 3, "count": 5}


if __name__ == "__main__":
    # Choose your preferred style:
    import asyncio

    asyncio.run(main())  # Async version

    # Or use SyncBlazing (cleanest sync experience):
    # main_sync()
