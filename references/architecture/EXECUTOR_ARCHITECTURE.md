# Blazing Executor Architecture

## Core Principle: Security Through Separation

```
COORDINATOR (Coordinator) - THE BRAIN              EXECUTOR - DUMB MUSCLE
══════════════════════════════════             ════════════════════════

Makes ALL decisions:                           Just follows orders:
• What to execute                              • Receives scaling commands
• When to execute                              • Spawns/kills workers
• Which worker type executes what              • Deserializes functions
• Queue depth monitoring                       • Executes in sandbox
• Scaling up/down decisions                    • Returns result to Redis
• Lifecycle management                         • Has per-worker cache
                                               • NO strategic decisions
NEVER runs user code ❌
NEVER deserializes dill ❌                      ALWAYS runs user code ✅
                                               ALWAYS deserializes dill ✅
```

## The 4 Worker Types

Blazing uses a 2×2 matrix of worker types based on two dimensions:

| Dimension | Values | Purpose |
|-----------|--------|---------|
| **Blocking** | BLOCKING / NON_BLOCKING | Whether operation blocks or can run async |
| **Trust** | trusted / sandboxed | Whether code runs in process or WASM sandbox |

### Worker Type Matrix

```
                    │  TRUSTED (in-process)  │  SANDBOXED (Pyodide WASM)
────────────────────┼────────────────────────┼──────────────────────────
BLOCKING            │  BLOCKING              │  BLOCKING_SANDBOXED
(sync, one at a time)│  • DB transactions     │  • User-defined blocking
                    │  • File I/O            │  • Untrusted blocking ops
────────────────────┼────────────────────────┼──────────────────────────
NON_BLOCKING        │  NON_BLOCKING          │  NON_BLOCKING_SANDBOXED
(async, many concurrent)│  • API calls         │  • User-defined async
                    │  • Lightweight compute │  • Untrusted async ops
```

### Queue Architecture

Each worker type has its own Redis queue (CRDT-safe partitioned):

```
Station:{pk}:Queue:BLOCKING:{node_id}
Station:{pk}:Queue:NON_BLOCKING:{node_id}
Station:{pk}:Queue:BLOCKING_SANDBOXED:{node_id}
Station:{pk}:Queue:NON_BLOCKING_SANDBOXED:{node_id}
```

Workers poll ONLY their assigned queue type.

## Command Protocol

### Scaling Command: POST /v1/executor/configure

The coordinator sends scaling instructions to the executor:

```json
{
  "worker_config": {
    "BLOCKING": {
      "count": 2,
      "description": "Trusted blocking workers for DB/IO"
    },
    "NON_BLOCKING": {
      "count": 4,
      "async_slots": 10,
      "description": "Trusted async workers, 10 concurrent ops each"
    },
    "BLOCKING_SANDBOXED": {
      "count": 1,
      "description": "Sandboxed blocking for untrusted code"
    },
    "NON_BLOCKING_SANDBOXED": {
      "count": 2,
      "async_slots": 5,
      "description": "Sandboxed async, 5 concurrent ops each"
    }
  },
  "redis_url": "redis://redis:6379",
  "app_id": "default"
}
```

### Executor Response

```json
{
  "status": "configured",
  "active_workers": {
    "BLOCKING": 2,
    "NON_BLOCKING": 4,
    "BLOCKING_SANDBOXED": 1,
    "NON_BLOCKING_SANDBOXED": 2
  },
  "total_async_capacity": 50
}
```

### Health Check: GET /v1/executor/health

```json
{
  "status": "healthy",
  "workers": {
    "BLOCKING": {"active": 2, "busy": 1},
    "NON_BLOCKING": {"active": 4, "slots_used": 15, "slots_total": 40},
    "BLOCKING_SANDBOXED": {"active": 1, "busy": 0},
    "NON_BLOCKING_SANDBOXED": {"active": 2, "slots_used": 3, "slots_total": 10}
  },
  "uptime_seconds": 3600
}
```

## Executor Worker Pool Implementation

### Process Model

```
Executor Main Process
├── HTTP Server (receives /configure commands)
├── Worker Pool Manager
│   ├── BLOCKING Pool
│   │   ├── Worker Process 1 (polls Redis, executes, writes result)
│   │   └── Worker Process 2
│   ├── NON_BLOCKING Pool
│   │   ├── Worker Process 1 (async event loop, N slots)
│   │   ├── Worker Process 2 (async event loop, N slots)
│   │   └── ...
│   ├── BLOCKING_SANDBOXED Pool
│   │   └── Worker Process 1 (Pyodide runtime)
│   └── NON_BLOCKING_SANDBOXED Pool
│       ├── Worker Process 1 (Pyodide + async)
│       └── Worker Process 2 (Pyodide + async)
└── Metrics Reporter (writes to Redis)
```

### Worker Lifecycle

1. **Spawn**: Pool manager starts worker process with type + config
2. **Poll**: Worker polls its Redis queue continuously
3. **Execute**: On operation found:
   - Fetch function bytes from Redis
   - Deserialize with dill
   - Execute (in sandbox if SANDBOXED type)
   - Write result to Redis
4. **Scale**: On `/configure`, pool manager adjusts counts
5. **Terminate**: Graceful shutdown with drain period

### Async Slot Management (NON_BLOCKING types)

Each NON_BLOCKING worker runs an asyncio event loop with bounded concurrency:

```python
class AsyncWorker:
    def __init__(self, worker_type: str, max_slots: int):
        self.semaphore = asyncio.Semaphore(max_slots)
        self.active_tasks = set()

    async def run(self):
        while True:
            async with self.semaphore:
                operation = await self.poll_queue()
                if operation:
                    task = asyncio.create_task(self.execute(operation))
                    self.active_tasks.add(task)
                    task.add_done_callback(self.active_tasks.discard)
```

## Coordinator (Coordinator) Responsibilities

The coordinator ONLY:
1. **Monitors** queue depths via Redis LLEN
2. **Calculates** optimal worker counts using pilot light algorithm
3. **Sends** scaling commands to executor(s)
4. **Tracks** executor health via health checks
5. **Reads** metrics from Redis (enqueue/dequeue counters)

The coordinator NEVER:
- Deserializes user functions
- Executes any user code
- Maintains worker processes internally
- Touches dill/pickle payloads

## Metrics Collection

### Queue Metrics (in Redis)

```
blazing:metrics:queue:BLOCKING:enqueued
blazing:metrics:queue:BLOCKING:dequeued
blazing:metrics:queue:NON_BLOCKING:enqueued
blazing:metrics:queue:NON_BLOCKING:dequeued
blazing:metrics:queue:BLOCKING_SANDBOXED:enqueued
blazing:metrics:queue:BLOCKING_SANDBOXED:dequeued
blazing:metrics:queue:NON_BLOCKING_SANDBOXED:enqueued
blazing:metrics:queue:NON_BLOCKING_SANDBOXED:dequeued
```

### Executor reports to Redis

```
blazing:executor:{executor_id}:workers:BLOCKING:count
blazing:executor:{executor_id}:workers:BLOCKING:busy
blazing:executor:{executor_id}:workers:NON_BLOCKING:count
blazing:executor:{executor_id}:workers:NON_BLOCKING:slots_used
...
```

## Scaling Algorithm (Coordinator-side)

```python
def calculate_worker_config(queue_depths: dict, current_config: dict) -> dict:
    """
    Pilot light algorithm with 4 worker types.

    Guarantees:
    - At least 1 worker per type when work exists
    - Scale up when queue_depth > threshold
    - Scale down when idle for cooldown_period
    """
    new_config = {}

    for worker_type in ["BLOCKING", "NON_BLOCKING",
                        "BLOCKING_SANDBOXED", "NON_BLOCKING_SANDBOXED"]:
        depth = queue_depths.get(worker_type, 0)
        current = current_config.get(worker_type, {}).get("count", 0)

        # Pilot light: ensure minimum when work exists
        if depth > 0:
            min_workers = PILOT_LIGHT_MIN[worker_type]
            new_count = max(current, min_workers)
        else:
            new_count = current

        # Scale up based on queue pressure
        if depth > SCALE_UP_THRESHOLD:
            new_count = min(new_count + 1, MAX_WORKERS[worker_type])

        # Scale down if idle
        if depth == 0 and idle_time[worker_type] > COOLDOWN:
            new_count = max(new_count - 1, 0)

        new_config[worker_type] = {"count": new_count}

    return new_config
```

## Sandboxed Execution (Pyodide)

SANDBOXED worker types use Pyodide (Python in WebAssembly):

```
┌─────────────────────────────────────────────────┐
│  Worker Process (Node.js)                       │
│  ┌───────────────────────────────────────────┐  │
│  │  Pyodide Runtime (WASM)                   │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  User Code Execution                │  │  │
│  │  │  • No filesystem access             │  │  │
│  │  │  • No network (except bridge)       │  │  │
│  │  │  • Memory limited                   │  │  │
│  │  │  • CPU time bounded                 │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                    │                      │  │
│  │           Service Bridge                 │  │
│  │                    ↓                      │  │
│  └───────────────────────────────────────────┘  │
│                      │                          │
│         High-Priority Queue Operations          │
│                      ↓                          │
│              Redis (trusted data)               │
└─────────────────────────────────────────────────┘
```

### Service Bridge

When sandboxed code needs trusted resources (DB, APIs):

1. Sandboxed code calls `service.fetch_data()`
2. Bridge serializes request → high-priority queue
3. TRUSTED worker picks up, executes with real credentials
4. Result written to Redis
5. Bridge fetches result → returns to sandboxed code

## Deployment Architecture

```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine

  coordinator:
    image: blazing-coordinator
    environment:
      REDIS_URL: redis://redis:6379
      EXECUTOR_URLS: http://executor:8000
    # NO user code execution capability

  executor:
    image: blazing-executor
    environment:
      REDIS_URL: redis://redis:6379
    deploy:
      replicas: 3  # Scale horizontally
    # ALL user code runs here
```

## Summary

| Component | Runs User Code | Makes Decisions | Scales Workers |
|-----------|---------------|-----------------|----------------|
| Coordinator (Coordinator) | ❌ NEVER | ✅ YES | Sends commands |
| Executor | ✅ ALWAYS | ❌ NO | Follows commands |

This separation ensures:
1. **Security**: Untrusted code never runs on coordinator
2. **Scalability**: Executors scale independently
3. **Reliability**: Coordinator crash doesn't affect running work
4. **Flexibility**: Different executor types (Docker, Pyodide, GPU) coexist
