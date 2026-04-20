import asyncio

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def map_operation(chunk: list, services=None):
        """Map operation: process chunk."""
        return sum(x**2 for x in chunk)

    @app.step
    async def reduce_operation(results: list, services=None):
        """Reduce operation: combine results."""
        return sum(results)

    @app.workflow
    async def map_reduce_sum_of_squares(
        numbers: list, chunk_size: int = 100, services=None
    ):
        """Map-reduce pattern for sum of squares."""

        # Split into chunks (map phase)
        chunks = [
            numbers[i : i + chunk_size] for i in range(0, len(numbers), chunk_size)
        ]

        # Process chunks in parallel
        mapped_results = await asyncio.gather(
            *[map_operation(chunk, services=services) for chunk in chunks]
        )

        # Combine results (reduce phase)
        final_result = await reduce_operation(mapped_results, services=services)

        return {
            "result": final_result,
            "chunks_processed": len(chunks),
            "total_numbers": len(numbers),
        }

    await app.publish()

    # Execute the map-reduce workflow
    numbers = list(range(1, 1001))  # 1 to 1000
    print(f"Computing sum of squares for {len(numbers)} numbers...")
    result = await app.map_reduce_sum_of_squares(numbers=numbers, chunk_size=100).wait_result()

    print(f"Result: {result['result']}")
    print(f"Chunks processed: {result['chunks_processed']}")
    print(f"Total numbers: {result['total_numbers']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
