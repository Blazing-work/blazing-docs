import uvicorn

from blazing import Blazing
from blazing.web import create_asgi_app


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.endpoint(path="/calculate")
    @app.workflow
    async def calculate(x: int, y: int, services=None):
        """Add two numbers together."""
        return x + y

    # Publish and create FastAPI app
    await app.publish()
    fastapi_app = await create_asgi_app(app)
    # Run server
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
