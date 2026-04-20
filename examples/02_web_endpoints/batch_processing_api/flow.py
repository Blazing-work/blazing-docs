import asyncio

from blazing import Blazing
from blazing.web import create_asgi_app


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def fetch_user(user_id: int, services=None):
        """Fetch user data."""
        # Simulate database query
        await asyncio.sleep(0.5)
        return {"user_id": user_id, "name": f"User {user_id}", "score": user_id * 10}

    @app.step
    async def process_user(user: dict, multiplier: float, services=None):
        """Process user data."""
        return {
            "user_id": user["user_id"],
            "name": user["name"],
            "original_score": user["score"],
            "final_score": int(user["score"] * multiplier),
        }

    @app.endpoint(path="/batch/users")
    @app.workflow
    async def process_users_batch(user_ids: list, multiplier: float, services=None):
        """
        Process multiple users concurrently.
        POST /batch/users
        Body: {"user_ids": [1, 2, 3], "multiplier": 1.5}
        """
        # Fetch all users concurrently
        fetch_tasks = [fetch_user(user_id, services=services) for user_id in user_ids]
        users = await asyncio.gather(*fetch_tasks)
        # Process all users concurrently
        process_tasks = [
            process_user(user, multiplier, services=services) for user in users
        ]
        results = await asyncio.gather(*process_tasks)
        return {"processed_count": len(results), "results": results}

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="Batch Processing API")

    # Run the server
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
