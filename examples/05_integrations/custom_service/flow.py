from blazing import Blazing, BaseService
import asyncio


# Define a custom service by extending BaseService
class CacheService(BaseService):
    """
    Custom caching service for storing key-value pairs.

    This demonstrates how to extend BaseService to create
    custom integrations that can be used across workflows.
    """

    def __init__(self, connector_instances=None):
        """
        Initialize the cache service.

        Args:
            connector_instances: Optional connector instances from the runtime
        """
        self.connectors = connector_instances
        self._cache = {}  # Simple in-memory cache
        self._hits = 0
        self._misses = 0

    async def get(self, key: str):
        """Retrieve a value from the cache."""
        if key in self._cache:
            self._hits += 1
            return {"found": True, "value": self._cache[key]}
        else:
            self._misses += 1
            return {"found": False, "value": None}

    async def set(self, key: str, value: any, ttl: int = None):
        """Store a value in the cache."""
        self._cache[key] = value
        return {"success": True, "key": key}

    async def delete(self, key: str):
        """Remove a value from the cache."""
        if key in self._cache:
            del self._cache[key]
            return {"success": True, "existed": True}
        return {"success": True, "existed": False}

    async def stats(self):
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0,
        }


async def main():
    app = Blazing()

    # Register the custom service
    @app.service
    class Cache(CacheService):
        """Registered cache service."""
        pass

    @app.step
    async def fetch_user_data(user_id: int, services=None):
        """Fetch user data with caching."""
        cache_key = f"user:{user_id}"

        # Check cache first
        if services and hasattr(services, "cache"):
            cached = await services.cache.get(cache_key)
            if cached["found"]:
                print(f"Cache HIT for user {user_id}")
                return cached["value"]

        # Simulate database fetch
        print(f"Cache MISS for user {user_id} - fetching from database")
        await asyncio.sleep(0.5)  # Simulate slow database query
        user_data = {
            "user_id": user_id,
            "name": f"User{user_id}",
            "email": f"user{user_id}@example.com",
        }

        # Store in cache
        if services and hasattr(services, "cache"):
            await services.cache.set(cache_key, user_data, ttl=300)

        return user_data

    @app.workflow
    async def get_user_profile(user_id: int, services=None):
        """Get user profile with caching."""
        user_data = await fetch_user_data(user_id, services=services)
        return user_data

    @app.workflow
    async def get_cache_stats(services=None):
        """Get cache performance statistics."""
        if services and hasattr(services, "cache"):
            stats = await services.cache.stats()
            return stats
        return {"error": "Cache service not available"}

    await app.publish()

    # Execute workflows to demonstrate caching
    print("First request (cache miss):")
    result1 = await app.get_user_profile(123).wait_result()
    print(f"Result: {result1}\n")

    print("Second request (cache hit):")
    result2 = await app.get_user_profile(123).wait_result()
    print(f"Result: {result2}\n")

    print("Cache statistics:")
    stats = await app.get_cache_stats().wait_result()
    print(f"Stats: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
