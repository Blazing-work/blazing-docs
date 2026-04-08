import asyncio

from blazing import Blazing
from blazing.base import BaseService


# Simulated in-memory database for demonstration
_users_db = {}
_next_id = 1


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.service
    class UserDatabase(BaseService):
        def __init__(self, connectors):
            # In production: self._db = connectors.get("postgres")
            pass

        async def get_user(self, user_id: int) -> dict:
            """Fetch user from database (simulated)."""
            # In production:
            # query = text("SELECT id, name, email FROM users WHERE id = :id")
            # result = await self._db.execute(query, {"id": user_id})
            # row = result.fetchone()
            # return {"id": row[0], "name": row[1], "email": row[2]}
            if user_id in _users_db:
                return _users_db[user_id]
            raise ValueError(f"User {user_id} not found")

        async def create_user(self, name: str, email: str) -> int:
            """Create new user (simulated)."""
            global _next_id
            # In production:
            # query = text("INSERT INTO users (name, email) VALUES (:name, :email) RETURNING id")
            # result = await self._db.execute(query, {"name": name, "email": email})
            # return result.fetchone()[0]
            user_id = _next_id
            _next_id += 1
            _users_db[user_id] = {"id": user_id, "name": name, "email": email}
            print(f"[DB] Created user: id={user_id}, name={name}, email={email}")
            await asyncio.sleep(0.1)  # Simulate DB latency
            return user_id

    @app.step
    async def register_user(name: str, email: str, services=None):
        """Register new user (uses database service)."""
        user_id = await services["UserDatabase"].create_user(name, email)
        return {"user_id": user_id, "name": name, "email": email}

    @app.workflow
    async def create_new_user(name: str, email: str, services=None):
        """Workflow: register a new user."""
        result = await register_user(name, email, services=services)
        return result

    await app.publish()

    # Execute the workflow
    print("Creating new user...")
    result = await app.create_new_user(
        name="Alice Smith",
        email="alice@example.com"
    ).wait_result()

    print(f"\nUser created successfully:")
    print(f"  ID: {result['user_id']}")
    print(f"  Name: {result['name']}")
    print(f"  Email: {result['email']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
