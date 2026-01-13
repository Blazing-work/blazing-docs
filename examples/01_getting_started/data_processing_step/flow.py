from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # Define a step (the unit of work)
    @app.step
    async def filter_positive(numbers: list, services=None):
        """Filter out negative numbers."""
        return [n for n in numbers if n > 0]

    # Define a workflow that orchestrates steps
    @app.workflow
    async def get_positive_numbers(numbers: list, services=None):
        """Workflow: filter and return only positive numbers."""
        return await filter_positive(numbers, services=services)

    # IMPORTANT: Publish to register steps/workflows with the execution engine
    await app.publish()

    # Execute workflow and wait for result
    result = await app.get_positive_numbers(numbers=[1, -2, 3, -4, 5]).wait_result()
    print(result)  # [1, 3, 5]


# ==============================================================================
# SYNC API - For learning and prototyping only
# NOTE: For production, we strongly recommend using the async Blazing class above
# ==============================================================================


def main_sync():
    """Synchronous version using SyncBlazing - for learning/prototyping only."""
    from blazing import SyncBlazing

    app = SyncBlazing()

    @app.step
    async def filter_positive(numbers: list, services=None):
        """Filter out negative numbers."""
        return [n for n in numbers if n > 0]

    @app.workflow
    async def get_positive_numbers(numbers: list, services=None):
        """Workflow: filter and return only positive numbers."""
        return await filter_positive(numbers, services=services)

    # No await, no asyncio.run()!
    app.publish()
    print(app.get_positive_numbers(numbers=[1, -2, 3, -4, 5]))  # [1, 3, 5]


if __name__ == "__main__":
    # Choose your preferred style:
    import asyncio

    asyncio.run(main())  # Async version

    # Or use SyncBlazing (cleanest sync experience):
    # main_sync()
