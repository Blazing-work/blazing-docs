import asyncio
import time

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # =========================================================================
    # CPU-INTENSIVE STEPS - Use step_type='BLOCKING'
    # =========================================================================

    @app.step(step_type="BLOCKING")
    async def compute_fibonacci(n: int, services=None):
        """
        CPU-INTENSIVE: Use BLOCKING workers.

        BLOCKING workers run in dedicated threads and don't block
        the async event loop. Use for:
        - Mathematical computations
        - Data processing algorithms
        - Image/video processing
        - Cryptographic operations
        """

        def fib(x):
            if x <= 1:
                return x
            return fib(x - 1) + fib(x - 2)

        start = time.time()
        result = fib(n)
        duration = time.time() - start

        return {
            "result": result,
            "duration_seconds": duration,
            "worker_type": "BLOCKING",
        }

    @app.step(step_type="BLOCKING")
    async def process_large_array(size: int, services=None):
        """
        CPU-INTENSIVE: Matrix operations.

        BLOCKING workers prevent this CPU work from blocking
        other async operations in the system.
        """
        import numpy as np

        start = time.time()

        # CPU-intensive matrix operations
        matrix = np.random.randn(size, size)
        result = np.linalg.inv(matrix @ matrix.T + np.eye(size))
        eigenvalues = np.linalg.eigvals(result)

        duration = time.time() - start

        return {
            "matrix_size": size,
            "max_eigenvalue": float(eigenvalues.max()),
            "duration_seconds": duration,
            "worker_type": "BLOCKING",
        }

    # =========================================================================
    # I/O-BOUND STEPS - Use default (NON_BLOCKING)
    # =========================================================================

    @app.step  # Default: step_type='NON_BLOCKING'
    async def fetch_from_api(url: str, services=None):
        """
        I/O-BOUND: Use NON_BLOCKING workers (default).

        NON_BLOCKING workers use async I/O and can handle
        many concurrent operations efficiently. Use for:
        - HTTP API calls
        - Database queries
        - File I/O
        - Network operations
        """
        import httpx

        start = time.time()

        # Async I/O operation
        async with httpx.AsyncClient() as client:
            response = await client.get(url)

        duration = time.time() - start

        return {
            "url": url,
            "status_code": response.status_code,
            "duration_seconds": duration,
            "worker_type": "NON_BLOCKING",
        }

    @app.step  # Default: NON_BLOCKING
    async def fetch_multiple_apis(urls: list, services=None):
        """
        I/O-BOUND: Concurrent API calls.

        NON_BLOCKING workers excel at concurrent I/O.
        Multiple requests run in parallel without blocking.
        """
        import httpx

        start = time.time()

        async with httpx.AsyncClient() as client:
            # All requests run concurrently
            tasks = [client.get(url) for url in urls]
            responses = await asyncio.gather(*tasks)

        duration = time.time() - start

        return {
            "url_count": len(urls),
            "statuses": [r.status_code for r in responses],
            "duration_seconds": duration,
            "avg_per_request": duration / len(urls),
            "worker_type": "NON_BLOCKING",
        }

    # =========================================================================
    # WORKFLOW - Combines CPU and I/O work optimally
    # =========================================================================

    @app.workflow
    async def mixed_workload(services=None):
        """
        Workflow demonstrating optimal worker type usage.

        Performance impact:
        - CPU work on BLOCKING: Doesn't block async operations ✓
        - I/O work on NON_BLOCKING: Efficient concurrency ✓
        - Mixed workload: Best of both worlds ✓
        """
        # I/O-bound work (fast, async, concurrent)
        api_results = await fetch_multiple_apis(
            [
                "https://httpbin.org/delay/1",
                "https://httpbin.org/delay/1",
                "https://httpbin.org/delay/1",
            ],
            services=services,
        )

        # CPU-bound work (doesn't block the I/O operations)
        fib_result = await compute_fibonacci(30, services=services)

        # More CPU-bound work (runs in parallel with other BLOCKING work)
        matrix_result = await process_large_array(100, services=services)

        return {
            "api_calls": api_results,
            "fibonacci": fib_result,
            "matrix_ops": matrix_result,
            "total_duration": (
                api_results["duration_seconds"]
                + fib_result["duration_seconds"]
                + matrix_result["duration_seconds"]
            ),
        }

    await app.publish()

    print("\nRunning optimized mixed workload...")
    print("   - I/O work: NON_BLOCKING workers (concurrent)")
    print("   - CPU work: BLOCKING workers (doesn't block I/O)")

    result = await app.mixed_workload().wait_result()

    print("\nWorkflow complete!")
    print("\nResults:")
    print(f"   API calls: {result['api_calls']['url_count']} concurrent requests")
    print(f"   API duration: {result['api_calls']['duration_seconds']:.2f}s")
    print(f"   Fibonacci(30): {result['fibonacci']['result']}")
    print(f"   Fibonacci duration: {result['fibonacci']['duration_seconds']:.2f}s")
    print(
        f"   Matrix size: {result['matrix_ops']['matrix_size']}x{result['matrix_ops']['matrix_size']}"
    )
    print(f"   Matrix duration: {result['matrix_ops']['duration_seconds']:.2f}s")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
