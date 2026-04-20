import jwt
from fastapi.security import HTTPAuthorizationCredentials

from blazing import Blazing
from blazing.web import create_asgi_app


async def main():
    app = Blazing()  # Uses Blazing SaaS by default
    SECRET_KEY = "your-jwt-secret"

    # Authentication handlers
    async def verify_jwt(credentials: HTTPAuthorizationCredentials) -> bool:
        """Verify JWT token."""
        if not credentials:
            return False
        try:
            token = credentials.credentials
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            return payload.get("user_id") is not None
        except jwt.InvalidTokenError:
            return False

    async def verify_api_key(credentials: HTTPAuthorizationCredentials) -> bool:
        """Verify API key (simpler authentication)."""
        if not credentials:
            return False
        # In production: check against database
        return credentials.credentials == "secret-api-key"

    # Public endpoint (no auth)
    @app.endpoint(path="/health")
    @app.workflow
    async def health_check(services=None):
        """Public health check endpoint."""
        return {"status": "healthy", "version": "1.0.0"}

    # Protected endpoint (JWT required)
    @app.endpoint(path="/secure/data", auth_handler=verify_jwt)
    @app.workflow
    async def get_secure_data(user_id: int, services=None):
        """
        Protected endpoint requiring JWT authentication.
        Header: Authorization: Bearer <jwt-token>
        """
        return {"user_id": user_id, "data": "sensitive data"}

    # Protected endpoint (API key required)
    @app.endpoint(path="/admin/stats", auth_handler=verify_api_key)
    @app.workflow
    async def get_admin_stats(services=None):
        """
        Admin endpoint requiring API key.
        Header: Authorization: Bearer secret-api-key
        """
        return {"total_users": 1000, "active_jobs": 42}

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="Authenticated API")

    # Run the server
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
