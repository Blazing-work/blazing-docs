import asyncio

from blazing import Blazing


# Simulated in-memory queue for demonstration
email_queue = []


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def enqueue_email(to: str, subject: str, body: str, services=None):
        """Add email to queue."""
        email = {"to": to, "subject": subject, "body": body}
        email_queue.append(email)
        return {"queued": True, "to": to}

    @app.step
    async def send_queued_email(services=None):
        """Process one email from queue."""
        if email_queue:
            email = email_queue.pop(0)
            # In production: await services["SMTPService"].send(email)
            print(f"[Simulated] Sending email to {email['to']}: {email['subject']}")
            await asyncio.sleep(0.1)  # Simulate sending
            return {"sent": True, "to": email["to"]}
        return {"sent": False, "reason": "queue_empty"}

    @app.workflow
    async def process_email_queue(batch_size: int = 10, services=None):
        """Process email queue in batches."""
        results = await asyncio.gather(
            *[send_queued_email(services=services) for _ in range(batch_size)]
        )
        sent_count = sum(1 for r in results if r["sent"])
        return {"processed": batch_size, "sent": sent_count}

    await app.publish()

    # First, queue some emails
    print("Queueing 5 emails...")
    for i in range(5):
        await app.enqueue_email(
            to=f"user{i}@example.com",
            subject=f"Test Email {i}",
            body=f"This is test email {i}"
        ).wait_result()

    print(f"\nQueue has {len(email_queue)} emails")

    # Process the queue
    print("\nProcessing email queue (batch of 10)...")
    result = await app.process_email_queue(batch_size=10).wait_result()

    print(f"\nResults:")
    print(f"  Processed: {result['processed']}")
    print(f"  Sent: {result['sent']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
