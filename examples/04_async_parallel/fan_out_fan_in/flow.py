import asyncio

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def fetch_user_data(user_id: int, services=None):
        """Fetch user data (simulated)."""
        await asyncio.sleep(0.3)  # Simulate DB query
        return {"id": user_id, "name": f"User {user_id}", "email": f"user{user_id}@example.com"}

    @app.step
    async def fetch_user_orders(user_id: int, services=None):
        """Fetch user orders (simulated)."""
        await asyncio.sleep(0.5)  # Simulate DB query
        return [
            {"order_id": f"ORD-{user_id}-001", "total": 99.99},
            {"order_id": f"ORD-{user_id}-002", "total": 149.99},
        ]

    @app.step
    async def fetch_user_preferences(user_id: int, services=None):
        """Fetch user preferences (simulated)."""
        await asyncio.sleep(0.2)  # Simulate API call
        return {"theme": "dark", "notifications": True, "language": "en"}

    @app.workflow
    async def get_user_profile(user_id: int, services=None):
        """Fetch all user data in parallel (fan-out), then combine (fan-in)."""
        # FAN-OUT: All three fetches run in parallel
        user, orders, prefs = await asyncio.gather(
            fetch_user_data(user_id, services=services),
            fetch_user_orders(user_id, services=services),
            fetch_user_preferences(user_id, services=services),
        )
        # FAN-IN: Combine results
        return {"user": user, "orders": orders, "preferences": prefs}

    await app.publish()

    # Execute the workflow
    print("Fetching user profile (fan-out / fan-in pattern)...")
    print("  - fetch_user_data (0.3s)")
    print("  - fetch_user_orders (0.5s)")
    print("  - fetch_user_preferences (0.2s)")
    print("  Total sequential time: 1.0s")
    print("  Expected parallel time: ~0.5s (longest task)\n")

    import time
    start = time.time()
    result = await app.get_user_profile(user_id=123).wait_result()
    duration = time.time() - start

    print(f"User Profile fetched in {duration:.2f}s:")
    print(f"  User: {result['user']['name']} ({result['user']['email']})")
    print(f"  Orders: {len(result['orders'])} orders")
    print(f"  Preferences: {result['preferences']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
