"""Service Injection Example

Demonstrates using the services=None parameter for dependency injection
in steps and workflows to access external services.

Documentation: https://blazing.work/docs/guides/custom-connectors#service-injection-pattern
Related Examples: custom_service, endpoint_interact
"""

from blazing import Blazing


async def main():
    app = Blazing()

    # Simple service class for database access
    class DatabaseService:
        def __init__(self):
            self.data = {
                "users": [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                    {"id": 3, "name": "Charlie"},
                ]
            }

        async def get_user(self, user_id: int):
            """Retrieve a user by ID."""
            for user in self.data["users"]:
                if user["id"] == user_id:
                    return user
            return None

    @app.step
    async def fetch_user_data(user_id: int, services=None):
        """Fetch user data using injected service."""
        if services and hasattr(services, "database"):
            user = await services.database.get_user(user_id)
            if user:
                return {"found": True, "user": user}
            return {"found": False, "user_id": user_id}
        return {"error": "No database service available"}

    @app.step
    async def format_greeting(user_data: dict, services=None):
        """Format a personalized greeting."""
        if user_data.get("found"):
            user = user_data["user"]
            return f"Hello, {user['name']}! (ID: {user['id']})"
        return f"User not found: {user_data.get('user_id', 'unknown')}"

    @app.workflow
    async def greet_user(user_id: int, services=None):
        """Workflow that fetches user and creates greeting."""
        # Services are automatically passed through workflow
        user_data = await fetch_user_data(user_id, services=services)
        greeting = await format_greeting(user_data, services=services)
        return greeting

    await app.publish()

    # Create a custom services object with our database
    class CustomServices:
        def __init__(self):
            self.database = DatabaseService()

    # Execute workflow with custom services injected
    custom_services = CustomServices()
    result = await app.greet_user(2, services=custom_services).wait_result()
    print(result)  # Hello, Bob! (ID: 2)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
