from blazing import Blazing
from blazing.web import create_asgi_app


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def validate_input(amount: float, services=None):
        """Validate input parameters."""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount > 1000000:
            raise ValueError("Amount exceeds maximum limit")
        return amount

    @app.step
    async def calculate_fee(amount: float, services=None):
        """Calculate transaction fee."""
        if amount < 100:
            return amount * 0.05  # 5% for small amounts
        elif amount < 1000:
            return amount * 0.03  # 3% for medium amounts
        else:
            return amount * 0.01  # 1% for large amounts

    @app.endpoint(path="/transaction/calculate")
    @app.workflow
    async def calculate_transaction(amount: float, services=None):
        """
        Calculate transaction fee with validation.
        POST /transaction/calculate
        Body: {"amount": 500}
        """
        try:
            validated_amount = await validate_input(amount, services=services)
            fee = await calculate_fee(validated_amount, services=services)
            return {
                "amount": validated_amount,
                "fee": fee,
                "total": validated_amount + fee,
                "status": "success",
            }
        except ValueError as e:
            # Errors are automatically caught and returned in job status
            raise e

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="Error Handling API")

    # Run the server
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
