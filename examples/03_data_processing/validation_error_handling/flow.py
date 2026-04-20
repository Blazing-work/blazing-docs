import re
import random

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def validate_email(email: str, services=None):
        """Validate email format."""
        pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(pattern, email):
            raise ValueError(f"Invalid email: {email}")
        return {"valid": True, "email": email}

    @app.workflow
    async def process_user_registration(email: str, name: str, services=None):
        """Register user with validation."""
        try:
            # Validate email
            await validate_email(email, services=services)

            # In production, use: user_id = await services["UserDatabase"].create_user(name, email)
            user_id = random.randint(1000, 9999)

            # In production, use: await services["EmailService"].send(email, "Welcome!", f"Hello {name}")
            print(f"[Simulated] Sending welcome email to {email}")

            return {"success": True, "user_id": user_id}
        except ValueError as e:
            return {"success": False, "error": str(e)}

    await app.publish()

    # Test with valid email
    print("Testing with valid email...")
    result = await app.process_user_registration(
        email="john@example.com", name="John Doe"
    ).wait_result()
    print(f"Result: {result}")

    # Test with invalid email
    print("\nTesting with invalid email...")
    result = await app.process_user_registration(
        email="invalid-email", name="Jane Doe"
    ).wait_result()
    print(f"Result: {result}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
