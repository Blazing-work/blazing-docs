"""Circuit Breaker Middleware Example

Demonstrates the circuit breaker pattern to protect against
cascading failures when a downstream service becomes unhealthy.
"""

from blazing import Blazing
from blazing.middleware import CircuitBreakerMiddleware
from blazing.web import create_asgi_app
import random


async def main():
    app = Blazing()

    @app.endpoint(
        path="/api/database",
        middleware=[
            CircuitBreakerMiddleware(
                failure_threshold=5,
                success_threshold=2,
                timeout=30.0,
                failure_status_codes={500, 502, 503, 504},
            )
        ],
    )
    @app.workflow
    async def query_database(services=None):
        """Query database with circuit breaker protection.

        Simulates a database that may become overloaded or unhealthy.
        Circuit breaker prevents cascading failures by failing fast
        when the database is down.
        """
        # Simulate database failures (40% chance when unhealthy)
        if random.random() < 0.4:
            # In real scenario, this would be from actual database error
            return {
                "error": "Database connection timeout",
                "status_code": 503,
            }

        return {
            "status": "success",
            "data": {
                "user_count": 15234,
                "active_sessions": 892,
                "database_health": "healthy",
            },
        }

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="Circuit Breaker API")

    import uvicorn

    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
