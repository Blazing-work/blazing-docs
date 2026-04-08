# Blazing Developer Guide

A comprehensive guide to building async pipelines with Blazing.

## Table of Contents

1. [Introduction](#introduction)
2. [Core Concepts](#core-concepts)
3. [Getting Started](#getting-started)
4. [Defining Pipelines](#defining-pipelines)
5. [Working with Services](#working-with-services)
6. [Environment Management](#environment-management)
7. [Executing Tasks](#executing-tasks)
8. [Advanced Patterns](#advanced-patterns)
9. [Error Handling](#error-handling)
10. [Best Practices](#best-practices)
11. [Production Deployment](#production-deployment)

---

## Introduction

Blazing is a distributed async pipeline orchestration framework designed for building complex, multi-stage workflows. It excels at coordinating I/O-bound and CPU-bound tasks across distributed workers while maintaining state and providing deep observability.

### When to Use Blazing

Blazing is ideal for:

- ✅ **Multi-stage data pipelines** - ETL workflows, data processing chains
- ✅ **Financial modeling** - Backtesting, portfolio optimization, risk analysis
- ✅ **API orchestration** - Coordinating multiple external API calls
- ✅ **Long-running workflows** - Jobs that take hours or days to complete
- ✅ **Mixed workloads** - Combining fast async operations with slow blocking tasks
- ✅ **Stateful computations** - Where intermediate results need to be persisted

### Key Features

- **Declarative API**: Define pipelines with simple `@workflow` and `@step` decorators
- **Remote Execution**: Submit jobs to a distributed worker fleet via HTTP API
- **Environment Replication**: Automatic Python environment setup on workers (uv, poetry, requirements.txt, or declarative)
- **Multi-App Isolation**: JWT-based tenant separation with isolated environments and state
- **Automatic Parallelization**: Workers execute operations concurrently
- **State Persistence**: All intermediate results stored in Redis
- **Dynamic Worker Mix**: Automatically optimizes CPU/IO worker ratios
- **Services**: Reusable components with managed lifecycle (DB connections, APIs)
- **Deep Observability**: Built-in monitoring and debugging tools

---

## Core Concepts

### Workflows

A **workflow** is the entry point to your pipeline. It defines the orchestration logic - what operations to execute and in what order.

```python
@app.route
async def my_pipeline(input_data, services=None):
    """Entry point for the pipeline."""
    result = await process_step_1(input_data)
    result = await process_step_2(result)
    return result
```

**Key characteristics:**
- Workflows are always `async` functions
- Must have `services=None` as a keyword argument
- Called via `app.run()` to create a unit of work
- Can call steps and other workflows

### Steps

A **step** is a single step in your pipeline. Steps can be:
- **Non-blocking (async)**: For I/O-bound work (API calls, DB queries)
- **Blocking (sync)**: For CPU-bound work (heavy computation, data processing)

```python
@app.station
async def fetch_data(symbol: str, services=None):
    """Async station for fetching data from API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.example.com/data/{symbol}")
        return response.json()

@app.station
def compute_metrics(data, services=None):
    """Blocking station for CPU-intensive computation."""
    # Runs in a separate process worker
    return expensive_calculation(data)
```

**Key characteristics:**
- Can be async (I/O-bound) or sync (CPU-bound)
- Must have `services=None` as a keyword argument
- Automatically distributed to workers
- Results are cached in Redis

### Services

**Services** are reusable components that provide shared resources to your pipeline. Common use cases:
- Database connections
- API clients with authentication
- Shared configuration
- Stateful services

```python
from blazing import BaseService

class DatabaseService(BaseService):
    async def connect(self):
        """Called once when service initializes."""
        self.db = await create_db_connection()

    async def query(self, sql):
        """Method available to all steps."""
        return await self.db.execute(sql)

    async def disconnect(self):
        """Called when service is torn down."""
        await self.db.close()
```

**Key characteristics:**
- Singleton per worker process
- Automatic lifecycle management (`connect()` → use → `disconnect()`)
- Injected into all workflows/stations via `services` parameter

### Units

A **unit** is a single instance of a route execution. When you call `app.run()`, Blazing creates a unit that tracks:
- Execution state (queued → running → completed/failed)
- All operation results
- Errors and retry counts
- Timing information

---

## Getting Started

### Installation

```bash
pip install blazing
```

### Initialize Blazing App (Remote Mode)

For production use, simply provide your API token:

```python
from blazing import Blazing

app = Blazing(api_token="your-api-token")
```

Blazing automatically connects to the production service backend with built-in redundancy to handle DNS failures. The client will try multiple API endpoints for high availability.

**For local testing only**, you can override the API URL:

```python
# Testing/development only - not for production use
app = Blazing(
    api_token="dev-token",
    api_url="http://localhost:8080"  # Override for local testing
)
```

### Declarative Dependencies (Recommended)

**New in v2.0**: Specify Python version and dependencies directly in code - no local environment setup required!

```python
app = Blazing(
    api_token="your-api-token",
    python_version="3.11",  # Optional, defaults to current Python
    dependencies=[
        "torch==2.7.1",
        "numpy>=1.24.0",
        "pandas<2.0.0",
        "httpx>=0.25.0",
    ]
)
```

**Benefits:**
- ✅ No need for local `uv`, `poetry`, or `requirements.txt`
- ✅ Dependencies declared explicitly in code
- ✅ Server-side environment creation using `uv`
- ✅ Cached by hash for instant reuse
- ✅ Perfect for notebooks, scripts, and quick prototyping

**Use cases:**
- Machine learning models with specific PyTorch/TensorFlow versions
- Data pipelines with specific pandas/numpy versions
- API integrations requiring specific library versions
- Quick prototyping without local environment setup

### Your First Pipeline

```python
import asyncio
from blazing import Blazing

# Initialize app with declarative dependencies
app = Blazing(
    api_token="your-api-token",
    python_version="3.11",
    dependencies=["httpx>=0.25.0"]  # Specify any dependencies you need
)

# Define a station
@app.station
async def greet(name: str, services=None):
    """Simple greeting station."""
    return f"Hello, {name}!"

# Define a route
@app.route
async def greeting_pipeline(name: str, services=None):
    """Pipeline that greets a user."""
    greeting = await greet(name)
    return {"message": greeting, "status": "success"}

async def main():
    # Publish workflows and steps to the service
    await app.publish()

    # Create and execute a task
    unit = await app.run("greeting_pipeline", name="Alice")
    result = await app.gather([unit])
    print(result[0])  # {"message": "Hello, Alice!", "status": "success"}

if __name__ == "__main__":
    asyncio.run(main())
```

**Output:**
```json
{"message": "Hello, Alice!", "status": "success"}
```

---

## Defining Pipelines

### Multi-Stage Pipelines

Chain multiple steps together to build complex workflows:

```python
from blazing import Blazing

# Specify dependencies for data processing
app = Blazing(
    api_token="your-api-token",
    python_version="3.11",
    dependencies=[
        "httpx>=0.25.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0"
    ]
)

@app.station
async def fetch_stock_data(symbol: str, services=None):
    """Fetch historical stock data."""
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.example.com/stocks/{symbol}")
        return response.json()

@app.station
def calculate_metrics(data, services=None):
    """Calculate technical indicators (CPU-intensive)."""
    import pandas as pd
    df = pd.DataFrame(data)

    # Calculate moving averages
    df['SMA_20'] = df['close'].rolling(window=20).mean()
    df['SMA_50'] = df['close'].rolling(window=50).mean()

    return df.to_dict('records')

@app.station
async def store_results(symbol: str, data, services=None):
    """Store processed data."""
    db = services['DatabaseService']
    await db.insert("stock_metrics", symbol=symbol, data=data)
    return {"symbol": symbol, "rows_inserted": len(data)}

@app.route
async def stock_analysis_pipeline(symbol: str, services=None):
    """Complete stock analysis pipeline."""
    # Step 1: Fetch data (async, I/O-bound)
    raw_data = await fetch_stock_data(symbol)

    # Step 2: Calculate metrics (sync, CPU-bound)
    metrics = await calculate_metrics(raw_data)

    # Step 3: Store results (async, I/O-bound)
    result = await store_results(symbol, metrics)

    return result
```

### Parallel Execution

Execute multiple operations in parallel using `asyncio.gather()`:

```python
@app.route
async def analyze_portfolio(symbols: list, services=None):
    """Analyze multiple stocks in parallel."""

    # Create tasks for all symbols
    tasks = [fetch_stock_data(symbol) for symbol in symbols]

    # Execute in parallel
    results = await asyncio.gather(*tasks)

    # Process results
    portfolio_data = dict(zip(symbols, results))
    return portfolio_data
```

### Conditional Logic

Routes can include branching logic:

```python
@app.route
async def adaptive_pipeline(data_source: str, services=None):
    """Pipeline that adapts based on data source."""

    if data_source == "api":
        raw_data = await fetch_from_api()
    elif data_source == "database":
        raw_data = await fetch_from_database()
    else:
        raw_data = await fetch_from_file(data_source)

    # Common processing
    processed = await process_data(raw_data)
    return processed
```

### Dynamic Station Calls

Build steps dynamically based on runtime data:

```python
@app.route
async def multi_stage_etl(config: dict, services=None):
    """ETL pipeline with configurable stages."""

    data = config['initial_data']

    # Execute stages defined in config
    for stage in config['stages']:
        station_name = stage['station']
        params = stage['params']

        # Call station by name
        station_func = app._station_funcs[station_name]
        data = await station_func(data, **params)

    return data
```

---

## Working with Services

### Defining a Service

```python
from blazing import BaseService
import asyncpg

class PostgresService(BaseService):
    """Manages PostgreSQL connection pool."""

    async def connect(self):
        """Initialize connection pool."""
        self.pool = await asyncpg.create_pool(
            host='localhost',
            port=5432,
            user='myuser',
            password='mypass',
            database='mydb',
            min_size=10,
            max_size=100
        )
        print("✓ PostgreSQL connection pool created")

    async def query(self, sql, *args):
        """Execute a query."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, *args)

    async def execute(self, sql, *args):
        """Execute a statement."""
        async with self.pool.acquire() as conn:
            return await conn.execute(sql, *args)

    async def disconnect(self):
        """Close connection pool."""
        await self.pool.close()
        print("✓ PostgreSQL connection pool closed")
```

### Registering Services

```python
# Register the service
@app.service(version="1.0")
class PostgresService(BaseService):
    # ... implementation ...
```

### Using Services in Stations

```python
@app.station
async def load_customer_data(customer_id: int, services=None):
    """Load customer data from database."""
    db = services['PostgresService']

    result = await db.query(
        "SELECT * FROM customers WHERE id = $1",
        customer_id
    )

    return result[0] if result else None

@app.station
async def save_analysis_results(customer_id: int, results: dict, services=None):
    """Save analysis results to database."""
    db = services['PostgresService']

    await db.execute(
        "INSERT INTO analysis_results (customer_id, data) VALUES ($1, $2)",
        customer_id,
        json.dumps(results)
    )

    return {"status": "saved", "customer_id": customer_id}
```

### Multiple Services

```python
@app.station
async def enrich_data(symbol: str, services=None):
    """Enrich stock data using multiple sources."""

    # Get data from database
    db = services['PostgresService']
    historical_data = await db.query(
        "SELECT * FROM stock_prices WHERE symbol = $1",
        symbol
    )

    # Get real-time data from API
    api = services['MarketDataAPIService']
    realtime_price = await api.get_current_price(symbol)

    # Combine data
    return {
        "symbol": symbol,
        "historical": historical_data,
        "current": realtime_price
    }
```

---

## Environment Management

Blazing automatically replicates your Python environment on remote workers, ensuring your code runs with the exact dependencies it needs.

### Environment Detection Priority

When you call `app.publish()`, Blazing captures your environment using this priority order:

1. **Declarative Dependencies** (highest priority)
   - Specified via `dependencies=` parameter in `Blazing()` constructor
   - Ideal for explicit control and reproducibility

2. **UV Project**
   - Auto-detected from `pyproject.toml` + `uv.lock` in current directory
   - Full lockfile ensures exact reproducibility

3. **Poetry Project**
   - Auto-detected from `pyproject.toml` + `poetry.lock`
   - Poetry-managed projects supported out of the box

4. **Requirements.txt**
   - Auto-detected from `requirements.txt` in current directory
   - Classic pip-style dependency specification

5. **Frozen Environment**
   - Falls back to `uv pip freeze` output from current virtualenv
   - Captures exact versions of all installed packages

6. **No Environment** (lowest priority)
   - Uses system Python on workers if no environment detected
   - Not recommended for production

### Declarative vs Auto-Detection

**Declarative (Recommended):**
```python
app = Blazing(
    api_token="token",
    python_version="3.11",
    dependencies=["torch==2.7.1", "numpy>=1.24.0"]
)
```
✅ Explicit and reproducible
✅ No local environment setup required
✅ Perfect for notebooks and scripts
✅ Version controlled in your code

**Auto-Detection:**
```python
app = Blazing(api_token="token")
# Automatically detects uv.lock, poetry.lock, or requirements.txt
```
✅ Works with existing projects
✅ Respects lockfiles for reproducibility
✅ Zero code changes required

### Environment Caching

Blazing caches environments by content hash:

```python
# First publish: Creates environment on workers (~30-60 seconds for large dependencies)
await app.publish()

# Subsequent publishes: Instant reuse of cached environment
await app.publish()  # < 1 second
```

**Cache benefits:**
- ⚡ Instant environment reuse across multiple `publish()` calls
- 💾 Shared across all apps using the same dependencies
- 🔄 Automatic cache invalidation when dependencies change
- 🧹 Automatic cleanup of old/unused environments

### Worker-Side Replication

When workers receive your environment specification:

1. **Hash Computation**: Worker computes environment hash
2. **Cache Lookup**: Checks if environment already exists
3. **Environment Creation** (if not cached):
   - Creates isolated virtual environment using `uv`
   - Installs all dependencies from specification
   - Caches for future use
4. **Task Execution**: Runs your code in the isolated environment

This ensures:
- ✅ Complete isolation between different apps
- ✅ Exact dependency versions match your specification
- ✅ No conflicts with system packages
- ✅ Reproducible execution across all workers

### Multi-App Isolation

Each Blazing app has complete isolation:

```python
# App 1: Machine learning with PyTorch 2.7
ml_app = Blazing(
    api_token="token-1",
    dependencies=["torch==2.7.1", "torchvision==0.18.1"]
)

# App 2: Data pipeline with older pandas
etl_app = Blazing(
    api_token="token-2",
    dependencies=["pandas==1.5.0", "numpy==1.23.0"]
)

# Both apps run independently with JWT-based tenant separation
```

**Isolation guarantees:**
- 🔒 Separate Python environments (no dependency conflicts)
- 🎫 JWT-based authentication and tenant separation
- 💾 Isolated state storage in Redis (per-app namespacing)
- ⚡ Independent worker pools (fair resource allocation)

### Example: Machine Learning Pipeline

```python
from blazing import Blazing

# Specify exact ML dependencies
app = Blazing(
    api_token="your-api-token",
    python_version="3.11",
    dependencies=[
        "torch==2.7.1",
        "torchvision==0.18.1",
        "transformers==4.35.0",
        "datasets==2.14.0",
        "scikit-learn>=1.3.0"
    ]
)

@app.station
def train_model(data, services=None):
    """CPU-intensive training happens in isolated environment."""
    import torch
    from transformers import AutoModelForSequenceClassification

    # Your training code here - runs with exact torch==2.7.1
    model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased")
    # ... training logic ...

    return {"model_path": "s3://models/my-model.pt"}

@app.route
async def ml_pipeline(dataset_name: str, services=None):
    """Train model with guaranteed environment."""
    result = await train_model(dataset_name)
    return result

# Publish: Environment created once, cached for all future runs
await app.publish()
```

---

## Executing Tasks

### Creating Tasks

Create a unit of work by calling `run()`:

```python
async def run_analysis():
    # Create a task
    unit = await app.run(
        "stock_analysis_pipeline",
        symbol="AAPL"
    )

    # Wait for result
    results = await app.gather([unit])
    print(results[0])
```

### Batch Execution

Process multiple tasks in parallel:

```python
async def analyze_multiple_stocks():
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]

    # Create tasks for all symbols
    units = []
    for symbol in symbols:
        unit = await app.run(
            "stock_analysis_pipeline",
            symbol=symbol
        )
        units.append(unit)

    # Wait for all results
    results = await app.gather(units)

    # Process results
    for symbol, result in zip(symbols, results):
        print(f"{symbol}: {result}")
```

### Monitoring Task Status

```python
async def run_with_monitoring():
    unit = await app.run(
        "long_running_pipeline",
        data_size="large"
    )

    # Poll for status
    while True:
        status = await app.get_task_status(unit.pk)
        print(f"Status: {status['current_status']}")

        if status['current_status'] in ['DONE', 'ERROR']:
            break

        await asyncio.sleep(5)  # Check every 5 seconds

    # Get final result
    result = await unit.wait_for_result()
    return result
```

### Canceling Tasks

```python
async def cancel_task_example():
    unit = await app.run(
        "expensive_computation",
        iterations=1000000
    )

    # Cancel after 10 seconds
    await asyncio.sleep(10)
    await app.cancel_task(unit.pk)

    print("Task canceled")
```

---

## Advanced Patterns

### Fan-Out / Fan-In

Process items in parallel and aggregate results:

```python
@app.station
async def process_item(item_id: int, services=None):
    """Process a single item."""
    # Simulate processing
    await asyncio.sleep(1)
    return {"item_id": item_id, "processed": True}

@app.route
async def fan_out_fan_in(item_ids: list, services=None):
    """Fan-out: Process all items in parallel, then fan-in: Aggregate."""

    # Fan-out: Create tasks for all items
    tasks = [process_item(item_id) for item_id in item_ids]

    # Execute in parallel
    results = await asyncio.gather(*tasks)

    # Fan-in: Aggregate results
    summary = {
        "total_items": len(results),
        "processed": sum(1 for r in results if r['processed']),
        "results": results
    }

    return summary
```

### Pipeline Composition

Chain multiple workflows together:

```python
@app.route
async def data_ingestion(source: str, services=None):
    """Ingest data from source."""
    # ... ingestion logic ...
    return raw_data

@app.route
async def data_transformation(data, services=None):
    """Transform raw data."""
    # ... transformation logic ...
    return transformed_data

@app.route
async def master_pipeline(source: str, services=None):
    """Composed pipeline: ingest → transform → load."""

    # Call other workflows as steps
    raw_data = await data_ingestion(source)
    transformed = await data_transformation(raw_data)
    result = await load_to_warehouse(transformed)

    return result
```

### Retry Logic

Implement retry patterns for unreliable operations:

```python
@app.station
async def fetch_with_retry(url: str, max_retries: int = 3, services=None):
    """Fetch data with exponential backoff retry."""

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if attempt == max_retries - 1:
                raise

            # Exponential backoff
            wait_time = 2 ** attempt
            await asyncio.sleep(wait_time)

    raise RuntimeError("Max retries exceeded")
```

### Streaming Results

Process large datasets in chunks:

```python
@app.station
async def fetch_chunk(offset: int, limit: int, services=None):
    """Fetch a chunk of data."""
    db = services['PostgresService']
    return await db.query(
        "SELECT * FROM large_table OFFSET $1 LIMIT $2",
        offset, limit
    )

@app.station
def process_chunk(data, services=None):
    """Process a chunk (CPU-intensive)."""
    # Heavy computation
    return [transform(row) for row in data]

@app.route
async def streaming_pipeline(total_rows: int, chunk_size: int = 1000, services=None):
    """Process large dataset in chunks."""

    results = []

    for offset in range(0, total_rows, chunk_size):
        # Fetch chunk
        chunk_data = await fetch_chunk(offset, chunk_size)

        # Process chunk
        processed = await process_chunk(chunk_data)

        # Store intermediate results
        results.extend(processed)

    return {"total_processed": len(results)}
```

### Checkpointing

Save intermediate progress for long-running pipelines:

```python
@app.route
async def long_running_etl(config: dict, services=None):
    """ETL pipeline with checkpointing."""

    db = services['PostgresService']
    checkpoint_key = f"etl_checkpoint_{config['job_id']}"

    # Load checkpoint if exists
    checkpoint = await db.query(
        "SELECT data FROM checkpoints WHERE key = $1",
        checkpoint_key
    )

    if checkpoint:
        state = json.loads(checkpoint[0]['data'])
        start_stage = state['stage']
    else:
        start_stage = 0

    stages = [
        extract_data,
        transform_data,
        validate_data,
        load_to_warehouse
    ]

    data = None
    for i, stage_func in enumerate(stages[start_stage:], start=start_stage):
        # Execute stage
        data = await stage_func(data or config)

        # Save checkpoint
        await db.execute(
            "INSERT INTO checkpoints (key, data) VALUES ($1, $2) "
            "ON CONFLICT (key) DO UPDATE SET data = $2",
            checkpoint_key,
            json.dumps({"stage": i + 1, "data": data})
        )

    # Clean up checkpoint
    await db.execute("DELETE FROM checkpoints WHERE key = $1", checkpoint_key)

    return data
```

---

## Error Handling

### Try-Catch in Stations

```python
@app.station
async def safe_api_call(url: str, services=None):
    """API call with error handling."""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            return {"status": "success", "data": response.json()}

    except httpx.HTTPError as e:
        return {"status": "error", "error": str(e), "data": None}

    except Exception as e:
        # Log unexpected errors
        print(f"Unexpected error: {e}")
        return {"status": "error", "error": "Internal error", "data": None}
```

### Graceful Degradation

```python
@app.route
async def resilient_pipeline(symbol: str, services=None):
    """Pipeline that degrades gracefully on failures."""

    # Try primary data source
    primary_result = await fetch_from_primary_api(symbol)

    if primary_result['status'] == 'error':
        # Fall back to secondary source
        secondary_result = await fetch_from_secondary_api(symbol)

        if secondary_result['status'] == 'error':
            # Fall back to cached data
            cached = await fetch_from_cache(symbol)

            if cached:
                return {"status": "cached", "data": cached, "warning": "Using stale data"}
            else:
                return {"status": "error", "error": "All sources failed"}

    return primary_result
```

### Validation

```python
@app.station
def validate_data(data: dict, services=None):
    """Validate data structure."""

    required_fields = ['symbol', 'price', 'timestamp']

    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    if data['price'] <= 0:
        raise ValueError("Price must be positive")

    return data
```

---

## Best Practices

### 1. Keep Stations Small and Focused

❌ **Bad**: One station doing everything
```python
@app.station
async def do_everything(symbol: str, services=None):
    # Fetch, transform, validate, store - all in one station
    ...
```

✅ **Good**: Separate concerns
```python
@app.station
async def fetch_data(symbol: str, services=None):
    """Single responsibility: fetch data."""
    ...

@app.station
def transform_data(data, services=None):
    """Single responsibility: transform."""
    ...
```

### 2. Use Appropriate Station Types

- **Async steps** for I/O-bound work (API calls, DB queries)
- **Sync steps** for CPU-bound work (data processing, computation)

```python
@app.station
async def fetch_from_api(url: str, services=None):
    """I/O-bound → async."""
    async with httpx.AsyncClient() as client:
        return await client.get(url)

@app.station
def heavy_computation(data, services=None):
    """CPU-bound → sync."""
    import pandas as pd
    return expensive_pandas_operation(data)
```

### 3. Leverage Services for Shared Resources

❌ **Bad**: Creating connections in every station
```python
@app.station
async def query_database(sql: str, services=None):
    # Creating new connection each time
    conn = await create_connection()
    result = await conn.execute(sql)
    await conn.close()
    return result
```

✅ **Good**: Use service for connection pooling
```python
@app.station
async def query_database(sql: str, services=None):
    # Reuse pooled connection
    db = services['DatabaseService']
    return await db.query(sql)
```

### 4. Use Type Hints

```python
from typing import List, Dict, Optional

@app.station
async def fetch_prices(symbols: List[str], services=None) -> Dict[str, float]:
    """Type hints improve code clarity and enable IDE support."""
    ...
```

### 5. Document Your Routes

```python
@app.route
async def portfolio_optimization(
    symbols: List[str],
    weights: Optional[List[float]] = None,
    services=None
) -> Dict[str, any]:
    """
    Optimize portfolio allocation.

    Args:
        symbols: List of stock symbols to include
        weights: Optional initial weights (default: equal weight)
        services: Injected services

    Returns:
        {
            'optimal_weights': {...},
            'expected_return': float,
            'risk': float
        }
    """
    ...
```

### 6. Handle Errors at the Right Level

- **Station level**: Handle expected errors (network timeouts, missing data)
- **Route level**: Handle pipeline orchestration errors
- **Client level**: Handle submission errors

### 7. Use Context Managers

```python
async def main():
    async with app:
        # App lifecycle managed automatically
        await app.publish()

        unit = await app.run("my_pipeline")
        result = await app.gather([unit])

        # Cleanup happens automatically
```

---

## Production Deployment

### Environment Configuration

```python
import os

# Production configuration with declarative dependencies
app = Blazing(
    api_token=os.getenv("BLAZING_API_TOKEN"),
    python_version="3.11",
    dependencies=[
        "httpx>=0.25.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        # Add your production dependencies here
    ]
)

# Built-in redundancy: Blazing automatically uses multiple API endpoints
# for high availability. No need to specify URLs in production.
```

**Production Best Practices:**
- ✅ Use declarative dependencies for explicit version control
- ✅ Pin exact versions for critical dependencies (e.g., `torch==2.7.1`)
- ✅ Use version ranges for compatible upgrades (e.g., `httpx>=0.25.0`)
- ✅ Store API token in environment variables, never hardcode
- ✅ Test with same dependencies in staging before production deploy

### Publishing Infrastructure

```python
async def deploy():
    """Deploy workflows and services to production."""

    async with app:
        # Publish all workflows, steps, and services
        await app.publish()

        print("✓ Successfully published to production")

if __name__ == "__main__":
    asyncio.run(deploy())
```

### Monitoring

```python
async def submit_with_monitoring(route_name: str, **kwargs):
    """Submit task with monitoring."""

    start_time = time.time()

    try:
        unit = await app.run(route_name, **kwargs)
        result = await app.gather([unit])

        duration = time.time() - start_time

        # Log metrics
        print(f"✓ {route_name} completed in {duration:.2f}s")

        return result[0]

    except Exception as e:
        # Log errors
        print(f"✗ {route_name} failed: {e}")
        raise
```

### Health Checks

```python
async def health_check():
    """Verify Blazing service is healthy."""

    try:
        # Simple ping task
        unit = await app.run("health_check_route")
        result = await app.gather([unit], timeout=30)

        return {"status": "healthy", "result": result}

    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

---

## Complete Example

Here's a complete real-world example: a machine learning pipeline for sentiment analysis with declarative dependencies:

```python
import asyncio
from blazing import Blazing, BaseService
from typing import List, Dict

# Initialize app with ML dependencies
app = Blazing(
    api_token="your-api-token",
    python_version="3.11",
    dependencies=[
        "torch==2.7.1",
        "transformers==4.35.0",
        "datasets==2.14.0",
        "scikit-learn>=1.3.0",
        "httpx>=0.25.0",
        "pandas>=2.0.0"
    ]
)

# Define service for model storage
@app.service(version="1.0")
class ModelStorageService(BaseService):
    """Manages model artifacts and metadata."""

    async def connect(self):
        import httpx
        self.client = httpx.AsyncClient()
        self.model_registry_url = "https://api.example.com/models"

    async def save_model(self, model_id: str, metrics: Dict):
        """Save model metadata to registry."""
        response = await self.client.post(
            f"{self.model_registry_url}/{model_id}",
            json=metrics
        )
        return response.json()

    async def disconnect(self):
        await self.client.aclose()

# Define steps
@app.station
async def fetch_training_data(dataset_name: str, services=None) -> Dict:
    """Fetch training dataset (I/O-bound)."""
    from datasets import load_dataset

    # Load dataset from HuggingFace
    dataset = load_dataset(dataset_name, split="train[:1000]")  # Sample for demo

    return {
        "texts": dataset["text"],
        "labels": dataset["label"],
        "dataset_name": dataset_name
    }

@app.station
def preprocess_data(data: Dict, services=None) -> Dict:
    """Preprocess text data (CPU-bound)."""
    from transformers import AutoTokenizer
    import pandas as pd

    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")

    # Tokenize texts
    encodings = tokenizer(
        data["texts"],
        truncation=True,
        padding=True,
        max_length=512,
        return_tensors="pt"
    )

    return {
        "encodings": encodings,
        "labels": data["labels"],
        "dataset_name": data["dataset_name"]
    }

@app.station
def train_model(data: Dict, epochs: int = 3, services=None) -> Dict:
    """Train sentiment classifier (CPU-intensive)."""
    import torch
    from transformers import AutoModelForSequenceClassification, Trainer, TrainingArguments
    from sklearn.metrics import accuracy_score, f1_score

    # Initialize model
    model = AutoModelForSequenceClassification.from_pretrained(
        "distilbert-base-uncased",
        num_labels=2
    )

    # Training arguments
    training_args = TrainingArguments(
        output_dir="./results",
        num_train_epochs=epochs,
        per_device_train_batch_size=16,
        logging_steps=100,
        save_strategy="epoch"
    )

    # Create dataset
    class SentimentDataset(torch.utils.data.Dataset):
        def __init__(self, encodings, labels):
            self.encodings = encodings
            self.labels = labels

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, idx):
            item = {key: val[idx] for key, val in self.encodings.items()}
            item["labels"] = torch.tensor(self.labels[idx])
            return item

    train_dataset = SentimentDataset(data["encodings"], data["labels"])

    # Train
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset
    )

    trainer.train()

    # Evaluate
    predictions = trainer.predict(train_dataset)
    preds = predictions.predictions.argmax(-1)

    accuracy = accuracy_score(data["labels"], preds)
    f1 = f1_score(data["labels"], preds, average="weighted")

    return {
        "model_id": f"sentiment-{data['dataset_name']}",
        "metrics": {
            "accuracy": float(accuracy),
            "f1_score": float(f1),
            "epochs": epochs
        }
    }

@app.station
async def save_model_metadata(model_data: Dict, services=None) -> Dict:
    """Save model to registry (I/O-bound)."""
    storage = services['ModelStorageService']

    result = await storage.save_model(
        model_id=model_data["model_id"],
        metrics=model_data["metrics"]
    )

    return {
        "model_id": model_data["model_id"],
        "registry_url": result["url"],
        "metrics": model_data["metrics"]
    }

# Define main route
@app.route
async def ml_training_pipeline(
    dataset_name: str,
    epochs: int = 3,
    services=None
) -> Dict:
    """
    Complete ML training pipeline.

    Args:
        dataset_name: HuggingFace dataset name
        epochs: Number of training epochs

    Returns:
        Training results with model metadata
    """
    # Step 1: Fetch data (async, I/O-bound)
    raw_data = await fetch_training_data(dataset_name)

    # Step 2: Preprocess (sync, CPU-bound)
    processed_data = await preprocess_data(raw_data)

    # Step 3: Train model (sync, CPU-intensive)
    model_results = await train_model(processed_data, epochs)

    # Step 4: Save metadata (async, I/O-bound)
    final_results = await save_model_metadata(model_results)

    return final_results

# Main execution
async def main():
    async with app:
        # Publish infrastructure (environment created once, cached)
        print("Publishing ML pipeline...")
        await app.publish()
        print("✓ Infrastructure published\n")

        # Submit training task
        print("Starting training pipeline...")
        unit = await app.run(
            "ml_training_pipeline",
            dataset_name="imdb",
            epochs=3
        )

        # Wait for result
        results = await app.gather([unit])
        result = results[0]

        # Display results
        print(f"\n{'='*50}")
        print(f"Training Complete!")
        print(f"{'='*50}")
        print(f"Model ID: {result['model_id']}")
        print(f"Registry URL: {result['registry_url']}")
        print(f"\nMetrics:")
        print(f"  Accuracy: {result['metrics']['accuracy']:.4f}")
        print(f"  F1 Score: {result['metrics']['f1_score']:.4f}")
        print(f"  Epochs: {result['metrics']['epochs']}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Key Features Demonstrated:**

1. **Declarative Dependencies**: ML libraries specified explicitly
2. **Mixed Workload**: Async I/O operations + CPU-intensive training
3. **Environment Isolation**: Workers run with exact torch==2.7.1
4. **Services**: Shared HTTP client for model registry
5. **Multi-Stage Pipeline**: Data fetch → preprocess → train → save
6. **Type Hints**: Clear interfaces for all functions
7. **Real-World Pattern**: Complete ML workflow from data to deployment

**Expected Output:**
```
Publishing ML pipeline...
✓ Infrastructure published

Starting training pipeline...

==================================================
Training Complete!
==================================================
Model ID: sentiment-imdb
Registry URL: https://api.example.com/models/sentiment-imdb

Metrics:
  Accuracy: 0.8924
  F1 Score: 0.8912
  Epochs: 3
```

---

## Next Steps

- **[Architecture Overview](architecture.md)** - Deep dive into Blazing's internals
- **[Worker Mix Optimizer](worker-mix-optimizer.md)** - How Blazing optimizes worker allocation
- **[Testing Guide](testing.md)** - Testing your Blazing pipelines
- **[API Reference](api-reference.md)** - Complete API documentation

For questions or support, please refer to the main [README](../README.md).
