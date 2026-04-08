from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def clean_data(data: list, services=None):
        """Remove null values."""
        return [x for x in data if x is not None]

    @app.step
    async def normalize(data: list, services=None):
        """Normalize to 0-1 range."""
        min_val, max_val = min(data), max(data)
        return [(x - min_val) / (max_val - min_val) for x in data]

    @app.workflow
    async def prepare_dataset(raw_data: list, services=None):
        """Clean and normalize dataset."""
        cleaned = await clean_data(raw_data, services=services)
        normalized = await normalize(cleaned, services=services)
        return normalized

    await app.publish()

    # Execute workflow using the simplest one-liner pattern
    result = await app.prepare_dataset(
        raw_data=[1, None, 5, 10, None, 15]
    ).wait_result()
    print(result)  # [0.0, 0.29, 0.64, 1.0]


# ==============================================================================
# SYNC API - For learning and prototyping only
# NOTE: For production, we strongly recommend using the async Blazing class above
# ==============================================================================


def main_sync():
    """Synchronous version using SyncBlazing - for learning/prototyping only."""
    from blazing import SyncBlazing

    # SyncBlazing is great for learning, but use async Blazing for production
    app = SyncBlazing()

    @app.step
    async def clean_data(data: list, services=None):
        """Remove null values."""
        return [x for x in data if x is not None]

    @app.step
    async def normalize(data: list, services=None):
        """Normalize to 0-1 range."""
        min_val, max_val = min(data), max(data)
        return [(x - min_val) / (max_val - min_val) for x in data]

    @app.workflow
    async def prepare_dataset(raw_data: list, services=None):
        """Clean and normalize dataset."""
        cleaned = await clean_data(raw_data, services=services)
        normalized = await normalize(cleaned, services=services)
        return normalized

    # No await, no asyncio.run()!
    app.publish()
    result = app.prepare_dataset(raw_data=[1, None, 5, 10, None, 15])
    print(result)  # [0.0, 0.29, 0.64, 1.0]


if __name__ == "__main__":
    # Choose your preferred style:
    import asyncio

    asyncio.run(main())  # Async version

    # Or use SyncBlazing (cleanest sync experience):
    # main_sync()
