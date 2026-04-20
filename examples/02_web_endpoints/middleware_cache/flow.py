"""Cache Middleware Example

Demonstrates how to cache expensive endpoint responses to
improve performance and reduce load on backend services.

Documentation: https://blazing.work/docs/endpoints/middleware#response-caching
Related Examples: middleware_cors, middleware_rate_limit
"""

from blazing import Blazing
from blazing.middleware import CacheMiddleware
from blazing.web import create_asgi_app


async def main():
    app = Blazing()

    @app.endpoint(
        path="/api/stats",
        middleware=[
            CacheMiddleware(ttl=300)  # Cache for 5 minutes
        ],
    )
    @app.workflow
    async def get_statistics(services=None):
        """Return computed statistics with caching."""
        # This would typically involve expensive database queries
        # or complex computations
        return {
            "statistics": {
                "total_users": 15234,
                "active_users": 8912,
                "total_requests": 1250000,
                "avg_response_time_ms": 142.5,
                "cache_hit_rate": 0.87,
            },
            "computed_at": "2026-02-03T12:00:00Z",
            "message": "Statistics computed from last 24 hours",
        }

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="Cached API")

    import uvicorn

    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
