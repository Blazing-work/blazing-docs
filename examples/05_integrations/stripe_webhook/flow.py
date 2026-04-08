import asyncio
import hashlib
import hmac
import json

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # Simulated secret for demonstration
    WEBHOOK_SECRET = "whsec_demo_secret_key"

    @app.step
    async def verify_stripe_signature(payload: str, signature: str, services=None):
        """Verify Stripe webhook signature (simulated)."""
        # In production with stripe library:
        # endpoint_secret = await services["ConfigService"].get("stripe_webhook_secret")
        # try:
        #     event = stripe.Webhook.construct_event(payload, signature, endpoint_secret)
        #     return event
        # except ValueError as err:
        #     raise ValueError("Invalid payload") from err
        # except stripe.error.SignatureVerificationError as err:
        #     raise ValueError("Invalid signature") from err

        # Simulated verification
        expected = hmac.new(
            WEBHOOK_SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

        if signature != f"sha256={expected}":
            raise ValueError("Invalid signature")

        print("[STRIPE] Signature verified successfully")
        return json.loads(payload)

    @app.step
    async def handle_payment_success(payment_intent: dict, services=None):
        """Handle successful payment (simulated)."""
        order_id = payment_intent["metadata"]["order_id"]
        email = payment_intent["receipt_email"]

        # In production:
        # await services["OrderDatabase"].mark_paid(order_id)
        # await services["EmailService"].send_receipt(email)

        print(f"[ORDER] Marked order {order_id} as paid")
        print(f"[EMAIL] Sent receipt to {email}")
        await asyncio.sleep(0.1)  # Simulate processing

        return {"order_id": order_id, "status": "paid"}

    @app.workflow
    async def process_stripe_webhook(payload: str, signature: str, services=None):
        """Process Stripe webhook event."""
        event = await verify_stripe_signature(payload, signature, services=services)

        result = {"event_type": event["type"], "processed": False}

        if event["type"] == "payment_intent.succeeded":
            result = await handle_payment_success(
                event["data"]["object"], services=services
            )
            result["processed"] = True

        return result

    await app.publish()

    # Simulate a Stripe webhook payload
    test_payload = json.dumps({
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_1234567890",
                "amount": 2999,
                "currency": "usd",
                "metadata": {"order_id": "ORD-12345"},
                "receipt_email": "customer@example.com"
            }
        }
    })

    # Generate valid signature for test
    test_signature = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), test_payload.encode(), hashlib.sha256
    ).hexdigest()

    # Execute the workflow
    print("Processing Stripe webhook...")
    result = await app.process_stripe_webhook(
        payload=test_payload,
        signature=test_signature
    ).wait_result()

    print(f"\nWebhook processed:")
    print(f"  Order ID: {result.get('order_id', 'N/A')}")
    print(f"  Status: {result.get('status', 'N/A')}")
    print(f"  Processed: {result.get('processed', False)}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
