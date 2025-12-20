# Redis TTL Configuration

All Redis keys in Blazing have Time-To-Live (TTL) expiration using a **sliding window** pattern:
- Keys are created with an initial TTL
- Every access (get/save/update) refreshes the TTL to full duration
- Hot data (frequently accessed) stays indefinitely
- Cold data (unused) expires automatically

This prevents Redis memory from growing unbounded in long-running deployments while preserving actively-used data.

## How It Works

### Sliding Window Pattern

When a DAO is saved or accessed, its TTL is automatically refreshed:

```python
# Save a station
station = StationDAO(name="my-station", station_type="NON-BLOCKING", priority=1.0)
await station.save()  # TTL set to 1 year

# Access the station after 6 months
fetched = await StationDAO.get(station.pk)  # TTL refreshed to 1 year from now

# If never accessed again, it will expire 1 year after the last access
```

### Key Expiration

- **Hot data**: Accessed frequently (e.g., daily) - stays indefinitely
- **Warm data**: Accessed occasionally (e.g., monthly) - survives as long as accessed within TTL window
- **Cold data**: Never accessed after creation - expires after configured TTL

## Environment Variables

All TTL durations are configurable via environment variables (values in seconds):

### Route Definitions (Long-Lived)

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_ROUTE_DEFINITION_ROUTE` | 31536000 (1 year) | Routes defined by users |
| `TTL_ROUTE_DEFINITION_STATION` | 31536000 (1 year) | Stations defined by users |
| `TTL_ROUTE_DEFINITION_STATION_STATUS` | 604800 (1 week) | Station status (changes frequently) |

### Unit/Operation Data (Medium-Lived)

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_UNIT_DEFINITION_UNIT` | 15552000 (6 months) | Unit execution records |
| `TTL_UNIT_DEFINITION_OPERATION` | 15552000 (6 months) | Operation records |
| `TTL_UNIT_DEFINITION_STORAGE` | 15552000 (6 months) | Large payload storage |

### Execution State (Short-Lived)

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_EXECUTION_COORDINATOR` | 86400 (1 day) | Coordinator coordinator state |
| `TTL_EXECUTION_WORKER_PROCESS` | 86400 (1 day) | Worker process state |
| `TTL_EXECUTION_WORKER_THREAD` | 86400 (1 day) | Worker thread state |
| `TTL_EXECUTION_WORKER_ASYNC` | 86400 (1 day) | Async worker state |
| `TTL_EXECUTION_STATUS` | 86400 (1 day) | All worker status DAOs |

### Metrics

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_METRICS_WORKER_LIFECYCLE` | 604800 (1 week) | Worker timing metrics |

### App-Specific

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_APP_SPECIFIC_SERVICE` | 31536000 (1 year) | Service definitions |
| `TTL_APP_SPECIFIC_CONNECTOR` | 31536000 (1 year) | Connector configurations |
| `TTL_APP_SPECIFIC_CUSTOMER_APP_MAPPING` | 15552000 (6 months) | Customer app mappings |
| `TTL_APP_SPECIFIC_SERVICE_INVOKE` | 86400 (1 day) | Service invocation records |
| `TTL_APP_SPECIFIC_DYNAMIC_CODE` | 604800 (1 week) | Dynamic code execution records |

### Queues

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_QUEUE_OPERATION` | 3600 (1 hour) | Operation queues (CRDT segments) |
| `TTL_QUEUE_STATISTICS` | 3600 (1 hour) | Statistics queues |

### Default

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_DEFAULT` | 15552000 (6 months) | Fallback for DAOs without specific TTL |

## Example Configuration

### Docker Compose

```yaml
services:
  blazing-api:
    environment:
      # Shorten station TTL to 30 days
      TTL_ROUTE_DEFINITION_STATION: "2592000"  # 30 days

      # Worker state expires after 12 hours instead of 1 day
      TTL_EXECUTION_WORKER_THREAD: "43200"  # 12 hours

      # Default for unspecified DAOs: 3 months
      TTL_DEFAULT: "7776000"  # 3 months
```

### .env File

```bash
# Long-lived user definitions
TTL_ROUTE_DEFINITION_ROUTE=31536000  # 1 year
TTL_APP_SPECIFIC_SERVICE=31536000   # 1 year

# Medium-lived execution artifacts
TTL_UNIT_DEFINITION_UNIT=15552000    # 6 months
TTL_UNIT_DEFINITION_OPERATION=15552000  # 6 months

# Short-lived runtime state
TTL_EXECUTION_COORDINATOR=86400          # 1 day
TTL_EXECUTION_WORKER_THREAD=86400    # 1 day

# Queue cleanup
TTL_QUEUE_OPERATION=3600             # 1 hour
TTL_QUEUE_STATISTICS=3600            # 1 hour
```

## Implementation Details

### Base DAO Classes

All three base DAO classes support TTL:

1. **AppAwareHashModel** - Most DAOs (Stations, Units, Workers, etc.)
2. **AppAwareJsonModel** - JSON-based DAOs (Connectors, etc.)
3. **DataRedisHashModel** - Large payload storage (StorageDAO)

Each class has:
- `_get_ttl_seconds()` - Look up TTL from configuration
- `_refresh_ttl(key)` - Set EXPIRE on a Redis key
- Modified `.save()` - Sets TTL after saving
- Modified `.get()` - Refreshes TTL on access

### Queue Operations

All queue enqueue operations set TTL after LPUSH:

- Non-blocking queues: `TTL_QUEUE_OPERATION` (1 hour)
- Blocking queues: `TTL_QUEUE_OPERATION` (1 hour)
- Sandboxed queues: `TTL_QUEUE_OPERATION` (1 hour)
- Statistics queues: `TTL_QUEUE_STATISTICS` (1 hour)

This prevents abandoned queue segments from accumulating.

## Migration Notes

### Gradual Application

The TTL system applies **gradually** to existing deployments:

- **Existing keys**: No TTL until they are accessed or updated
- **New keys**: TTL set immediately on creation
- **Accessed keys**: TTL set on first `.get()` after deployment

This is **safe and non-disruptive**:
- No scan/migration script needed
- No downtime required
- Keys that are never accessed again remain indefinitely (acceptable trade-off)

### Monitoring

To check if TTL is being applied:

```bash
# Check TTL on a specific key
redis-cli TTL "blazing:my-app:route_definition:Station:01234567890"

# Count keys with vs without TTL
redis-cli --scan --pattern "blazing:*:route_definition:Station:*" | \
  xargs -I {} redis-cli TTL {} | \
  awk '{if($1==-1) print "No TTL"; else print "Has TTL"}' | \
  sort | uniq -c

# Output example:
# 42 Has TTL
#  3 No TTL  (old keys not yet accessed)
```

### TTL Values

- `TTL > 0`: Key has TTL, value is seconds until expiration
- `TTL = -1`: Key exists but has no TTL (old key not yet accessed)
- `TTL = -2`: Key does not exist

## Performance Impact

TTL management has **minimal performance impact**:

- `.save()`: One additional `EXPIRE` command per save (~0.1-0.5ms)
- `.get()`: One additional `EXPIRE` command per get (~0.1-0.5ms)
- Queue operations: One additional `EXPIRE` per enqueue (~0.1-0.5ms)

Benefits:
- Prevents Redis memory exhaustion
- Automatic cleanup of cold data
- No manual maintenance required

## FAQ

### What happens to data being accessed when it expires?

The sliding window pattern means **actively accessed data never expires**. Only cold (unused) data expires.

### Can I disable TTL for specific DAOs?

Not currently supported. Set a very long TTL (e.g., 100 years) if needed:

```bash
TTL_ROUTE_DEFINITION_STATION=3153600000  # 100 years
```

### What if I want fixed TTL instead of sliding window?

The sliding window pattern is hardcoded for safety. To implement fixed TTL, you would need to:
1. Remove `_refresh_ttl()` calls from `.get()` methods
2. Keep `_refresh_ttl()` calls in `.save()` methods only

### How do I verify TTL is working?

Run the test suite:

```bash
uv run pytest tests/test_dao_ttl.py -v
```

Or check manually:

```bash
# Create a station via API
curl -X POST http://localhost:8000/v1/registry/sync \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{"stations": [{"name": "test", "type": "NON-BLOCKING", "priority": 1.0, "func": "..."}]}'

# Check its TTL
docker exec blazing-redis redis-cli --scan --pattern "*:Station:*" | \
  head -1 | \
  xargs docker exec blazing-redis redis-cli TTL

# Should return a large number (close to 31536000 for 1 year)
```

## See Also

- [Dual Redis Architecture](redis-architecture.md) - How Coordination and Data Redis instances work together
- [CRDT Multi-Master Queues](crdt-multimaster-queues.md) - Queue TTL with CRDT-safe partitioning
- [DAO Caching](optimization-caches.md) - Client-side caching vs Redis TTL
