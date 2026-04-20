import asyncio
from datetime import datetime

from blazing import Blazing
from blazing.base import BaseService


# Simulated cache storage
_cache = {}


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.service
    class Database(BaseService):
        def __init__(self, connectors):
            pass

        async def execute(self, query, params=None):
            """Execute database query (simulated)."""
            await asyncio.sleep(0.05)
            return True  # Simulated success

    @app.service
    class CacheService(BaseService):
        def __init__(self, connectors):
            pass

        async def set(self, key: str, value: str, ttl: int = 60):
            """Set cache value (simulated)."""
            await asyncio.sleep(0.02)
            _cache[key] = value

        async def get(self, key: str):
            """Get cache value (simulated)."""
            await asyncio.sleep(0.02)
            return _cache.get(key)

    @app.step
    async def check_database_health(services=None):
        """Check database connectivity."""
        try:
            await services["Database"].execute("SELECT 1", {})
            return {"service": "database", "status": "healthy"}
        except Exception as e:
            return {"service": "database", "status": "unhealthy", "error": str(e)}

    @app.step
    async def check_cache_health(services=None):
        """Check cache connectivity."""
        try:
            await services["CacheService"].set("health_check", "ok", ttl=10)
            value = await services["CacheService"].get("health_check")
            if value == "ok":
                return {"service": "cache", "status": "healthy"}
            return {
                "service": "cache",
                "status": "unhealthy",
                "error": "Value mismatch",
            }
        except Exception as e:
            return {"service": "cache", "status": "unhealthy", "error": str(e)}

    @app.step
    async def check_external_api_health(services=None):
        """Check external API connectivity (simulated)."""
        try:
            # In production:
            # async with httpx.AsyncClient() as client:
            #     response = await client.get("https://api.example.com/health", timeout=5.0)
            #     if response.status_code == 200:
            #         return {"service": "external_api", "status": "healthy"}

            # Simulated API check
            await asyncio.sleep(0.1)
            return {"service": "external_api", "status": "healthy"}
        except Exception as e:
            return {"service": "external_api", "status": "unhealthy", "error": str(e)}

    @app.workflow
    async def health_check(services=None):
        """Run health checks for all services."""
        checks = await asyncio.gather(
            check_database_health(services=services),
            check_cache_health(services=services),
            check_external_api_health(services=services),
        )

        healthy = all(c["status"] == "healthy" for c in checks)

        return {
            "overall_status": "healthy" if healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.now().isoformat(),
        }

    await app.publish()

    # Execute the workflow
    print("Running system health check...")
    result = await app.health_check().wait_result()

    print(f"\nHealth Check Results:")
    print(f"  Overall Status: {result['overall_status'].upper()}")
    print(f"  Timestamp: {result['timestamp']}")
    print("\n  Service Status:")
    for check in result["checks"]:
        status_icon = "OK" if check["status"] == "healthy" else "FAIL"
        print(f"    [{status_icon}] {check['service']}: {check['status']}")
        if "error" in check:
            print(f"         Error: {check['error']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
