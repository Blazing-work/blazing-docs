"""CLI Publish & Deploy Example

This file demonstrates a simple Blazing workflow that can be published
using the Blazing CLI.

To publish this workflow:
    blazing publish --app flow:app

Or set environment variables and auto-discover:
    export BLAZING_API_URL=https://api.blazing.example.com
    export BLAZING_API_TOKEN=your-token-here
    blazing publish

Documentation: https://blazing.work/docs/cli/reference#blazing-publish
Related Examples: scheduling_workflow, autoscaling_config
"""

from blazing import Blazing

# Create the Blazing app instance
# This will be discovered by the CLI
app = Blazing()


@app.step
async def process_order(order_id: str, amount: float, services=None):
    """Process a customer order."""
    # Simulate order processing
    return {
        "order_id": order_id,
        "amount": amount,
        "status": "processed",
        "fee": amount * 0.03,
        "total": amount * 1.03,
    }


@app.step
async def send_confirmation(order_info: dict, services=None):
    """Send order confirmation email."""
    # Simulate sending email
    return {
        "order_id": order_info["order_id"],
        "email_sent": True,
        "recipient": "customer@example.com",
    }


@app.workflow
async def order_workflow(order_id: str, amount: float, services=None):
    """
    Complete order processing workflow.

    Args:
        order_id: Unique order identifier
        amount: Order amount in dollars

    Returns:
        Order processing result with confirmation
    """
    # Process the order
    order_info = await process_order(order_id, amount, services=services)

    # Send confirmation email
    confirmation = await send_confirmation(order_info, services=services)

    return {
        "order": order_info,
        "confirmation": confirmation,
        "workflow_status": "completed",
    }


# For local testing only - not needed when using CLI
if __name__ == "__main__":
    import asyncio

    async def test_local():
        await app.publish()
        result = await app.order_workflow("ORDER-123", 99.99).wait_result()
        print(result)

    asyncio.run(test_local())
