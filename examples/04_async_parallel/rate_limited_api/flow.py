import asyncio
import random

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # Semaphore to limit concurrent API calls
    semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests

    @app.step
    async def rate_limited_fetch(endpoint: str, services=None):
        """Fetch from API with rate limiting using semaphore."""
        async with semaphore:
            # Simulate API call
            await asyncio.sleep(0.5)  # Simulate network latency
            return {
                "endpoint": endpoint,
                "status": "success",
                "data": {"value": random.randint(1, 100)},
            }

    @app.workflow
    async def fetch_multiple_endpoints(endpoints: list, services=None):
        """Fetch multiple API endpoints with rate limiting."""
        # Without rate limiting, all requests would fire at once
        # With semaphore, only 3 run concurrently
        tasks = [rate_limited_fetch(endpoint, services=services) for endpoint in endpoints]
        results = await asyncio.gather(*tasks)
        return {"fetched_count": len(results), "results": results}

    await app.publish()

    # Execute the workflow with 10 endpoints but only 3 concurrent
    endpoints = [f"endpoint_{i}" for i in range(10)]
    print(f"Fetching {len(endpoints)} endpoints with rate limit of 3 concurrent...")

    result = await app.fetch_multiple_endpoints(endpoints=endpoints).wait_result()

    print(f"\nFetched {result['fetched_count']} endpoints:")
    for item in result["results"][:3]:  # Show first 3
        print(f"  {item['endpoint']}: {item['data']}")
    print("  ...")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
