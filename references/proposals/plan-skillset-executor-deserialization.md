# Plan: Move Service Deserialization to Executor Sandbox

## Current State (UNSAFE)

Services are currently deserialized on the **coordinator** (coordinator), which is a security risk:

```
Coordinator startup:
  WorkerThread._async_init()
    → Services.fetch_all_services()
      → _load_single_service()
        → load_service_from_dao()  [environment_manager.py:305]
          → dill.loads(serialized_bytes)  ← UNSAFE: runs on coordinator
```

The coordinator then passes loaded services to workers, but the executor **doesn't receive services at all** currently.

## Problem Analysis

1. **Security Risk**: `dill.loads()` on the coordinator can execute arbitrary code
2. **Services ARE needed**: They provide connectors (DB, API clients) to user functions
3. **Current executor gap**: Executor doesn't inject services into function execution

## Proposed Architecture

### Phase 1: Store service metadata (no code change to execution)
- Store service class serialization in Redis (already done via `serialized_class`)
- Store service dependencies/environment spec (already done)

### Phase 2: Executor-side service loading
- Executor loads services lazily on first use
- Service deserialization happens in the sandbox
- Services are cached per-executor instance

### Phase 3: Remove coordinator-side service loading
- Remove `Services.fetch_all_services()` from WorkerThread
- Remove services parameter from execute_operation chain

## Implementation Steps

### Step 1: Add service loading to executor_service.py

```python
# executor_service.py

# Global cache for loaded services (per-executor instance)
_service_cache: Dict[str, Any] = {}

async def _load_service(service_name: str) -> Any:
    """Load a service in the executor sandbox."""
    if service_name in _service_cache:
        return _service_cache[service_name]

    # Fetch from Redis
    from blazing_service.data_access.data_access import ServiceDAO
    service_dao = await ServiceDAO.find(
        ServiceDAO.name == service_name,
        ServiceDAO.latest == True
    ).first()

    if not service_dao or not service_dao.serialized_class:
        raise ValueError(f"Service {service_name} not found")

    # SECURITY: Deserialization happens HERE, in the executor sandbox
    import dill
    import base64
    serialized_bytes = base64.b64decode(service_dao.serialized_class.encode('utf-8'))
    service_class = dill.loads(serialized_bytes)

    # Instantiate with connectors
    connectors = await _get_connectors()  # TODO: implement
    service_instance = await service_class.create(connectors)

    _service_cache[service_name] = service_instance
    return service_instance

async def _get_all_services() -> Dict[str, Any]:
    """Load all latest services in the executor sandbox."""
    from blazing_service.data_access.data_access import ServiceDAO

    services = {}
    query = ServiceDAO.find(ServiceDAO.latest == True)
    for service_dao in await query.all():
        services[service_dao.name] = await _load_service(service_dao.name)

    return services
```

### Step 2: Inject services into function execution

```python
# In _execute_task():

# Load services in executor (safe - we're in sandbox)
services = await _get_all_services()

# Inject into kwargs if function accepts services parameter
import inspect
sig = inspect.signature(func)
if 'services' in sig.parameters:
    kwargs['services'] = services

result = await executor.execute_function(func, args=args, kwargs=kwargs)
```

### Step 3: Update station wrappers to use services

Station wrappers (in executor) need access to services for connector usage:

```python
# In _inject_station_wrappers():

async def station_wrapper(*args, _station_pk=station_pk, _station_name=station_name, **kwargs):
    # Inject services if not already present
    if 'services' not in kwargs:
        kwargs['services'] = await _get_all_services()

    # ... rest of wrapper
```

### Step 4: Remove coordinator-side service loading

```python
# In WorkerThread._async_init():
# REMOVE: self.services = await Services.fetch_all_services(connectors)

# In WorkerAsync.__init__():
# REMOVE: self.services = services

# In execute_operation/execute_next_operation:
# REMOVE: services parameter (already not used, just passed through)
```

## Test Plan

1. **Unit test**: Mock service loading in executor
2. **Integration test**: Full flow with services that use connectors
3. **Security test**: Verify no dill.loads on coordinator after changes

## Rollback Plan

If issues arise:
1. Re-add coordinator-side service loading
2. Pass services to executor via new API parameter
3. Executor uses passed services instead of loading from Redis

## Timeline Estimate

- Phase 1: Already done (services stored in Redis)
- Phase 2: 2-4 hours (executor-side loading + injection)
- Phase 3: 1 hour (cleanup coordinator-side code)
- Testing: 2 hours

## Open Questions

1. **Connector management**: How should executors get connector credentials?
   - Option A: Pass via environment variables
   - Option B: Fetch from Redis (encrypted)
   - Option C: Inject via API at execution time

2. **Service caching**: Should executors cache services per-operation or globally?
   - Per-operation: More isolated, but slower
   - Global: Faster, but state leakage risk

3. **Environment setup**: Services may require specific packages
   - Should executor containers have all packages pre-installed?
   - Or dynamically install on first use?

## Dependencies

- Executor must have Redis access (already has)
- Executor must have connector credentials (TBD)
- Tests for service-using functions (currently missing)
