"""JWT Authentication Example.

Demonstrates protecting HTTP endpoints with JWT token authentication.
Shows how to validate JWT tokens and access user claims.
"""

from blazing import Blazing
from blazing.auth import JWTAuth, AuthContext
from blazing.web import create_asgi_app


async def main():
    app = Blazing()

    # Configure JWT authentication
    # In production, use environment variables for secrets
    jwt_auth = JWTAuth(
        secret="your-secret-key-here",
        algorithms=["HS256"],
        audience="my-api",
        issuer="https://auth.example.com",
        header_name="Authorization",
        header_prefix="Bearer",
    )

    @app.endpoint(path="/api/user/profile", auth=jwt_auth)
    @app.workflow
    async def get_user_profile(services=None):
        """Protected endpoint requiring JWT authentication."""
        # Access authenticated user from JWT claims
        if services and services.auth_context:
            auth_context: AuthContext = services.auth_context
            return {
                "user_id": auth_context.user_id,
                "tenant_id": auth_context.tenant_id,
                "scopes": auth_context.scopes,
                "auth_method": auth_context.auth_method,
                "profile": {
                    "name": "John Doe",
                    "email": "john@example.com",
                },
            }
        return {"error": "Authentication failed"}

    @app.endpoint(path="/api/admin/users", auth=jwt_auth)
    @app.workflow
    async def list_users(services=None):
        """Admin endpoint requiring JWT with specific claims."""
        if services and services.auth_context:
            auth_context: AuthContext = services.auth_context

            # Check if user has admin scope
            if "admin" in auth_context.scopes:
                return {
                    "users": [
                        {"id": 1, "name": "Alice"},
                        {"id": 2, "name": "Bob"},
                    ],
                    "authenticated_as": auth_context.user_id,
                }
            else:
                return {"error": "Insufficient permissions"}
        return {"error": "Authentication failed"}

    @app.endpoint(path="/health")
    @app.workflow
    async def health(services=None):
        """Public endpoint (no authentication required)."""
        return {"status": "healthy"}

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="JWT Auth Example")

    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
