"""OAuth2 Authentication Example.

Demonstrates protecting HTTP endpoints with OAuth2 token validation.
Shows both token introspection and built-in provider support.
"""

from blazing import Blazing
from blazing.auth import OAuth2Auth, AuthContext
from blazing.web import create_asgi_app


async def main():
    app = Blazing()

    # Option 1: OAuth2 with token introspection
    # Validates tokens by calling the OAuth2 provider's introspection endpoint
    oauth2_introspection = OAuth2Auth(
        introspection_url="https://auth.example.com/oauth/introspect",
        client_id="your-client-id",
        client_secret="your-client-secret",
        scopes_claim="scope",
    )

    # Option 2: OAuth2 with built-in provider (e.g., Google)
    # Uses Google's token validation endpoint
    oauth2_google = OAuth2Auth(
        provider="google",
        client_id="your-google-client-id",
        client_secret="your-google-client-secret",
    )

    @app.endpoint(path="/api/user-data", auth=oauth2_introspection)
    @app.workflow
    async def user_data(services=None):
        """
        Protected endpoint requiring OAuth2 access token.

        OAuth2 Flow:
        1. User authenticates with OAuth2 provider
        2. Provider issues access token
        3. Client includes token in Authorization header
        4. Server validates token via introspection endpoint
        5. Request proceeds if token is valid and active
        """
        if services and services.auth_context:
            auth_context: AuthContext = services.auth_context
            return {
                "message": "OAuth2 protected resource",
                "user_id": auth_context.user_id,
                "tenant_id": auth_context.tenant_id,
                "scopes": auth_context.scopes,
                "claims": auth_context.claims,
                "auth_method": auth_context.auth_method,
            }
        return {"error": "Authentication failed"}

    @app.endpoint(path="/api/google-user", auth=oauth2_google)
    @app.workflow
    async def google_user(services=None):
        """
        Protected endpoint using Google OAuth2 provider.

        Validates tokens using Google's UserInfo endpoint.
        """
        if services and services.auth_context:
            auth_context: AuthContext = services.auth_context
            return {
                "message": "Google OAuth2 authenticated",
                "user_id": auth_context.user_id,
                "provider": auth_context.metadata.get("provider"),
                "claims": auth_context.claims,
            }
        return {"error": "Authentication failed"}

    @app.endpoint(path="/health")
    @app.workflow
    async def health(services=None):
        """Public endpoint (no authentication required)."""
        return {"status": "healthy"}

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="OAuth2 Auth Example")

    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
