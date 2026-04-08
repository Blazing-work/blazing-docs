from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # Define a step (the unit of work)
    @app.step
    async def hello(services=None):
        """A simple hello world step."""
        return {"message": "Hello, World!"}

    @app.step
    async def hello_name(name: str, services=None):
        """A personalized greeting step."""
        return {"message": f"Hello, {name}!"}

    # Define workflows that orchestrate steps
    @app.workflow
    async def greet(services=None):
        """Workflow: say hello."""
        return await hello(services=services)

    @app.workflow
    async def greet_person(name: str, services=None):
        """Workflow: personalized greeting."""
        return await hello_name(name, services=services)

    # IMPORTANT: Publish to register steps/workflows with the execution engine
    await app.publish()

    # Execute workflows and wait for results
    result1 = await app.greet().wait_result()
    result2 = await app.greet_person(name="Blazing").wait_result()

    print(result1)  # {"message": "Hello, World!"}
    print(result2)  # {"message": "Hello, Blazing!"}


# ==============================================================================
# SYNC API - For learning and prototyping only
# NOTE: For production, we strongly recommend using the async Blazing class above
# ==============================================================================


def main_sync():
    """Synchronous version using SyncBlazing - for learning/prototyping only."""
    from blazing import SyncBlazing

    app = SyncBlazing()

    @app.step
    async def hello(services=None):
        """A simple hello world step."""
        return {"message": "Hello, World!"}

    @app.step
    async def hello_name(name: str, services=None):
        """A personalized greeting step."""
        return {"message": f"Hello, {name}!"}

    @app.workflow
    async def greet(services=None):
        """Workflow: say hello."""
        return await hello(services=services)

    @app.workflow
    async def greet_person(name: str, services=None):
        """Workflow: personalized greeting."""
        return await hello_name(name, services=services)

    # No await, no asyncio.run()!
    app.publish()
    print(app.greet())  # {"message": "Hello, World!"}
    print(app.greet_person(name="Blazing"))  # {"message": "Hello, Blazing!"}


if __name__ == "__main__":
    # Choose your preferred style:
    import asyncio

    asyncio.run(main())  # Async version (recommended)

    # Or use SyncBlazing (cleanest sync experience):
    # main_sync()
