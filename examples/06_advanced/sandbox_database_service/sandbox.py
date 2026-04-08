import asyncio

from blazing import Blazing
from blazing.base import BaseService


# Simulated user database
_users_db = [
    {"id": 1, "name": "Alice", "age": 28, "score": 0},
    {"id": 2, "name": "Bob", "age": 35, "score": 0},
    {"id": 3, "name": "Charlie", "age": 22, "score": 0},
    {"id": 4, "name": "Diana", "age": 45, "score": 0},
]


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # YOUR CODE (trusted - has real database access)
    @app.service
    class DatabaseService(BaseService):
        def __init__(self, connectors):
            # Real database connection (user code NEVER sees this)
            # In production: self._db = connectors.get("postgres")
            pass

        async def fetch_users(self, min_age: int) -> list:
            """Fetch users from database (simulated)."""
            # In production:
            # query = text("SELECT id, name, age FROM users WHERE age >= :min_age")
            # result = await self._db.execute(query, {"min_age": min_age})
            # return [dict(row) for row in result]
            await asyncio.sleep(0.1)  # Simulate DB latency
            return [u for u in _users_db if u["age"] >= min_age]

        async def save_scores(self, user_scores: list):
            """Batch update user scores (simulated)."""
            # In production:
            # for item in user_scores:
            #     query = text("UPDATE users SET score = :score WHERE id = :id")
            #     await self._db.execute(query, ...)
            # await self._db.commit()
            for item in user_scores:
                for user in _users_db:
                    if user["id"] == item["user_id"]:
                        user["score"] = item["score"]
                        print(f"  [DB] Updated user {user['name']}: score = {item['score']}")
            await asyncio.sleep(0.1)

    # USER CODE (untrusted - runs in WASM sandbox)
    @app.step
    async def calculate_scores(min_age: int, services=None):
        """
        User-provided scoring logic.
        Can call database methods but CANNOT access database directly.
        """
        # Fetch data via service (executes on trusted worker)
        users = await services["DatabaseService"].fetch_users(min_age)
        # Process in sandbox (NO database access)
        user_scores = []
        for user in users:
            score = len(user["name"]) * user["age"]  # User's scoring logic
            user_scores.append({"user_id": user["id"], "score": score})
        # Save via service (executes on trusted worker)
        await services["DatabaseService"].save_scores(user_scores)
        return {"processed": len(user_scores), "users": [u["name"] for u in users]}

    # YOUR CODE (trusted - orchestrates)
    @app.workflow
    async def score_users(min_age: int, services=None):
        """Run user's scoring algorithm safely."""
        return await calculate_scores(min_age, services=services)

    await app.publish()

    # Execute the workflow
    print("Running user scoring algorithm (for users age 25+)...")
    result = await app.score_users(min_age=25).wait_result()

    print(f"\nScoring Results:")
    print(f"  Users Processed: {result['processed']}")
    print(f"  Users: {', '.join(result['users'])}")

    print("\nFinal User Scores:")
    for user in _users_db:
        if user["score"] > 0:
            print(f"  {user['name']} (age {user['age']}): score = {user['score']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
