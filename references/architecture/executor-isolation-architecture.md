# Blazing Executor Isolation Architecture

## Overview

Blazing uses a split-plane architecture to ensure secure execution of user code. The system is divided into two distinct planes:

- **Control Plane** - Orchestration, business logic, state management
- **Data Plane** - Raw data storage and retrieval (args, kwargs, results)

The executor runs in an isolated environment with access ONLY to the data plane.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CONTROL PLANE                                  │
│                        (blazing_service)                                │
│                                                                          │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────────────┐ │
│  │   API       │    │   Coordinator    │    │       Coordinator           │ │
│  │  Server     │───▶│  (Workers)   │───▶│  • DAOs (Redis-OM)          │ │
│  │             │    │              │    │  • Orchestration            │ │
│  └─────────────┘    └──────────────┘    │  • State Management         │ │
│                                          │  • Queue Management         │ │
│                                          └─────────────────────────────┘ │
│                                                      │                   │
│                                                      │ HTTP              │
│                                                      ▼                   │
└─────────────────────────────────────────────────────────────────────────┘
                                                       │
                                                       │ POST /execute
                                                       │ {
                                                       │   serialized_function,
                                                       │   args_address,
                                                       │   kwargs_address,
                                                       │   result_key
                                                       │ }
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           EXECUTION PLANE                                │
│                        (blazing_executor)                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    Executor Service                                  ││
│  │                                                                      ││
│  │  1. Receive HTTP request with addresses                              ││
│  │  2. Fetch args/kwargs from DATA PLANE                                ││
│  │  3. Deserialize and execute function                                 ││
│  │  4. Store result to DATA PLANE                                       ││
│  │  5. Return result_address to coordinator                             ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                              │                                           │
│                              │ Data Fetching                             │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    Data Plane Access                                 ││
│  │                                                                      ││
│  │  ┌─────────────────┐         ┌─────────────────────┐                ││
│  │  │   Redis-Data    │         │    Arrow Flight     │                ││
│  │  │   (Pickled)     │         │    (Columnar)       │                ││
│  │  └─────────────────┘         └─────────────────────┘                ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  SECURITY: No access to Control Plane (DAOs, Coordinator, API)              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Package Separation

### Control Plane Package: `blazing_service`

Contains:
- `server.py` - FastAPI REST API
- `engine/runtime.py` - Coordinator, workers, orchestration
- `data_access/` - Redis-OM DAOs for state management
- `auth/` - JWT verification, app_id context
- `executor/` - Executor backend dispatchers (calls external executors)

### Execution Plane Package: `blazing_executor`

Contains:
- `service.py` - Minimal FastAPI HTTP endpoint
- `data_fetching/` - Data plane clients only
  - `redis_client.py` - Direct Redis access for data
  - `lru_cache.py` - In-memory caching
  - `arrow_client.py` - Arrow Flight access (future)

**CRITICAL**: `blazing_executor` has ZERO imports from:
- `blazing` (client SDK)
- `blazing_service` (coordinator)

## Data Flow

### 1. Coordinator Prepares Execution

```python
# In blazing_service (coordinator)
operation = OperationDAO.get(operation_pk)

# Store args/kwargs to data plane
args_key = f"data:{operation_pk}:args"
kwargs_key = f"data:{operation_pk}:kwargs"
await redis_data.set_pickled(args_key, operation.args)
await redis_data.set_pickled(kwargs_key, operation.kwargs)

# Prepare addresses
payload = {
    "serialized_function": operation.serialized_function,
    "args_address": f"RedisIndirect|{args_key}",
    "kwargs_address": f"RedisIndirect|{kwargs_key}",
    "result_key": f"data:{operation_pk}:result",
    "ttl": 3600
}

# Call executor
response = await httpx.post("http://executor:8000/execute", json=payload)
```

### 2. Executor Processes Request

```python
# In blazing_executor (isolated container)
@app.post("/execute")
async def execute(request: ExecuteRequest):
    # Fetch args from data plane
    args = await fetch_from_address(request.args_address)
    kwargs = await fetch_from_address(request.kwargs_address)

    # Deserialize and execute
    func = dill.loads(base64.b64decode(request.serialized_function))
    result = await func(*args, **kwargs)

    # Store result to data plane
    result_address = await store_to_address(result, request.result_key, request.ttl)

    return {"result_address": result_address}
```

### 3. Coordinator Retrieves Result

```python
# In blazing_service (coordinator)
result_address = response.json()["result_address"]
# Result is stored in data plane, coordinator can fetch if needed
# Or just store the address in OperationDAO for later retrieval
```

## Data Transfer Options

The executor supports multiple ways to receive args/kwargs and return results:

### Input Data (args/kwargs)

| Method | Field | Use Case |
|--------|-------|----------|
| **Inline** | `args_inline`, `kwargs_inline` | Small data (<1MB), passed directly in HTTP payload |
| **RedisIndirect** | `args_address`, `kwargs_address` | Large data, fetched from Redis-data |
| **Arrow Flight** | `args_address`, `kwargs_address` | Columnar data (future) |

### Output Data (results)

| Method | When | How |
|--------|------|-----|
| **Inline** | Small results | Returned in `GET /status/{task_id}` response |
| **RedisIndirect** | Large results | Stored to Redis-data, address in `result_address` |

### Address Formats

| Format | Description | Example |
|--------|-------------|---------|
| `RedisIndirect\|{key}` | Pickled data in Redis-data | `RedisIndirect\|data:op123:args` |
| `arrow\|{grpc}\|{pk}\|{ipc}` | Columnar data in Arrow Flight | `arrow\|localhost:8815\|op123\|localhost:8816` |

### Deprecated

| Format | Status | Replacement |
|--------|--------|-------------|
| `redis` | **DEPRECATED** | Use `args_inline` or `RedisIndirect\|{key}` |

The `redis` address type required the executor to access `OperationDAO` from `blazing_service`,
breaking control/data plane isolation. It should not be used with the new isolated executor.

## HTTP API Contract

### POST /execute

Execute a serialized function with data from the data plane.

**Request:**
```json
{
  "serialized_function": "base64-encoded-dill-bytes",
  "args_address": "RedisIndirect|data:op123:args",
  "kwargs_address": "RedisIndirect|data:op123:kwargs",
  "result_key": "data:op123:result",
  "ttl": 3600
}
```

**Response:**
```json
{
  "result_address": "RedisIndirect|data:op123:result",
  "execution_time_ms": 42
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "redis_data": true,
  "arrow_flight": false
}
```

## Security Boundaries

### What Executor CAN Access

| Resource | Access Level | Purpose |
|----------|--------------|---------|
| Redis-data | Read/Write | Fetch args/kwargs, store results |
| Arrow Flight | Read/Write | Columnar data transfer |
| HTTP (outbound) | None | Sandboxed, no external calls |
| Filesystem | Minimal | Temp files only |

### What Executor CANNOT Access

| Resource | Reason |
|----------|--------|
| Control Redis | Contains DAOs, state, queues |
| Coordinator API | Business logic exposure |
| JWT Secrets | Authentication bypass |
| Source Code | IP protection |
| Other Containers | Network isolation |

## Container Isolation Layers

### Production Configuration (Linux)

```
┌──────────────────────────────────────────────────────┐
│                    gVisor (runsc)                     │
│         Linux user-space kernel replacement          │
│                                                       │
│  ┌────────────────────────────────────────────────┐  │
│  │              Docker Container                   │  │
│  │         Namespace/cgroup isolation              │  │
│  │                                                 │  │
│  │  ┌───────────────────────────────────────────┐ │  │
│  │  │         Pyodide (Optional)                │ │  │
│  │  │        WebAssembly sandbox                │ │  │
│  │  │                                           │ │  │
│  │  │  ┌─────────────────────────────────────┐ │ │  │
│  │  │  │         User Code                   │ │ │  │
│  │  │  │    Deserialized function            │ │ │  │
│  │  │  └─────────────────────────────────────┘ │ │  │
│  │  └───────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Isolation Layers

1. **gVisor** (Production, Linux only)
   - Intercepts all syscalls
   - Implements Linux kernel in user-space
   - Configured at Docker daemon level: `default-runtime: runsc`

2. **Docker Container**
   - Namespace isolation (PID, network, mount)
   - cgroup resource limits
   - Seccomp syscall filtering
   - Read-only filesystem

3. **Pyodide** (Optional, additional layer)
   - WebAssembly sandbox
   - No direct syscalls
   - Memory-safe execution

## Dockerfile

```dockerfile
# Minimal executor image
FROM python:3.11-slim

# Only install executor dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .[executor]

# Copy ONLY executor package
COPY src/blazing_executor /app/blazing_executor

WORKDIR /app

# Security: non-root user
RUN useradd -m executor
USER executor

# Minimal exposed surface
EXPOSE 8000
CMD ["uvicorn", "blazing_executor.service:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_REDIS_URL` | `redis-data` | Redis data plane host |
| `DATA_REDIS_PORT` | `6379` | Redis data plane port |
| `DATA_REDIS_DB` | `0` | Redis database number |
| `DATA_REDIS_PASSWORD` | None | Redis password |
| `ARROW_GRPC_ADDRESS` | None | Arrow Flight gRPC address |
| `EXECUTION_TIMEOUT` | `300` | Max execution time (seconds) |

## Migration Path

### Phase 1: Create Package (Current)
- [x] Create `blazing_executor` package structure
- [x] Implement `data_fetching/redis_client.py`
- [x] Copy `data_fetching/lru_cache.py`
- [ ] Implement `service.py`

### Phase 2: Update Coordinator
- [ ] Refactor executor backends to use HTTP
- [ ] Store args/kwargs to data plane before execution
- [ ] Retrieve results from data plane after execution

### Phase 3: Deployment
- [ ] Create minimal Dockerfile for executor
- [ ] Update docker-compose with separate executor service
- [ ] Configure gVisor in production Docker daemon

### Phase 4: Cleanup
- [ ] Remove old executor code from `blazing_service`
- [ ] Remove unnecessary dependencies from executor image
- [ ] Security audit of final architecture
