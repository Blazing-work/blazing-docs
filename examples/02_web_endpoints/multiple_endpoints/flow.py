from blazing import Blazing
from blazing.web import create_asgi_app


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # V1 Endpoints
    @app.endpoint(path="/v1/users/create")
    @app.workflow
    async def create_user_v1(name: str, email: str, services=None):
        """V1: Create user (simple)."""
        return {"id": 1, "name": name, "email": email, "version": "v1"}

    @app.endpoint(path="/v1/users/list")
    @app.workflow
    async def list_users_v1(services=None):
        """V1: List all users."""
        return {"users": [], "count": 0, "version": "v1"}

    # V2 Endpoints (with enhanced features)
    @app.endpoint(path="/v2/users/create")
    @app.workflow
    async def create_user_v2(name: str, email: str, metadata: dict, services=None):
        """V2: Create user with metadata."""
        return {
            "id": 1,
            "name": name,
            "email": email,
            "metadata": metadata,
            "version": "v2",
            "created_at": "2025-12-09T10:00:00Z",
        }

    @app.endpoint(path="/v2/users/list")
    @app.workflow
    async def list_users_v2(limit: int = 10, offset: int = 0, services=None):
        """V2: List users with pagination."""
        return {
            "users": [],
            "count": 0,
            "limit": limit,
            "offset": offset,
            "version": "v2",
        }

    # Admin endpoints
    @app.endpoint(path="/admin/stats")
    @app.workflow
    async def admin_stats(services=None):
        """Admin: System statistics."""
        return {"total_users": 1000, "active_jobs": 42, "uptime_seconds": 86400}

    await app.publish()
    fastapi_app = await create_asgi_app(
        app,
        title="User Management API",
        description="Multi-version user management API",
        version="2.0.0",
    )

    # Run the server
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
