import asyncio
import random

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def fetch_sales_data(region: str, services=None):
        """Fetch sales data for region (simulated)."""
        # In production, use: data = await services["SalesDatabase"].get_by_region(region)
        # Simulate database query with random sales data
        await asyncio.sleep(0.1)  # Simulate network latency
        total = random.randint(10000, 100000)
        return {"region": region, "total": total}

    @app.workflow
    async def aggregate_sales(regions: list, services=None):
        """Aggregate sales across all regions."""
        results = await asyncio.gather(
            *[fetch_sales_data(region, services=services) for region in regions]
        )

        total_sales = sum(r["total"] for r in results)
        return {
            "by_region": results,
            "grand_total": total_sales,
            "regions_count": len(regions),
        }

    await app.publish()

    # Execute the workflow
    regions = ["North America", "Europe", "Asia Pacific", "Latin America"]
    print(f"Aggregating sales for regions: {regions}")
    result = await app.aggregate_sales(regions=regions).wait_result()

    print(f"\nResults by region:")
    for region_data in result["by_region"]:
        print(f"  {region_data['region']}: ${region_data['total']:,}")
    print(f"\nGrand Total: ${result['grand_total']:,}")
    print(f"Regions processed: {result['regions_count']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
