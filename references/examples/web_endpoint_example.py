"""Example: Exposing Blazing Workflows as Public HTTP Endpoints

This example shows how to wrap Blazing workflows with FastAPI endpoints
to make them publicly accessible.

Architecture:
- Internal Blazing API runs in VPC (not publicly accessible)
- FastAPI endpoints wrap workflows to make them publicly accessible
- Async execution model: POST returns job_id, client polls for results
- Separate authentication from Blazing JWT
- JSON inputs/outputs for high-level task creation

Run this example:
    1. Start Docker infrastructure:
       docker-compose up -d redis api coordinator

    2. Run this script:
       uv run python docs/examples/web_endpoint_example.py

    3. Test the endpoints:
       # Create a job
       curl -X POST http://localhost:8080/calculate \
         -H "Content-Type: application/json" \
         -H "Authorization: Bearer secret-key" \
         -d '{"user_id": 123, "multiplier": 2}'

       # Check job status
       curl http://localhost:8080/jobs/{job_id}

       # Test WebSocket (using websocat or similar)
       websocat ws://localhost:8080/calculate/ws
       {"user_id": 123, "multiplier": 2}
"""

import asyncio
import os
from fastapi.security import HTTPAuthorizationCredentials
from blazing import Blazing
from blazing.web import create_asgi_app


async def verify_api_key(credentials: HTTPAuthorizationCredentials) -> bool:
    """Simple API key authentication - replace with your auth logic."""
    if credentials is None:
        return False
    # In production, verify against database, JWT, etc.
    return credentials.credentials == "secret-key"


async def main():
    # Initialize Blazing client
    api_url = os.getenv("BLAZING_API_URL", "http://localhost:8000")
    api_token = os.getenv("BLAZING_API_TOKEN", "test-token")

    print(f"🚀 Initializing Blazing client: {api_url}")
    app = Blazing(api_url=api_url, api_token=api_token)

    # Define internal steps (not exposed as endpoints)
    @app.step
    async def fetch_user_data(user_id: int, services=None):
        """Fetch user data from database (internal step)."""
        # In production, this would query a database
        return {
            "user_id": user_id,
            "base_score": 10,
            "multiplier": 1.0
        }

    @app.step
    async def calculate_score(user_data: dict, multiplier: int, services=None):
        """Calculate user score (internal step)."""
        base = user_data["base_score"]
        factor = user_data["multiplier"]
        return int(base * factor * multiplier)

    # Define workflow exposed as public endpoint
    @app.endpoint(
        path="/calculate",
        method="POST",
        auth_handler=verify_api_key,
        enable_websocket=True  # Enable ws://host/calculate/ws
    )
    @app.workflow
    async def calculate_user_score(user_id: int, multiplier: int, services=None):
        """
        Public workflow: Calculate user score.

        This workflow is exposed at POST /calculate
        Requires Authorization: Bearer secret-key header

        Args:
            user_id: User ID to calculate score for
            multiplier: Score multiplier
        """
        user_data = await fetch_user_data(user_id, services=services)
        score = await calculate_score(user_data, multiplier, services=services)
        return {"user_id": user_id, "score": score}

    # Define another endpoint with different path
    @app.endpoint(path="/v1/scores/batch", method="POST")
    @app.workflow
    async def batch_calculate_scores(user_ids: list, multiplier: int, services=None):
        """
        Public workflow: Calculate scores for multiple users.

        This workflow is exposed at POST /v1/scores/batch
        """
        results = []
        for user_id in user_ids:
            user_data = await fetch_user_data(user_id, services=services)
            score = await calculate_score(user_data, multiplier, services=services)
            results.append({"user_id": user_id, "score": score})
        return results

    print("📝 Publishing workflows to Blazing backend...")
    await app.publish()
    print("✅ Workflows published")

    print("\n🌐 Generating FastAPI app...")
    fastapi_app = await create_asgi_app(
        app,
        title="User Score API",
        description="Public HTTP endpoints for calculating user scores",
        version="1.0.0"
    )
    print("✅ FastAPI app generated")

    print("\n" + "=" * 70)
    print("🎉 FastAPI app ready!")
    print("=" * 70)
    print("\nAvailable endpoints:")
    print("  POST /calculate              - Calculate user score (auth required)")
    print("  POST /v1/scores/batch        - Batch calculate scores")
    print("  GET  /jobs/{job_id}          - Get job status/result")
    print("  POST /jobs/{job_id}/cancel   - Cancel a job")
    print("  WS   /calculate/ws           - WebSocket for real-time updates")
    print("  GET  /health                 - Health check")
    print("\nAuthentication:")
    print("  Header: Authorization: Bearer secret-key")
    print("\nExample requests:")
    print("""
  # Create a job
  curl -X POST http://localhost:8080/calculate \\
    -H "Content-Type: application/json" \\
    -H "Authorization: Bearer secret-key" \\
    -d '{"user_id": 123, "multiplier": 2}'

  # Response: {"job_id": "...", "status": "pending", ...}

  # Check status
  curl http://localhost:8080/jobs/{job_id}

  # Response: {"job_id": "...", "status": "completed", "result": {"user_id": 123, "score": 20}}
    """)
    print("=" * 70)

    # Deploy with uvicorn
    print("\n🚀 Starting server on http://0.0.0.0:8080")
    print("Press Ctrl+C to stop\n")

    import uvicorn
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
