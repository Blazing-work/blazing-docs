import asyncio

from blazing import Blazing
from blazing.web import create_asgi_app


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def process_batch(batch_id: int, services=None):
        """Simulate processing a batch."""
        await asyncio.sleep(2)  # Simulate work
        return {"batch_id": batch_id, "status": "completed"}

    # Enable WebSocket with enable_websocket=True
    @app.endpoint(path="/process", enable_websocket=True)
    @app.workflow
    async def process_data(num_batches: int, services=None):
        """
        Long-running workflow with progress updates.
        WebSocket endpoint: ws://localhost:8080/process/ws
        """
        results = []
        for i in range(num_batches):
            result = await process_batch(i, services=services)
            results.append(result)
        return {"processed": len(results), "results": results}

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="WebSocket Real-Time API")

    # Run the server
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
