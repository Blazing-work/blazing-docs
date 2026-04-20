import asyncio

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def send_email(to: str, subject: str, body: str, services=None):
        """Send email (simulated)."""
        # In production, use SMTP connector:
        # await services["SMTPService"].send({"to": to, "subject": subject, "body": body})
        print(f"[EMAIL] To: {to}")
        print(f"[EMAIL] Subject: {subject}")
        print(f"[EMAIL] Body: {body[:50]}...")
        await asyncio.sleep(0.2)  # Simulate sending
        return {"sent": True, "to": to}

    @app.workflow
    async def send_welcome_email(user_email: str, user_name: str, services=None):
        """Send welcome email to new user."""
        subject = f"Welcome, {user_name}!"
        body = f"Hello {user_name},\n\nWelcome to our platform!\n\nBest regards,\nThe Team"
        result = await send_email(user_email, subject, body, services=services)
        return result

    await app.publish()

    # Execute the workflow
    print("Sending welcome email...")
    result = await app.send_welcome_email(
        user_email="john@example.com",
        user_name="John"
    ).wait_result()

    print(f"\nEmail {'sent successfully' if result['sent'] else 'failed'} to {result['to']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
