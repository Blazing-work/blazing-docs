"""Endpoint Routing Example

Demonstrates creating multiple HTTP endpoints with different paths
using the @app.endpoint decorator.

Documentation: https://blazing.work/docs/endpoints/overview
Related Examples: endpoint_interact, middleware_cors
"""

from blazing import Blazing
from blazing.web import create_asgi_app


async def main():
    app = Blazing()

    # Health check endpoint - GET /health
    @app.endpoint(path="/health")
    @app.workflow
    async def health_check(services=None):
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "example-api",
            "version": "1.0.0",
        }

    # User retrieval endpoint - POST /users/get
    @app.endpoint(path="/users/get")
    @app.workflow
    async def get_user(user_id: int, services=None):
        """Get user information by ID."""
        # Simulated database lookup
        users = {
            1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
            2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
            3: {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
        }
        user = users.get(user_id)
        if user:
            return {"success": True, "user": user}
        return {"success": False, "error": "User not found"}

    # User creation endpoint - POST /users/create
    @app.endpoint(path="/users/create")
    @app.workflow
    async def create_user(name: str, email: str, services=None):
        """Create a new user."""
        # Simulated user creation
        new_user = {
            "id": 999,
            "name": name,
            "email": email,
            "created_at": "2024-01-01T00:00:00Z",
        }
        return {"success": True, "user": new_user}

    # Data processing endpoint - POST /data/process
    @app.endpoint(path="/data/process")
    @app.workflow
    async def process_data(data: list, operation: str, services=None):
        """Process a list of numbers with the specified operation."""
        if operation == "sum":
            result = sum(data)
        elif operation == "average":
            result = sum(data) / len(data) if data else 0
        elif operation == "max":
            result = max(data) if data else None
        elif operation == "min":
            result = min(data) if data else None
        else:
            return {"error": f"Unknown operation: {operation}"}

        return {
            "operation": operation,
            "input": data,
            "result": result,
            "count": len(data),
        }

    await app.publish()

    # Create ASGI app and run server
    asgi_app = await create_asgi_app(app, title="Multi-Route API")

    import uvicorn

    uvicorn.run(asgi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
