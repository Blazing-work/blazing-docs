# Redis TTL Configuration

Blazing uses a **selective TTL policy** - only transient data has TTL expiration. Definitions (Workflows, Steps, Services, Connectors) live forever until explicitly deleted.

## TTL Policy (Lexicon 2.0)

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| **Definitions** | None | User-defined schemas - live forever until deleted |
| - Workflows | ♾️ | User workflow definitions |
| - Steps | ♾️ | User step definitions |
| - Services | ♾️ | User service definitions |
| - Connectors | ♾️ | Connector configurations |
| **Transient Data** | 6 months | Execution artifacts - expire if unused |
| - Runs | 6 months | Run execution records (was Units) |
| - StepRuns | 6 months | Step execution records (was Operations) |
| - Storage | 6 months | Large payload storage |
| **Execution State** | 1 day | Worker/coordinator state - ephemeral |
| - Coordinators | 1 day | Coordinator state |
| - Worker processes | 1 day | Worker process state |
| - Worker threads | 1 day | Worker thread state |
| **Queues** | None | Items are processed and removed naturally |

## Sliding Window Pattern

For data types with TTL, Blazing uses a **sliding window** pattern:
- Keys are created with an initial TTL
- Every access (get/save/update) refreshes the TTL to full duration
- Hot data (frequently accessed) stays indefinitely
- Cold data (unused) expires automatically

This prevents Redis memory from growing unbounded while preserving actively-used data.

### Example

```python
# Create a run (Lexicon 2.0: was Unit)
run = RunDAO()
await run.save()  # TTL set to 6 months

# Access the run after 3 months
fetched = await RunDAO.get(run.pk)  # TTL refreshed to 6 months from now

# If never accessed again, it will expire 6 months after the last access
```

## Environment Variables

All TTL durations are configurable via environment variables (values in seconds):

### Definitions (No TTL)

| Data Type | TTL | Notes |
|-----------|-----|-------|
| Workflows | None | Live forever until deleted |
| Steps | None | Live forever until deleted |
| Services | None | Live forever until deleted |
| Connectors | None | Live forever until deleted |

### Transient Data (Lexicon 2.0)

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_RUN_DEFINITION_RUN` | 15552000 (6 months) | Run execution records |
| `TTL_RUN_DEFINITION_STEP_RUN` | 15552000 (6 months) | StepRun records |
| `TTL_RUN_DEFINITION_STORAGE` | 15552000 (6 months) | Large payload storage |

### Execution State

| Variable | Default | Description |
|----------|---------|-------------|
| `TTL_EXECUTION_COORDINATOR` | 86400 (1 day) | Coordinator state |
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
| `TTL_APP_SPECIFIC_CUSTOMER_APP_MAPPING` | 15552000 (6 months) | Customer app mappings |
| `TTL_APP_SPECIFIC_SERVICE_INVOKE` | 86400 (1 day) | Service invocation records |
| `TTL_APP_SPECIFIC_DYNAMIC_CODE` | 604800 (1 week) | Dynamic code execution records |

## Example Configuration

### Docker Compose

```yaml
services:
  blazing-api:
    environment:
      # Shorten run TTL to 30 days
      TTL_RUN_DEFINITION_RUN: "2592000"  # 30 days

      # Worker state expires after 12 hours instead of 1 day
      TTL_EXECUTION_WORKER_THREAD: "43200"  # 12 hours
```

### .env File

```bash
# Transient execution artifacts (Lexicon 2.0)
TTL_RUN_DEFINITION_RUN=15552000       # 6 months
TTL_RUN_DEFINITION_STEP_RUN=15552000  # 6 months
TTL_RUN_DEFINITION_STORAGE=15552000   # 6 months

# Short-lived runtime state
TTL_EXECUTION_COORDINATOR=86400       # 1 day
TTL_EXECUTION_WORKER_THREAD=86400     # 1 day
```

## Implementation Details

### Base DAO Classes

DAOs with TTL support have:
- `_get_ttl_seconds()` - Look up TTL from configuration
- `_refresh_ttl(key)` - Set EXPIRE on a Redis key
- Modified `.save()` - Sets TTL after saving
- Modified `.get()` - Refreshes TTL on access

### Definitions (No TTL)

Definition DAOs (WorkflowDAO, StepDAO, ServiceDAO, ConnectorDAO) do **not** have TTL set:
- They live forever until explicitly deleted
- User-defined schemas should persist indefinitely
- No automatic cleanup needed

### Queues (No TTL)

Queues do **not** have TTL:
- Items are processed and removed naturally by workers
- Queue registry entries are cleaned up when queues become empty
- No TTL needed since queues are self-cleaning

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
redis-cli TTL "blazing:my-app:run_definition:Run:01234567890"

# Check that definitions have no TTL
redis-cli TTL "blazing:my-app:workflow_definition:Step:01234567890"
# Should return -1 (no TTL)

# Count keys with vs without TTL
redis-cli --scan --pattern "blazing:*:run_definition:Run:*" | \
  xargs -I {} redis-cli TTL {} | \
  awk '{if($1==-1) print "No TTL"; else print "Has TTL"}' | \
  sort | uniq -c
```

### TTL Values

- `TTL > 0`: Key has TTL, value is seconds until expiration
- `TTL = -1`: Key exists but has no TTL (definition, or old key not yet accessed)
- `TTL = -2`: Key does not exist

## Performance Impact

TTL management has **minimal performance impact**:

- `.save()`: One additional `EXPIRE` command per save (~0.1-0.5ms)
- `.get()`: One additional `EXPIRE` command per get (~0.1-0.5ms)

Benefits:
- Prevents Redis memory exhaustion for transient data
- Automatic cleanup of cold execution artifacts
- No manual maintenance required

## FAQ

### What happens to data being accessed when it expires?

The sliding window pattern means **actively accessed data never expires**. Only cold (unused) data expires.

### Why don't definitions have TTL?

User-defined schemas (Workflows, Steps, Services, Connectors) should persist indefinitely:
- They represent the user's application structure
- Deleting them breaks applications
- They should only be removed when the user explicitly deletes them

### Why don't queues have TTL?

Queues are self-cleaning:
- Workers process items and remove them from queues
- Empty queue segments are cleaned up automatically
- TTL would risk losing unprocessed work

### Can I add TTL to definitions?

Set a very long TTL manually if needed:

```bash
# NOT RECOMMENDED - but possible
redis-cli EXPIRE "blazing:my-app:workflow_definition:Step:01234" 31536000  # 1 year
```

### How do I verify TTL is working?

Run the test suite:

```bash
uv run pytest tests/test_z_dao_ttl.py -v
```

## Lexicon 2.0 Migration

The TTL configuration uses Lexicon 2.0 terminology:

| Old Name | New Name | Description |
|----------|----------|-------------|
| `TTL_UNIT_DEFINITION_UNIT` | `TTL_RUN_DEFINITION_RUN` | Run records |
| `TTL_UNIT_DEFINITION_OPERATION` | `TTL_RUN_DEFINITION_STEP_RUN` | StepRun records |
| `TTL_UNIT_DEFINITION_STORAGE` | `TTL_RUN_DEFINITION_STORAGE` | Storage records |
| `TTL_ROUTE_DEFINITION_ROUTE` | Removed | Workflows have no TTL |
| `TTL_ROUTE_DEFINITION_STATION` | Removed | Steps have no TTL |
| `TTL_QUEUE_OPERATION` | Removed | Queues have no TTL |

## See Also

- [Dual Redis Architecture](redis-architecture.md) - How Coordination and Data Redis instances work together
- [CRDT Multi-Master Queues](crdt-multimaster-queues.md) - Queue architecture
- [Lexicon v2.0](LEXICON.md) - Terminology mapping
