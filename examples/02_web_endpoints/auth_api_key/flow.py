"""API Key Authentication Example.

Demonstrates protecting HTTP endpoints with API key authentication.
Shows both header-based and query parameter authentication.

Documentation: https://blazing.work/docs/endpoints/authentication#apikeyauth
Related Examples: auth_jwt, auth_oauth2
"""

from blazing import Blazing
from blazing.auth import APIKeyAuth, AuthContext
from blazing.web import create_asgi_app


async def main():
    app = Blazing()

    # Configure API key authentication
    # Supports both header and query parameter
    api_key_auth = APIKeyAuth(
        header="X-API-Key",
        query_param="api_key",
        keys=["demo-key-123", "test-key-456"],
    )

    @app.endpoint(path="/api/data", auth=api_key_auth)
    @app.workflow
    async def protected_data(services=None):
        """Protected endpoint requiring API key."""
        # Access auth context to get authenticated user info
        if services and services.auth_context:
            auth_context: AuthContext = services.auth_context
            return {
                "message": "Access granted",
                "data": "sensitive information",
                "auth_method": auth_context.auth_method,
            }
        return {"error": "Authentication failed"}

    @app.endpoint(path="/health")
    @app.workflow
    async def health(services=None):
        """Public endpoint (no authentication required)."""
        return {"status": "healthy", "version": "1.0.0"}

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="API Key Auth Example")

    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
