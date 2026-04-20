import asyncio

from blazing import Blazing
from blazing.base import BaseService


# Simulated in-memory database for demonstration
_users_db = {
    1: {"id": 1, "name": "Alice Smith", "email": "alice@example.com"},
    2: {"id": 2, "name": "Bob Jones", "email": "bob@example.com"},
}
_orders_db = {
    1: [
        {"order_id": "ORD-001", "amount": 99.99},
        {"order_id": "ORD-002", "amount": 149.99},
    ],
    2: [
        {"order_id": "ORD-003", "amount": 49.99},
    ],
}
_recommendations_db = {
    1: [{"product_id": "P001"}, {"product_id": "P002"}, {"product_id": "P003"}],
    2: [{"product_id": "P004"}],
}


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # YOUR CODE (trusted - provides data access)
    @app.service
    class DataService(BaseService):
        def __init__(self, connectors):
            # In production: self._db = connectors.get("postgres")
            pass

        async def fetch_user(self, user_id: int) -> dict:
            """Fetch single user (simulated)."""
            await asyncio.sleep(0.1)  # Simulate DB latency
            if user_id in _users_db:
                return _users_db[user_id]
            raise ValueError(f"User {user_id} not found")

        async def fetch_orders(self, user_id: int) -> list:
            """Fetch user's orders (simulated)."""
            await asyncio.sleep(0.15)  # Simulate DB latency
            return _orders_db.get(user_id, [])

        async def fetch_recommendations(self, user_id: int) -> list:
            """Fetch user's recommendations (simulated)."""
            await asyncio.sleep(0.08)  # Simulate DB latency
            return _recommendations_db.get(user_id, [])

    # USER CODE (untrusted - makes concurrent service calls)
    @app.step
    async def analyze_user(user_id: int, services=None):
        """
        User-provided analysis with concurrent service calls.
        Runs in WASM sandbox but can call services concurrently.
        """
        # Fetch all data concurrently (service calls execute on trusted workers)
        user, orders, recommendations = await asyncio.gather(
            services["DataService"].fetch_user(user_id),
            services["DataService"].fetch_orders(user_id),
            services["DataService"].fetch_recommendations(user_id),
        )
        # Process in sandbox
        total_spent = sum(order["amount"] for order in orders)
        avg_order = total_spent / len(orders) if orders else 0
        return {
            "user_id": user_id,
            "name": user["name"],
            "total_orders": len(orders),
            "total_spent": round(total_spent, 2),
            "avg_order": round(avg_order, 2),
            "recommendations_count": len(recommendations),
        }

    # YOUR CODE (trusted - orchestrates)
    @app.workflow
    async def user_report(user_id: int, services=None):
        """Generate user report using user's analysis logic."""
        return await analyze_user(user_id, services=services)

    await app.publish()

    # Execute the workflow for user 1
    print("Generating report for user 1 (with concurrent data fetching)...")
    result1 = await app.user_report(user_id=1).wait_result()
    print(f"\nUser Report:")
    print(f"  Name: {result1['name']}")
    print(f"  Total Orders: {result1['total_orders']}")
    print(f"  Total Spent: ${result1['total_spent']}")
    print(f"  Average Order: ${result1['avg_order']}")
    print(f"  Recommendations: {result1['recommendations_count']}")

    # Execute for user 2
    print("\nGenerating report for user 2...")
    result2 = await app.user_report(user_id=2).wait_result()
    print(f"\nUser Report:")
    print(f"  Name: {result2['name']}")
    print(f"  Total Orders: {result2['total_orders']}")
    print(f"  Total Spent: ${result2['total_spent']}")
    print(f"  Average Order: ${result2['avg_order']}")
    print(f"  Recommendations: {result2['recommendations_count']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
