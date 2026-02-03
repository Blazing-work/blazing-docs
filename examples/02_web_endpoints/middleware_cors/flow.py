"""CORS Middleware Example

Demonstrates how to enable Cross-Origin Resource Sharing (CORS)
for a browser-based single-page application (SPA) API.
"""

from blazing import Blazing
from blazing.middleware import CORSMiddleware
from blazing.web import create_asgi_app


async def main():
    app = Blazing()

    @app.endpoint(
        path="/api/users",
        middleware=[
            CORSMiddleware(
                allow_origins=["http://localhost:3000"],
                allow_methods=["GET", "POST"],
                allow_headers=["Authorization", "Content-Type"],
                allow_credentials=True,
            )
        ],
    )
    @app.workflow
    async def get_users(services=None):
        """Get list of users for browser SPA."""
        # This would typically query a database
        users = [
            {"id": 1, "name": "Alice", "role": "admin"},
            {"id": 2, "name": "Bob", "role": "user"},
            {"id": 3, "name": "Charlie", "role": "user"},
        ]
        return {"users": users, "count": len(users)}

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="CORS API Example")

    import uvicorn

    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
