from datetime import datetime

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def extract(source: str, services=None):
        """Extract data from source (simulated)."""
        # In production, use: data = await services["DataSource"].fetch(source)
        # Simulate extracting data from a source
        return [
            {"id": 1, "name": "Product A", "price": 100, "valid": True},
            {"id": 2, "name": "Product B", "price": 200, "valid": True},
            {"id": 3, "name": "Invalid", "price": None, "valid": False},
            {"id": 4, "name": "Product C", "price": 150, "valid": True},
        ]

    @app.step
    async def transform(data: list, services=None):
        """Transform data."""
        # Clean, normalize, enrich
        cleaned = [d for d in data if d.get("valid")]
        enriched = [{**d, "processed_at": datetime.now().isoformat()} for d in cleaned]
        return enriched

    @app.step
    async def load(data: list, destination: str, services=None):
        """Load data to destination (simulated)."""
        # In production, use: await services["DataWarehouse"].bulk_insert(destination, data)
        print(f"[Simulated] Loading {len(data)} records to {destination}")
        return {"loaded": len(data), "destination": destination}

    @app.workflow
    async def etl_pipeline(source: str, destination: str, services=None):
        """Complete ETL pipeline."""
        raw_data = await extract(source, services=services)
        transformed = await transform(raw_data, services=services)
        result = await load(transformed, destination, services=services)
        return {
            "source": source,
            "destination": destination,
            "rows_processed": result["loaded"],
        }

    await app.publish()

    # Execute the ETL pipeline
    print("Running ETL pipeline...")
    result = await app.etl_pipeline(
        source="products_db", destination="analytics_warehouse"
    ).wait_result()

    print(f"\nETL Pipeline completed!")
    print(f"  Source: {result['source']}")
    print(f"  Destination: {result['destination']}")
    print(f"  Rows processed: {result['rows_processed']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
