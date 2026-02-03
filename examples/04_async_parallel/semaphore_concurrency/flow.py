"""Semaphore Concurrency Example

Demonstrates using Blazing Semaphore to limit concurrent execution
and prevent resource exhaustion.

Documentation: https://blazing.work/docs/async-parallel/concurrency
Related Examples: endpoint_routing, service_injection
"""

from blazing import Blazing, Semaphore
import asyncio


async def main():
    app = Blazing()

    # Create a semaphore to limit concurrent database queries
    # Only 2 queries can run simultaneously
    db_semaphore = Semaphore(2)

    @app.step
    async def fetch_user_profile(user_id: int, services=None):
        """Simulate fetching a user profile from database."""
        async with db_semaphore:
            print(f"Fetching user {user_id}...")
            await asyncio.sleep(1)  # Simulate database query
            return {
                "user_id": user_id,
                "name": f"User{user_id}",
                "status": "active",
            }

    @app.step
    async def enrich_profile(profile: dict, services=None):
        """Add computed fields to profile."""
        profile["display_name"] = f"{profile['name']} (ID: {profile['user_id']})"
        return profile

    @app.workflow
    async def fetch_multiple_users(user_ids: list, services=None):
        """Fetch multiple user profiles with bounded concurrency."""
        # Fan-out: fetch all profiles in parallel, but limited by semaphore
        fetch_tasks = [
            fetch_user_profile(user_id, services=services) for user_id in user_ids
        ]
        profiles = await asyncio.gather(*fetch_tasks)

        # Enrich each profile
        enrich_tasks = [
            enrich_profile(profile, services=services) for profile in profiles
        ]
        enriched = await asyncio.gather(*enrich_tasks)

        return {
            "count": len(enriched),
            "profiles": enriched,
        }

    await app.publish()

    # Fetch 5 users - only 2 will run concurrently due to semaphore
    user_ids = [1, 2, 3, 4, 5]
    print(f"Fetching {len(user_ids)} users with max concurrency of 2...")

    result = await app.fetch_multiple_users(user_ids).wait_result()
    print(f"\nFetched {result['count']} users:")
    for profile in result["profiles"]:
        print(f"  - {profile['display_name']}")


if __name__ == "__main__":
    asyncio.run(main())
