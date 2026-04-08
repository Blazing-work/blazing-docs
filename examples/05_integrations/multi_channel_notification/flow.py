import asyncio

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def send_email_notification(user_id: int, message: str, services=None):
        """Send email notification (simulated)."""
        await asyncio.sleep(0.2)  # Simulate API call
        print(f"[EMAIL] Sending to user {user_id}: {message}")
        return {"channel": "email", "sent": True}

    @app.step
    async def send_sms_notification(user_id: int, message: str, services=None):
        """Send SMS notification (simulated)."""
        await asyncio.sleep(0.3)  # Simulate API call
        print(f"[SMS] Sending to user {user_id}: {message}")
        return {"channel": "sms", "sent": True}

    @app.step
    async def send_push_notification(user_id: int, message: str, services=None):
        """Send push notification (simulated)."""
        await asyncio.sleep(0.1)  # Simulate API call
        print(f"[PUSH] Sending to user {user_id}: {message}")
        return {"channel": "push", "sent": True}

    @app.workflow
    async def notify_user(user_id: int, message: str, channels: list, services=None):
        """Send notification through multiple channels."""
        tasks = []
        if "email" in channels:
            tasks.append(send_email_notification(user_id, message, services=services))
        if "sms" in channels:
            tasks.append(send_sms_notification(user_id, message, services=services))
        if "push" in channels:
            tasks.append(send_push_notification(user_id, message, services=services))

        results = await asyncio.gather(*tasks)
        return {"user_id": user_id, "channels": results}

    await app.publish()

    # Execute the workflow
    print("Sending multi-channel notification to user 123...")
    result = await app.notify_user(
        user_id=123,
        message="Your order has shipped!",
        channels=["email", "sms", "push"]
    ).wait_result()

    print(f"\nNotification sent to user {result['user_id']}:")
    for channel in result["channels"]:
        print(f"  {channel['channel']}: {'Sent' if channel['sent'] else 'Failed'}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
