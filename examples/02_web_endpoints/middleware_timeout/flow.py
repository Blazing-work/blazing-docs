"""Timeout Middleware Example

Demonstrates request timeout enforcement to prevent endpoints
from hanging indefinitely on slow operations.

Documentation: https://blazing.work/docs/endpoints/middleware#timeout-enforcement
Related Examples: middleware_retry, middleware_circuit_breaker
"""

from blazing import Blazing
from blazing.middleware import TimeoutMiddleware
from blazing.web import create_asgi_app
import asyncio


async def main():
    app = Blazing()

    @app.endpoint(
        path="/api/compute",
        middleware=[
            TimeoutMiddleware(
                timeout=5.0,
                message="Computation exceeded time limit",
            )
        ],
    )
    @app.workflow
    async def compute_result(duration: float = 2.0, services=None):
        """Perform computation with timeout protection.

        Args:
            duration: Simulated computation time in seconds
        """
        # Simulate long-running computation
        await asyncio.sleep(duration)

        return {
            "status": "success",
            "result": {
                "computation": "completed",
                "duration_seconds": duration,
                "value": 42,
            },
        }

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="Timeout Middleware API")

    import uvicorn

    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
