# Getting Started with Blazing

This tutorial provides a step-by-step guide to building your first Blazing pipeline. We'll create a simple application that fetches data from a public API, processes it, and prints the result.

## Prerequisites

Before you begin, ensure you have the following installed:

- Python 3.11+
- Redis (or KeyDB) running on `localhost:6379` (or accessible to your application). You can use Docker for a quick setup:
  ```bash
  docker run -d --name redis -p 6379:6379 redis/redis-stack
  ```
- `uv` (or `pip`) for package installation.

## Step 1: Project Setup

First, let's set up your project directory and install Blazing.

```bash
mkdir blazing-tutorial
cd blazing-tutorial
uv venv
source .venv/bin/activate
uv pip install blazing
```

*Note: When developing locally, replace the final command with `uv pip install /path/to/blazing` to install from the cloned repository.*

## Step 2: Create Your First Blazing App

Create a file named `main.py`. This file will contain your Blazing application and pipeline definition.

```python
import asyncio
from blazing import Blazing

# Initialize the Blazing app
# This assumes Redis is running on localhost:6379.
# For production, you would use a more robust configuration.
app = Blazing(redis_config={"host": "localhost", "port": 6379})

if __name__ == "__main__":
    async def main():
        # Publish the workflows and steps to Redis
        async with app:
            await app.publish()
        print("Blazing workflows and steps have been published.")

    asyncio.run(main())
```

This script initializes the Blazing application and connects to Redis. The `app.publish()` command registers all your defined workflows and steps with Redis.

Run this script to ensure your connection to Redis is working:

```bash
python main.py
```

You should see the message "Blazing workflows and steps have been published."

## Step 3: Define a Step

Steps are the building blocks of your pipeline. Let's create a step that fetches data from a public API. We'll use the [JSONPlaceholder API](https://jsonplaceholder.typicode.com/) for this example.

First, install `httpx` for making async HTTP requests:

```bash
uv pip install httpx
```

Now, add the following to your `main.py`:

```python
import asyncio
import httpx
from blazing import Blazing

# Initialize the Blazing app
app = Blazing(redis_config={"host": "localhost", "port": 6379})

@app.step
async def fetch_post(post_id: int, services=None):
    """Fetches a single post from the JSONPlaceholder API."""
    print(f"Fetching post {post_id}...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://jsonplaceholder.typicode.com/posts/{post_id}")
        response.raise_for_status()
        return response.json()

# ... (rest of the file)
```

We've defined an `async` step called `fetch_post`. It takes a `post_id` and fetches the corresponding post.

## Step 4: Define a Workflow

A workflow defines the orchestration logic of your pipeline. It calls one or more steps. Let's create a workflow that uses our `fetch_post` station.

Add the following to `main.py`:

```python
# ... (imports and app initialization)

@app.step
async def fetch_post(post_id: int, services=None):
    # ... (station implementation)

@app.workflow
async def simple_pipeline(post_id: int, services=None):
    """A simple pipeline that fetches a post."""
    print(f"Starting pipeline for post {post_id}")
    post_data = await fetch_post(post_id)
    print("Pipeline finished. Post title:", post_data.get("title"))
    return post_data

# ... (main function)
```

Our `simple_pipeline` route takes a `post_id`, calls the `fetch_post` station, and then prints the title of the fetched post.

## Step 5: Run the Pipeline

To run the pipeline, you need to start the Blazing runtime (Coordinator) and then create a task for your workflow.

The `architecture.md` document mentions `scripts/start_coordinator.py`. For this tutorial, we'll assume you have it running in a terminal.

1.  **Start Coordinator:**
    ```bash
    # In terminal 1
    python /path/to/blazing/src/blazing/scripts/start_coordinator.py
    ```

2.  **Create a Task:**

    Now, we need a script to trigger our pipeline. Create a new file `trigger.py`:

    ```python
    import asyncio
    from main import app # Import the app instance from your main.py

    async def run_task():
        post_id_to_fetch = 1
        print(f"Creating task for pipeline 'simple_pipeline' with post_id={post_id_to_fetch}")

        # Create a task for the route
        unit = await app.run("simple_pipeline", post_id=post_id_to_fetch)

        # Wait for the result
        result = await unit.wait_for_result()

        print("\n--- Pipeline Result ---")
        print(result)
        print("-----------------------")

    if __name__ == "__main__":
        asyncio.run(run_task())
    ```

3.  **Run the trigger script:**

    ```bash
    # In terminal 2
    python trigger.py
    ```

You should see output in the Coordinator's terminal indicating that the `fetch_post` station was executed, and the final result will be printed in the trigger script's terminal.

## Next Steps

Congratulations! You've built and run your first Blazing pipeline.

From here, you can explore more advanced features:

-   **Services:** For managing shared resources like database connections.
-   **Blocking Workers:** For CPU-intensive tasks.
-   **Error Handling:** Building resilient pipelines.
-   **Deployment:** Running Blazing in production environments.

Refer to the other documents in this directory for more in-depth information on these topics.
