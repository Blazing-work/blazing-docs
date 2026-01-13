from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # USER CODE (untrusted - runs in WASM sandbox)
    @app.step
    async def user_transform(data: list, services=None):
        """
        User-provided transformation logic.
        Runs in WASM sandbox - NO network, NO filesystem access.
        """
        # Pure Python computation (safe)
        return [x * 2 for x in data if x > 0]

    # YOUR CODE (trusted - orchestrates)
    @app.workflow
    async def process_data(data: list, services=None):
        """
        Your workflow that calls user code safely.
        """
        result = await user_transform(data, services=services)
        return {"transformed": result, "count": len(result)}

    await app.publish()

    # Execute (using simplest one-liner syntax)
    result = await app.process_data(data=[1, -2, 3, -4, 5]).wait_result()
    print(result)  # {"transformed": [2, 6, 10], "count": 3}


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
