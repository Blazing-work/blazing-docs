"""Rate Limit Middleware Example

Demonstrates how to protect an API endpoint from abuse by
limiting the number of requests per client.
"""

from blazing import Blazing
from blazing.middleware import RateLimitMiddleware
from blazing.web import create_asgi_app


async def main():
    app = Blazing()

    @app.endpoint(
        path="/api/data",
        middleware=[
            RateLimitMiddleware(requests_per_minute=60)
        ],
    )
    @app.workflow
    async def get_data(services=None):
        """Return data with rate limiting protection."""
        # This would typically fetch from database or external service
        return {
            "status": "success",
            "data": {
                "temperature": 72.5,
                "humidity": 45.2,
                "pressure": 1013.25,
                "timestamp": "2026-02-03T12:00:00Z",
            },
            "message": "Weather data retrieved successfully",
        }

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="Rate Limited API")

    import uvicorn

    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
