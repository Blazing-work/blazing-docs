import asyncio
import hashlib
import hmac
import json

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # Simulated secret for demonstration
    WEBHOOK_SECRET = "github_webhook_secret_demo"

    @app.step
    async def validate_github_signature(payload: str, signature: str, services=None):
        """Validate GitHub webhook signature."""
        # In production:
        # secret = await services["ConfigService"].get("github_webhook_secret")

        expected = hmac.new(
            WEBHOOK_SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(f"sha256={expected}", signature):
            raise ValueError("Invalid signature")

        print("[GITHUB] Signature validated successfully")
        return json.loads(payload)

    @app.step
    async def process_pull_request(pr_data: dict, services=None):
        """Process pull request event (simulated)."""
        action = pr_data["action"]
        title = pr_data["title"]
        user = pr_data["user"]

        if action == "opened":
            # In production:
            # await services["SlackService"].notify(f"New PR: {title} by {user}")
            print(f"[SLACK] Notified: New PR '{title}' by {user}")

        await asyncio.sleep(0.1)  # Simulate processing
        return {"processed": True, "action": action, "pr_title": title}

    @app.step
    async def process_push(push_data: dict, services=None):
        """Process push event (simulated)."""
        branch = push_data["ref"]
        commits = push_data["commits"]
        pusher = push_data["pusher"]

        print(f"[PUSH] {pusher} pushed {len(commits)} commit(s) to {branch}")
        await asyncio.sleep(0.1)
        return {"processed": True, "branch": branch, "commit_count": len(commits)}

    @app.workflow
    async def handle_github_webhook(payload: str, signature: str, services=None):
        """Handle GitHub webhook."""
        validated = await validate_github_signature(
            payload, signature, services=services
        )

        event_type = validated.get("event_type", "unknown")
        result = {"event_type": event_type, "processed": False}

        if event_type == "pull_request":
            result = await process_pull_request(validated["data"], services=services)
        elif event_type == "push":
            result = await process_push(validated["data"], services=services)

        return result

    await app.publish()

    # Test 1: Pull Request webhook
    pr_payload = json.dumps({
        "event_type": "pull_request",
        "data": {
            "action": "opened",
            "title": "Add new feature",
            "user": "developer123",
            "number": 42
        }
    })
    pr_signature = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), pr_payload.encode(), hashlib.sha256
    ).hexdigest()

    print("Processing Pull Request webhook...")
    pr_result = await app.handle_github_webhook(
        payload=pr_payload,
        signature=pr_signature
    ).wait_result()

    print(f"  Action: {pr_result.get('action', 'N/A')}")
    print(f"  PR Title: {pr_result.get('pr_title', 'N/A')}")
    print(f"  Processed: {pr_result.get('processed', False)}")

    # Test 2: Push webhook
    push_payload = json.dumps({
        "event_type": "push",
        "data": {
            "ref": "refs/heads/main",
            "commits": [{"id": "abc123"}, {"id": "def456"}],
            "pusher": "developer456"
        }
    })
    push_signature = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), push_payload.encode(), hashlib.sha256
    ).hexdigest()

    print("\nProcessing Push webhook...")
    push_result = await app.handle_github_webhook(
        payload=push_payload,
        signature=push_signature
    ).wait_result()

    print(f"  Branch: {push_result.get('branch', 'N/A')}")
    print(f"  Commits: {push_result.get('commit_count', 0)}")
    print(f"  Processed: {push_result.get('processed', False)}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
