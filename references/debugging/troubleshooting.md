# Blazing Troubleshooting Guide

This guide documents common issues encountered when working with Blazing, particularly in Docker/REST API mode, and their solutions.

## Table of Contents
- [Serialization Issues](#serialization-issues)
- [Redis & Docker Issues](#redis--docker-issues)
- [Operation Execution Issues](#operation-execution-issues)
- [Testing Issues](#testing-issues)
- [Quick Diagnostic Commands](#quick-diagnostic-commands)

---

## Serialization Issues

### ModuleNotFoundError: No module named 'tests' (or other module)

**Symptoms:**
- Tests work the first time but fail on subsequent runs
- Coordinator logs show: `ModuleNotFoundError: No module named 'tests'`
- May also see: `_pickle.UnpicklingError: pickle data was truncated`

**Root Cause:**
When functions are defined in test files (or any module not available in the Docker container), dill serializes the module `__globals__` which contains references to `tests.test_docker_example.__dict__`. When the coordinator tries to deserialize, it needs to import the `tests` module, which doesn't exist in the Docker container.

**Diagnosis:**
1. Check coordinator logs for deserialization errors:
   ```bash
   docker logs blazing-coordinator 2>&1 | grep -E "(ModuleNotFoundError|deserialize|pickle)"
   ```

2. Inspect serialized function in Redis:
   ```bash
   # Get a station's serialized function
   docker exec blazing-redis redis-cli HGET "blazing:default:workflow_definition:Station:<station_pk>" "serialized_function" > /tmp/func.b64

   # Decode and inspect with Python
   python -c "
   import base64, pickletools
   with open('/tmp/func.b64') as f:
       data = base64.b64decode(f.read().strip())
   pickletools.dis(data)
   " | grep GLOBAL
   ```

**Solution:**
The serialization code in `src/blazing/blazing.py` already implements clean serialization using `types.FunctionType()` to strip module references. If you're still seeing this error:

1. **Clear Redis** - Old serialized functions may still be cached:
   ```bash
   docker exec blazing-redis redis-cli FLUSHDB
   docker-compose restart coordinator
   ```

2. **Verify clean serialization is active** - Check client logs for:
   ```
   🔧 SERIALIZE-STATION: 'add' original_module=tests.test_docker_example → clean_module=__main__
   ```

3. **For production code** - Deploy shared modules to both client and coordinator environments so imports work naturally.

**Prevention:**
- Always clear Redis when updating serialization code
- For production, use proper module deployment instead of test-based functions

---

### "byref=False" Doesn't Prevent Module References

**Symptoms:**
- Using `dill.dumps(func, byref=False)` but still getting import errors
- Pickle disassembly shows GLOBAL references to module `__dict__`

**Root Cause:**
`byref=False` tells dill not to serialize objects BY REFERENCE, but it still serializes `func.__globals__` which contains the module dictionary. The module reference is embedded in the serialized data.

**Solution:**
Use the clean serialization pattern (already implemented in `blazing.py`):

```python
import types

# Create minimal globals
minimal_globals = {
    '__builtins__': __builtins__,
    '__name__': '__main__',
    '__doc__': None,
    '__package__': None,
}

# Recreate function with clean globals
clean_func = types.FunctionType(
    original_func.__code__,
    minimal_globals,
    original_func.__name__,
    original_func.__defaults__,
    original_func.__closure__
)
clean_func.__module__ = '__main__'

# Now serialize
serialized = dill.dumps(clean_func, byref=False)
```

---

## Redis & Docker Issues

### Redis Search Returns 0 Results (But Data Exists)

**Symptoms:**
- Workers can't find stations: "Found 0 stations"
- But Redis has station keys when you check manually
- Operations never execute

**Root Cause:**
Redis Search indexes only work on database 0. If your application is using a different database, or if indexes weren't created, queries return empty results.

**Diagnosis:**
```bash
# Check what database you're using
docker logs blazing-api 2>&1 | grep "database\|db="
docker logs blazing-coordinator 2>&1 | grep "database\|db="

# Check if indexes exist
docker exec blazing-redis redis-cli FT._LIST

# Test if search works
docker exec blazing-redis redis-cli FT.SEARCH "blazing:workflow_definition:Station:index" "*"
```

**Solution:**
1. **Ensure database 0** - Both API and coordinator should use Redis database 0
2. **Recreate indexes** after FLUSHDB:
   ```bash
   # Restart coordinator (triggers Migrator().run())
   docker-compose restart coordinator
   ```

3. **Or manually trigger index creation** via `/v1/registry/sync` endpoint (which now runs `Migrator().run()` automatically)

**Prevention:**
- Always use database 0 for Redis Search functionality
- The `/v1/registry/sync` endpoint now automatically recreates indexes

---

### Coordinator Crash Loop After FLUSHDB

**Symptoms:**
- After `FLUSHDB`, coordinator enters crash loop
- Logs show: `NotFoundError` when trying to fetch coordinator/worker state

**Root Cause:**
`FLUSHDB` deletes ALL data including the coordinator's own state objects (CoordinatorDAO, WorkerThreadDAO, etc.). The running coordinator tries to fetch its deleted state and crashes.

**Solution:**
**ALWAYS restart coordinator after FLUSHDB:**
```bash
docker exec blazing-redis redis-cli FLUSHDB && docker-compose restart coordinator
```

**Prevention:**
- Add this pattern to test fixtures (already done in `docker_infrastructure` fixture)
- Document this requirement clearly for manual operations

---

### Docker Disk Space Issues

**Symptoms:**
- Docker becomes unresponsive
- Builds fail with "no space left on device"
- `docker system df` shows very high usage

**Diagnosis:**
```bash
docker system df
du -h ~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw
```

**Solution:**
1. **Remove unused resources:**
   ```bash
   docker system prune -a --volumes
   ```

2. **If Docker.raw is huge**, reset Docker Desktop:
   - Docker Desktop → Preferences → Resources → Advanced → "Reset to factory defaults"
   - Or manually delete Docker.raw and restart Docker Desktop

3. **Remove Colima** if you have both:
   ```bash
   colima delete
   rm -rf ~/.colima
   ```

---

### Docker Containers Running Stale Code

**Symptoms:**
- Code changes don't take effect after `docker-compose build`
- Logs show old debug messages or behavior
- Tests fail with errors that should be fixed by recent code changes

**Root Cause:**
`docker-compose build` rebuilds the image, but `docker-compose restart` doesn't recreate containers with the new image. Containers continue running with the old image until explicitly recreated.

**Diagnosis:**
1. **Check container creation time vs image build time:**
   ```bash
   docker ps --filter "name=blazing-api" --format "{{.CreatedAt}}"
   docker images blazing-api --format "{{.CreatedAt}}"
   ```

2. **Verify code in running container:**
   ```bash
   docker exec blazing-api grep "specific code pattern" /app/src/path/to/file.py
   docker exec blazing-coordinator grep "specific code pattern" /app/src/path/to/file.py
   ```

**Solution:**
**ALWAYS use `--force-recreate` when deploying code changes:**

```bash
# Rebuild images
docker-compose build --no-cache api coordinator

# Force recreate containers with new images
docker-compose up -d --force-recreate api coordinator

# Clear Redis and restart coordinator (if needed)
docker exec blazing-redis redis-cli FLUSHDB
docker-compose restart coordinator
```

**Quick rebuild script:**
```bash
#!/bin/bash
# Save as scripts/rebuild-docker.sh
echo "Rebuilding API and Coordinator..."
docker-compose build --no-cache api coordinator

echo "Recreating containers..."
docker-compose up -d --force-recreate api coordinator

echo "Clearing Redis..."
docker exec blazing-redis redis-cli FLUSHDB

echo "Restarting coordinator..."
docker-compose restart coordinator

echo "Waiting for services..."
sleep 5

echo "✓ Rebuild complete"
```

**Prevention:**
- Always use `docker-compose up -d --force-recreate` after building
- Add this to Makefile targets
- Document in test setup instructions

---

## Operation Execution Issues

### Operations Stuck in PENDING State

**Symptoms:**
- Unit status stays PENDING forever
- No AVAILABLE queues exist in Redis
- Workers are polling but finding no work
- API logs show successful enqueue: `lpush returned 1`

**Root Cause:**
This can have multiple causes:

1. **Queue key format mismatch** - API and workers using different queue key patterns
2. **API connected to wrong Redis database**
3. **Operations enqueued but immediately popped by workers who then fail**

**Diagnosis:**
```bash
# Check if operations exist
docker exec blazing-redis redis-cli KEYS "blazing:*:unit_definition:Operation:*"

# Check operation status
docker exec blazing-redis redis-cli HGETALL "blazing:default:unit_definition:Operation:<operation_pk>"

# Check for AVAILABLE queues
docker exec blazing-redis redis-cli KEYS "*:AVAILABLE"

# Check API enqueue logs
docker logs blazing-api 2>&1 | grep -E "(enqueue|LPUSH)"

# Check if workers are finding stations
docker logs blazing-coordinator 2>&1 | grep -E "Found.*stations"
```

**Solution:**
1. **Verify queue key consistency** - Check that `StationDAO.enqueue_non_blocking_operation()` and `StationDAO.dequeue_non_blocking_operation()` use the same key format:
   ```
   blazing:{app_id}:workflow_definition:Station:{station_pk}:AVAILABLE
   ```

2. **Check for deserialization errors** that cause workers to fail after dequeuing:
   ```bash
   docker logs blazing-coordinator 2>&1 | grep -A10 "execute_operation.*ENTERED"
   ```

3. **Manual test** - Try manually enqueuing and watch coordinator:
   ```bash
   # Get unit and station PKs from Redis
   UNIT_PK=$(docker exec blazing-redis redis-cli KEYS "blazing:*:unit_definition:Unit:*" | head -1 | cut -d: -f5)
   STATION_PK=$(docker exec blazing-redis redis-cli KEYS "blazing:*:workflow_definition:Station:*" | grep -v index | head -1 | cut -d: -f5)

   # Manually enqueue
   docker exec blazing-redis redis-cli LPUSH "blazing:default:workflow_definition:Station:${STATION_PK}:AVAILABLE" "$UNIT_PK"

   # Watch coordinator logs
   docker logs -f blazing-coordinator
   ```

---

### Worker Type Mismatch

**Symptoms:**
- BLOCKING workers polling NON-BLOCKING stations (or vice versa)
- Workers find stations but never find matching work
- Logs show: `Checking station X: type=NON-BLOCKING` but `operation_type=BLOCKING`

**Root Cause:**
Workers filter stations by type. If all stations are NON-BLOCKING but workers are BLOCKING type, they skip all stations.

**Diagnosis:**
```bash
# Check station types
docker exec blazing-redis redis-cli FT.SEARCH "blazing:workflow_definition:Station:index" "*" | grep -E "station_type|name"

# Check what worker types are polling
docker logs blazing-coordinator 2>&1 | grep -E "operation_type=(BLOCKING|NON-BLOCKING)" | sort | uniq -c
```

**Solution:**
Ensure you have workers of both types running (controlled by coordinator configuration). The pilot light mechanism should maintain minimum workers of each type.

---

## Testing Issues

### Tests Work First Time, Fail Second Time

**Symptoms:**
- `pytest` passes on first run
- Same test fails on second run without code changes
- Common with Docker integration tests

**Root Causes:**
1. **Serialization issue** - Old functions in Redis with module references (see [Serialization Issues](#serialization-issues))
2. **Coordinator not restarted after FLUSHDB** (see [Coordinator Crash Loop](#coordinator-crash-loop-after-flushdb))
3. **Redis Search indexes not recreated**

**Solution:**
Use the `docker_infrastructure` fixture pattern:
```python
@pytest.fixture(scope="session")
async def docker_infrastructure(redis_port, api_url):
    """Ensure clean Docker state at session start."""
    import subprocess

    # Clean Redis and restart coordinator
    subprocess.run(["docker", "exec", "blazing-redis", "redis-cli", "FLUSHDB"], check=True)
    subprocess.run(["docker-compose", "restart", "coordinator"], check=True)

    # Wait for coordinator to be ready
    await asyncio.sleep(3)

    yield
```

---

### Python Bytecode Cache Issues

**Symptoms:**
- Code changes not taking effect
- Old behavior persists after edits
- Seeing debug logs showing `module=tests.test_docker_example` even after fix applied

**Solution:**
```bash
# Clear Python bytecode cache
find /Users/jonathanborduas/code/blazing/src/blazing -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# Or use uv to ensure clean environment
uv sync --reinstall
```

---

## Quick Diagnostic Commands

### Redis Health Check
```bash
# Count keys by pattern
docker exec blazing-redis redis-cli KEYS "blazing:*:workflow_definition:Station:*" | wc -l
docker exec blazing-redis redis-cli KEYS "blazing:*:unit_definition:Unit:*" | wc -l
docker exec blazing-redis redis-cli KEYS "blazing:*:unit_definition:Operation:*" | wc -l

# Check operation status
docker exec blazing-redis redis-cli KEYS "blazing:*:unit_definition:Unit:*" | \
  xargs -I {} docker exec blazing-redis redis-cli HGET {} "current_status"

# Check for AVAILABLE queues
docker exec blazing-redis redis-cli KEYS "*:AVAILABLE"

# Test Redis Search
docker exec blazing-redis redis-cli FT.SEARCH "blazing:workflow_definition:Station:index" "*"
```

### Docker Service Logs
```bash
# API logs
docker logs blazing-api 2>&1 | tail -100

# Coordinator logs
docker logs blazing-coordinator 2>&1 | tail -100

# Filter for specific issues
docker logs blazing-coordinator 2>&1 | grep -E "(ERROR|Exception|ModuleNotFoundError)"
docker logs blazing-api 2>&1 | grep -E "(enqueue|DEBUG-Station)"
```

### Worker Status
```bash
# Count worker types
docker exec blazing-redis redis-cli KEYS "blazing:default:execution:WorkerThread:*" | \
  xargs -I {} docker exec blazing-redis redis-cli HGET {} "worker_type" | \
  sort | uniq -c

# Check worker activity
docker logs blazing-coordinator 2>&1 | grep -E "operation_type=" | tail -20
```

### Full System Reset
```bash
# Nuclear option - reset everything
docker exec blazing-redis redis-cli FLUSHDB
docker-compose restart coordinator
docker-compose restart api
sleep 5
echo "✓ System reset complete"
```

---

## Common Patterns & Best Practices

### 1. Always Clear Redis When Changing Serialization
Serialized functions are cached in Redis. After modifying serialization code:
```bash
docker exec blazing-redis redis-cli FLUSHDB && docker-compose restart coordinator
```

### 2. Check Both Client and Coordinator Logs
Issues often span both services:
- Client logs show serialization
- Coordinator logs show deserialization and execution
- API logs show HTTP requests and enqueuing

### 3. Use Manual Enqueuing to Test Worker Logic
When debugging worker issues, bypass the API and manually enqueue:
```bash
docker exec blazing-redis redis-cli LPUSH "blazing:default:workflow_definition:Station:<station_pk>:AVAILABLE" "<unit_pk>"
```

### 4. Verify Module Loading
```bash
# Check which blazing module is loaded
uv run python -c "import blazing; print(blazing.__file__)"
# Should show: /Users/.../code/blazing/src/blazing/__init__.py
```

### 5. Redis Database 0 for Redis Search
Always use database 0 when using Redis Search (FT.SEARCH). Other databases won't work with search indexes.

---

## Known Limitations

1. **Redis Search only works on database 0** - This is a Redis Search limitation, not a Blazing limitation

2. **Functions defined in test files** - Cannot be deserialized in Docker without the clean serialization pattern or deploying the test module (not recommended)

3. **Coordinator state in Redis** - Must restart coordinator after FLUSHDB to recreate state

4. **ContextVar doesn't propagate to worker threads** - app_id context must be extracted from Redis keys in worker threads

---

## Getting Help

If you encounter an issue not covered here:

1. **Check recent logs** for the specific error message
2. **Search CLAUDE.md and JOURNAL.md** for similar issues
3. **Use the diagnostic commands** above to gather evidence
4. **Document new issues** in JOURNAL.md with:
   - Symptoms
   - Root cause (if discovered)
   - Solution
   - How to prevent recurrence

---

*Last updated: 2025-11-23*
