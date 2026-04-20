from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # Define a step that processes data
    @app.step
    async def validate_data(data: dict, services=None):
        """Validate that data has required fields."""
        if "id" not in data or "value" not in data:
            return {"valid": False, "error": "Missing required fields"}
        return {"valid": True, "data": data}

    @app.step
    async def transform_data(data: dict, services=None):
        """Transform the data (uppercase the value)."""
        return {
            "id": data["id"],
            "value": data["value"].upper(),
            "processed": True
        }

    # Define a workflow that combines steps
    @app.workflow
    async def process_data(data: dict, services=None):
        """Workflow: validate then transform data."""
        validation = await validate_data(data, services=services)
        if not validation["valid"]:
            return validation
        result = await transform_data(data, services=services)
        return result

    # Publish to the execution engine
    await app.publish()

    # Execute workflow and wait for result
    print("Running workflow...")

    # Option 1: One-liner with wait_result() - SIMPLEST! ⭐
    result = await app.process_data(data={"id": 1, "value": "Hello from Blazing Flow"}).wait_result()

    # Option 2: Using RemoteRun handle (more explicit)
    # run = await app.process_data(data={"id": 1, "value": "Hello from Blazing Flow"})
    # result = await run.result()

    # Option 3: Using run() method (by name)
    # run = await app.run("process_data", data={"id": 1, "value": "Hello from Blazing Flow"})
    # result = await run.wait_result()

    print(f"Task completed! Result: {result}")


# ==============================================================================
# SYNC API - For learning and prototyping only
# NOTE: For production, we strongly recommend using the async Blazing class above
# ==============================================================================


def main_sync():
    """Synchronous version using SyncBlazing - for learning/prototyping only."""
    from blazing import SyncBlazing

    app = SyncBlazing()

    @app.step
    async def validate_data(data: dict, services=None):
        """Validate that data has required fields."""
        if "id" not in data or "value" not in data:
            return {"valid": False, "error": "Missing required fields"}
        return {"valid": True, "data": data}

    @app.step
    async def transform_data(data: dict, services=None):
        """Transform the data (uppercase the value)."""
        return {
            "id": data["id"],
            "value": data["value"].upper(),
            "processed": True
        }

    @app.workflow
    async def process_data(data: dict, services=None):
        """Workflow: validate then transform data."""
        validation = await validate_data(data, services=services)
        if not validation["valid"]:
            return validation
        result = await transform_data(data, services=services)
        return result

    # No await, no asyncio.run()!
    app.publish()
    result = app.process_data(data={"id": 1, "value": "Hello from Blazing Flow"})
    print(f"Task completed! Result: {result}")


if __name__ == "__main__":
    # Choose your preferred style:
    import asyncio

    asyncio.run(main())  # Async version (recommended)

    # Or use SyncBlazing (cleanest sync experience):
    # main_sync()
