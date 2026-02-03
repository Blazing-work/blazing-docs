"""Endpoint Interact Example

Demonstrates using app.interact() for bidirectional communication
between workflows and external services.

Documentation: https://blazing.work/docs/endpoints/overview
Related Examples: endpoint_routing, service_injection
"""

from blazing import Blazing
from blazing.web import create_asgi_app
import asyncio


async def main():
    app = Blazing()

    @app.step
    async def process_batch(items: list, services=None):
        """Process a batch of items."""
        results = []
        for item in items:
            # Simulate processing
            await asyncio.sleep(0.5)
            results.append({"id": item["id"], "processed": True, "value": item["value"] * 2})
        return results

    @app.workflow
    async def long_running_job(batch_size: int, services=None):
        """A long-running workflow that processes data in batches."""
        results = []
        for batch_num in range(3):
            # Create a batch of items
            items = [
                {"id": f"{batch_num}-{i}", "value": i}
                for i in range(batch_size)
            ]
            batch_results = await process_batch(items, services=services)
            results.extend(batch_results)
            await asyncio.sleep(1)  # Simulate time between batches

        return {
            "total_items": len(results),
            "batches": 3,
            "results": results,
        }

    @app.endpoint(path="/interact/demo")
    @app.workflow
    async def interact_demo(service_name: str, services=None):
        """Demonstrate bidirectional communication with a running service."""
        try:
            # Get an interactive handle to the service
            service = await app.interact(service_name)

            # Read service state or call service methods
            info = {
                "service_name": service_name,
                "connected": True,
                "message": f"Successfully connected to service: {service_name}",
            }

            return info
        except ValueError as e:
            return {
                "service_name": service_name,
                "connected": False,
                "error": str(e),
            }

    await app.publish()

    # Create ASGI app and run server
    asgi_app = await create_asgi_app(app, title="Interactive API")

    import uvicorn

    uvicorn.run(asgi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
