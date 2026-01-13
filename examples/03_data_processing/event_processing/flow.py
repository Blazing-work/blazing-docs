from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def validate_event(event: dict, services=None):
        """Validate event structure."""
        required = ["event_type", "user_id", "timestamp"]
        if not all(k in event for k in required):
            raise ValueError("Invalid event structure")
        return event

    @app.step
    async def enrich_event(event: dict, services=None):
        """Enrich event with user data (simulated)."""
        # In production, use: user = await services["UserDatabase"].get_user(event["user_id"])
        user_id = event["user_id"]
        return {
            **event,
            "user_name": f"User {user_id}",
            "user_email": f"user{user_id}@example.com",
        }

    @app.step
    async def store_event(event: dict, services=None):
        """Store event in analytics database (simulated)."""
        # In production, use: await services["EventDatabase"].insert(event)
        return {"stored": True, "event_id": event.get("id", "evt_001")}

    @app.workflow
    async def process_event(event: dict, services=None):
        """Process incoming event."""
        validated = await validate_event(event, services=services)
        enriched = await enrich_event(validated, services=services)
        result = await store_event(enriched, services=services)
        return result

    await app.publish()

    # Execute the workflow
    sample_event = {
        "id": "evt_001",
        "event_type": "page_view",
        "user_id": 123,
        "timestamp": "2025-12-10T10:00:00Z",
        "page": "/products",
    }
    print(f"Processing event: {sample_event}")
    result = await app.process_event(event=sample_event).wait_result()
    print(f"Result: {result}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
