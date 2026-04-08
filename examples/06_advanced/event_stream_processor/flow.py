import asyncio
from collections import Counter
from datetime import datetime

from blazing import Blazing
from blazing.base import BaseService


# Simulated event data for demonstration
_event_queue = [
    {"event_type": "page_view", "user_id": 1, "page": "/home"},
    {"event_type": "click", "user_id": 2, "element": "button-signup"},
    {"event_type": "page_view", "user_id": 1, "page": "/products"},
    {"event_type": "purchase", "user_id": 3, "amount": 99.99},
    {"event_type": "page_view", "user_id": 2, "page": "/checkout"},
    {"event_type": "click", "user_id": 1, "element": "add-to-cart"},
    {"event_type": "purchase", "user_id": 1, "amount": 49.99},
]
_processed_events = []


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.service
    class EventStreamService(BaseService):
        def __init__(self, connectors):
            # In production: self._kafka = connectors.get("kafka")
            pass

        async def consume_batch(self, topic: str, batch_size: int = 100) -> list:
            """Consume batch of events from Kafka (simulated)."""
            # In production:
            # events = []
            # async for message in self._kafka.consume(topic, max_messages=batch_size):
            #     events.append(message.value)
            # return events
            await asyncio.sleep(0.1)  # Simulate network latency
            batch = _event_queue[:batch_size]
            return batch

        async def produce(self, topic: str, event: dict):
            """Produce event to Kafka (simulated)."""
            await asyncio.sleep(0.02)
            print(f"[KAFKA] Produced to {topic}: {event.get('event_type', 'unknown')}")

    @app.service
    class EventDatabase(BaseService):
        def __init__(self, connectors):
            pass

        async def insert(self, event: dict):
            """Insert processed event into database (simulated)."""
            _processed_events.append(event)
            await asyncio.sleep(0.01)

    @app.step
    async def process_event_batch(events: list, services=None):
        """Process batch of events."""
        processed = []
        for event in events:
            # Transform event
            transformed = {
                **event,
                "processed_at": datetime.now().isoformat(),
                "enriched": True,
            }
            processed.append(transformed)
        return processed

    @app.step
    async def aggregate_events(events: list, services=None):
        """Aggregate events by type."""
        event_types = Counter(e["event_type"] for e in events)
        return {"total_events": len(events), "by_type": dict(event_types)}

    @app.workflow
    async def stream_processing_job(topic: str, batch_size: int = 100, services=None):
        """Process event stream in batches."""
        # Consume batch
        events = await services["EventStreamService"].consume_batch(topic, batch_size)
        if not events:
            return {"processed": 0, "message": "No events"}
        # Process batch
        processed = await process_event_batch(events, services=services)
        # Aggregate
        stats = await aggregate_events(processed, services=services)
        # Store processed events
        for event in processed:
            await services["EventDatabase"].insert(event)
        return {"topic": topic, "processed": len(processed), "stats": stats}

    await app.publish()

    # Execute the workflow
    print("Processing event stream batch from 'user-events' topic...")
    result = await app.stream_processing_job(
        topic="user-events",
        batch_size=10
    ).wait_result()

    print(f"\nStream Processing Results:")
    print(f"  Topic: {result['topic']}")
    print(f"  Events Processed: {result['processed']}")
    print(f"  Event Type Breakdown:")
    for event_type, count in result['stats']['by_type'].items():
        print(f"    - {event_type}: {count}")

    print(f"\nTotal events stored in database: {len(_processed_events)}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
