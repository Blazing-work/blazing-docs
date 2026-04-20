import asyncio

from blazing import Blazing


# Simulated in-memory cache for demonstration
cache = {}


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def cache_get(key: str, services=None):
        """Get value from cache."""
        return cache.get(key)

    @app.step
    async def cache_set(key: str, value: str, services=None):
        """Set value in cache."""
        cache[key] = value
        return {"cached": True, "key": key}

    @app.step
    async def expensive_computation(key: str, services=None):
        """Simulate an expensive computation."""
        print(f"[Computing] Expensive computation for key: {key}")
        await asyncio.sleep(1)  # Simulate expensive operation
        return f"computed_value_for_{key}"

    @app.workflow
    async def cached_lookup(key: str, services=None):
        """Lookup value with caching (cache-aside pattern)."""
        # Check cache first
        cached = await cache_get(key, services=services)
        if cached:
            return {"source": "cache", "value": cached}

        # Cache miss - compute and store
        value = await expensive_computation(key, services=services)
        await cache_set(key, value, services=services)
        return {"source": "computed", "value": value}

    await app.publish()

    # First lookup - cache miss, will compute
    print("First lookup for 'user_123'...")
    result1 = await app.cached_lookup(key="user_123").wait_result()
    print(f"Result: {result1}")

    # Second lookup - cache hit
    print("\nSecond lookup for 'user_123'...")
    result2 = await app.cached_lookup(key="user_123").wait_result()
    print(f"Result: {result2}")

    # Different key - cache miss
    print("\nLookup for 'user_456'...")
    result3 = await app.cached_lookup(key="user_456").wait_result()
    print(f"Result: {result3}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
