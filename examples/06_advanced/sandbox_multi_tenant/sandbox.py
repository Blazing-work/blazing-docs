import asyncio

from blazing import Blazing
from blazing.base import BaseService


# Simulated multi-tenant database
_tenant_data = {
    "tenant_a": [
        {"value": 10, "category": "sales"},
        {"value": 20, "category": "marketing"},
    ],
    "tenant_b": [
        {"value": 5, "category": "sales"},
        {"value": 15, "category": "engineering"},
    ],
}
_tenant_results = {}


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # YOUR CODE (trusted - manages tenant data)
    @app.service
    class TenantDataService(BaseService):
        def __init__(self, connectors):
            # In production: self._db = connectors.get("postgres")
            pass

        async def get_tenant_data(self, tenant_id: str) -> list:
            """Fetch data for specific tenant (simulated)."""
            # In production:
            # query = text("""
            #     SELECT * FROM data
            #     WHERE tenant_id = :tenant_id
            #     AND deleted_at IS NULL
            # """)
            # result = await self._db.execute(query, {"tenant_id": tenant_id})
            # return [dict(row) for row in result]
            await asyncio.sleep(0.1)  # Simulate DB latency
            return _tenant_data.get(tenant_id, [])

        async def save_tenant_results(self, tenant_id: str, results: list):
            """Save processed results for tenant (simulated)."""
            # In production:
            # for item in results:
            #     query = text("""
            #         INSERT INTO results (tenant_id, data, created_at)
            #         VALUES (:tenant_id, :data, NOW())
            #     """)
            #     await self._db.execute(query, ...)
            # await self._db.commit()
            _tenant_results[tenant_id] = results
            print(f"[DB] Saved {len(results)} results for {tenant_id}")
            await asyncio.sleep(0.1)

    # TENANT A's CODE (untrusted - runs in WASM)
    @app.step
    async def tenant_a_transform(tenant_id: str, services=None):
        """Tenant A's custom transformation logic."""
        data = await services["TenantDataService"].get_tenant_data(tenant_id)
        # Tenant A's processing logic - DOUBLE values
        results = [{"value": item["value"] * 2, "label": "doubled"} for item in data]
        await services["TenantDataService"].save_tenant_results(tenant_id, results)
        return {"processed": len(results), "tenant": tenant_id, "algorithm": "doubled"}

    # TENANT B's CODE (untrusted - runs in WASM)
    @app.step
    async def tenant_b_transform(tenant_id: str, services=None):
        """Tenant B's custom transformation logic (different from Tenant A)."""
        data = await services["TenantDataService"].get_tenant_data(tenant_id)
        # Tenant B's processing logic - SQUARE values
        results = [{"value": item["value"] ** 2, "label": "squared"} for item in data]
        await services["TenantDataService"].save_tenant_results(tenant_id, results)
        return {"processed": len(results), "tenant": tenant_id, "algorithm": "squared"}

    # YOUR CODE (trusted - routes to correct tenant code)
    @app.workflow
    async def process_tenant_data(tenant_id: str, services=None):
        """Route to correct tenant's processing logic."""
        if tenant_id == "tenant_a":
            return await tenant_a_transform(tenant_id, services=services)
        elif tenant_id == "tenant_b":
            return await tenant_b_transform(tenant_id, services=services)
        else:
            raise ValueError(f"Unknown tenant: {tenant_id}")

    await app.publish()

    # Execute for Tenant A
    print("Processing data for Tenant A...")
    result_a = await app.process_tenant_data(tenant_id="tenant_a").wait_result()
    print(f"  Tenant: {result_a['tenant']}")
    print(f"  Algorithm: {result_a['algorithm']}")
    print(f"  Records processed: {result_a['processed']}")
    print(f"  Results: {_tenant_results.get('tenant_a', [])}")

    # Execute for Tenant B
    print("\nProcessing data for Tenant B...")
    result_b = await app.process_tenant_data(tenant_id="tenant_b").wait_result()
    print(f"  Tenant: {result_b['tenant']}")
    print(f"  Algorithm: {result_b['algorithm']}")
    print(f"  Records processed: {result_b['processed']}")
    print(f"  Results: {_tenant_results.get('tenant_b', [])}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
