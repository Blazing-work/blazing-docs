"""
Example Blazing app for testing CLI.
"""

from blazing import Blazing, BaseService

# Create app (credentials will be provided by CLI)
app = Blazing(
    api_url="http://localhost:8080",
    api_token="test-token"
)


@app.service(version="1.0")
class ExampleService(BaseService):
    """Example service for demo."""

    def __init__(self, connector_instances):
        self.connector_instances = connector_instances

    async def process_data(self, data):
        """Process some data."""
        return f"Processed: {data}"


@app.route
async def hello_world(name: str, services=None):
    """Simple hello world route."""
    return f"Hello, {name}!"


@app.route
async def process_with_service(data: str, services=None):
    """Route that uses a service."""
    result = await services["ExampleService"].process_data(data)
    return result


if __name__ == "__main__":
    # This would be used for local development/testing
    import asyncio
    asyncio.run(app.publish())
    print("✓ Published successfully!")
