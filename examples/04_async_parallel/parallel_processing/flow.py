import asyncio

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def process_item(item_id: int, services=None):
        """Process single item."""
        # Simulate processing
        result = item_id * 2
        return {"item_id": item_id, "processed_value": result}

    @app.workflow
    async def process_batch(item_ids: list, services=None):
        """Process multiple items in parallel."""
        tasks = [process_item(item_id, services=services) for item_id in item_ids]
        results = await asyncio.gather(*tasks)
        return {"processed_count": len(results), "results": results}

    await app.publish()

    # Execute the workflow
    result = await app.process_batch(item_ids=[1, 2, 3, 4, 5]).wait_result()
    print(f"Processed {result['processed_count']} items")
    for item in result["results"]:
        print(f"  Item {item['item_id']}: {item['processed_value']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
