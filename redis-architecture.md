# Redis Architecture

Blazing uses a dual-Redis architecture with distinct roles and capabilities for each instance.

## Overview

| Instance | Image | Port | Purpose | RediSearch |
|----------|-------|------|---------|------------|
| **Coordination Redis** | `redis/redis-stack-server:latest` | 6379 | DAOs, queues, indexes | Yes |
| **Data Redis** | `redis:7-alpine` | 6381 | Large payload storage | No |

## Coordination Redis (redis-stack)

**Image:** `redis/redis-stack-server:latest`

**Purpose:** Manages all coordination state, metadata, and queues.

**Modules Included:**
- **RediSearch** - Full-text search and secondary indexing (required for `.find()` queries)
- **RedisJSON** - Native JSON document storage
- **RedisGraph** - Graph database capabilities
- **RedisTimeSeries** - Time series data storage
- **RedisBloom** - Probabilistic data structures

**Used For:**
- All DAO objects (`StationDAO`, `OperationDAO`, `UnitDAO`, `CoordinatorDAO`, `WorkerThreadDAO`, etc.)
- Queue management (blocking queues, non-blocking queues, statistics queues)
- Search indexes for finding objects (e.g., `CoordinatorDAO.find()`, `StationDAO.find()`)
- ACL user management with role-based permissions

**Key Operations:**
```python
# These require RediSearch indexes
await StationDAO.find(StationDAO.name == "my_station").first()
await CoordinatorDAO.find_next_available_name()
await WorkerThreadDAO.find(WorkerThreadDAO.worker_process_pk == pk).all()
```

**ACL Users:**
- `admin` - Full access for management operations
- `coordinator` - Full access for worker coordination
- `api` - Full access for API server
- `executor` - Limited access (no `FT.SEARCH`, specific key patterns only)

## Data Redis (redis:7-alpine)

**Image:** `redis:7-alpine`

**Purpose:** High-performance blob storage for large operation payloads.

**Modules Included:** None (vanilla Redis)

**Used For:**
- `StorageDAO` - Stores serialized args, kwargs, and results for operations
- Large payload storage (>1MB data that would bloat Coordination Redis)
- Temporary data with TTL expiration

**Key Operations:**
```python
# Simple GET/SET operations - no RediSearch needed
await redis_data.hset(f"blazing:{app_id}:storage:{pk}", "data", payload)
await redis_data.hget(f"blazing:{app_id}:storage:{pk}", "data")
```

**Why Not redis-stack?**
1. **Resource efficiency** - redis-stack adds ~200-400MB memory overhead for modules we don't use
2. **Simplicity** - Data Redis only needs basic key-value operations
3. **Separation of concerns** - Keeps storage layer lightweight and fast
4. **Cost optimization** - Can use smaller instances for Data Redis

## RediSearch Availability

### Where RediSearch IS Required

| Component | Needs RediSearch | Why |
|-----------|-----------------|-----|
| API Server | Yes | Uses `.find()` for station/route lookups |
| Coordinator | Yes | Uses `.find()` for worker management |
| Worker Processes | Yes | Uses `.find()` for operation lookups |
| Health Check | No* | Simplified to avoid RediSearch dependency |

*Note: `health_check()` was simplified to only check Redis connectivity, not coordinator count, to avoid RediSearch dependency in minimal deployments.

### Where RediSearch is NOT Required

| Component | Needs RediSearch | Why |
|-----------|-----------------|-----|
| Executor (Docker/Pyodide) | No | Only fetches/stores data via addresses |
| Data Redis operations | No | Only basic GET/SET/HGET/HSET |
| Storage operations | No | Key-value storage only |

## Code Patterns

### Checking for RediSearch Availability

When code needs to handle both RediSearch-enabled and basic Redis:

```python
async def health_check():
    """Check system health."""
    try:
        redis_client = thread_local_data.redis
        await redis_client.ping()

        # Note: Coordinator check disabled due to FT.SEARCH requiring RediSearch module
        # To re-enable, uncomment below (only works with redis-stack-server):
        # foremen = await CoordinatorDAO.find().all()
        # foremen_count = len(foremen)

        return {
            "status": "healthy",
            "redis": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unhealthy: {str(e)}")
```

### Executor Pattern (No RediSearch)

The executor intentionally has limited Redis access and doesn't need RediSearch:

```python
# Executor uses simple address-based fetching
# Address format: RedisIndirect|{app_id}|{pk}
async def fetch_from_redis(address: str) -> bytes:
    parts = address.split("|")
    _, app_id, pk = parts
    client = get_redis_data_client()
    return await client.hget(f"blazing:{app_id}:storage:{pk}", "data")
```

## Docker Compose Configuration

```yaml
services:
  # Coordination Redis - Full redis-stack with RediSearch
  redis:
    image: redis/redis-stack-server:latest
    ports:
      - "6379:6379"
    environment:
      - REDIS_ADMIN_PASSWORD=${REDIS_ADMIN_PASSWORD}
      - REDIS_EXECUTOR_PASSWORD=${REDIS_EXECUTOR_PASSWORD}
      - REDIS_COORDINATOR_PASSWORD=${REDIS_COORDINATOR_PASSWORD}
      - REDIS_API_PASSWORD=${REDIS_API_PASSWORD}
    entrypoint: ["/usr/local/bin/redis-entrypoint.sh"]
    volumes:
      - ./docker/redis-entrypoint.sh:/usr/local/bin/redis-entrypoint.sh

  # Data Redis - Lightweight vanilla Redis
  redis-data:
    image: redis:7-alpine
    ports:
      - "6381:6379"
    environment:
      - REDIS_DATA_ADMIN_PASSWORD=${REDIS_DATA_ADMIN_PASSWORD}
      - REDIS_DATA_EXECUTOR_PASSWORD=${REDIS_DATA_EXECUTOR_PASSWORD}
      - REDIS_DATA_COORDINATOR_PASSWORD=${REDIS_DATA_COORDINATOR_PASSWORD}
      - REDIS_DATA_API_PASSWORD=${REDIS_DATA_API_PASSWORD}
    entrypoint: ["/usr/local/bin/redis-data-entrypoint.sh"]
```

## Migration Considerations

### If You Need RediSearch on Data Redis

If future requirements need search capabilities on stored data:

1. Change `redis-data` image to `redis/redis-stack-server:latest`
2. Create search indexes for the data patterns you need
3. Update ACL permissions if needed
4. Account for increased memory usage (~200-400MB overhead)

### Current Recommendation

**Keep the dual-architecture** unless you have specific search requirements on stored data:
- Coordination Redis: `redis-stack-server` (full capabilities)
- Data Redis: `redis:7-alpine` (lightweight, efficient)

This separation provides optimal resource usage and clear separation of concerns.
