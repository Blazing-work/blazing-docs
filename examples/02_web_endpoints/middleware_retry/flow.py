"""Retry Middleware Example

Demonstrates automatic retry with exponential backoff for
endpoints that call unreliable external services.

Documentation: https://blazing.work/docs/endpoints/middleware#automatic-retries
Related Examples: middleware_circuit_breaker, middleware_timeout
"""

from blazing import Blazing
from blazing.middleware import RetryMiddleware
from blazing.web import create_asgi_app
import random


async def main():
    app = Blazing()

    @app.endpoint(
        path="/api/external",
        middleware=[
            RetryMiddleware(
                max_retries=3,
                retry_on_status={502, 503, 504},
                initial_delay=0.1,
                max_delay=5.0,
                exponential_base=2.0,
                jitter=True,
            )
        ],
    )
    @app.workflow
    async def call_external_service(services=None):
        """Call external service that may fail transiently.

        Simulates an unreliable external API that occasionally
        returns 503 Service Unavailable errors.
        """
        # Simulate transient failures (30% chance)
        if random.random() < 0.3:
            # In real scenario, this would be from external API
            return {
                "error": "Service temporarily unavailable",
                "status_code": 503,
            }

        return {
            "status": "success",
            "data": {
                "external_id": "ext-12345",
                "result": "Data successfully retrieved from external service",
                "provider": "example-api",
            },
        }

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="Retry Middleware API")

    import uvicorn

    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
