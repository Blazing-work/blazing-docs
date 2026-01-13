# Service Versioning Architectural Proposal

## Overview

`blazing` currently stores a single mutable record per service name. Publishing a new revision overwrites that record, so long-running jobs or queued routes can lose the service implementation they were created with. This document proposes a backwards-compatible versioning model that allows multiple revisions of the same service to coexist, enables safe phased rollouts, and exposes tooling to manage the lifecycle of older versions.

## Goals

- Preserve the existing ergonomics of `@app.service` and `@app.route` for the common case.
- Allow multiple versions of the same service to be registered and instantiated side by side.
- Let callers opt into specific versions by name without affecting other routes or background work.
- Guarantee that only one `latest` version exists per service name at any point in time.
- Provide operational tooling to list, deprecate, or delete historical versions.

## Non-Goals

- Refactoring connector lifecycle management.
- Automating progressive delivery (percentage rollouts, automatic expiry). Those features can be layered on after core versioning support lands.

## Data Model

Each service revision continues to be represented by a row in `ServiceDAO`. We add several fields:

```python
class ServiceDAO(HashModel):
    name: str = Field(index=True)                 # unchanged
    version: str = Field(default="1.0", index=True)
    latest: bool = Field(default=True, index=True)
    status: ServiceStatus = Field(default=ServiceStatus.active)
    registered_at: datetime = Field(default_factory=utc_now, index=True)
```

- `version` is a free-form string; publishers own their versioning scheme (semantic versions, dates, git hashes, etc.).
- `latest` marks the canonical version returned when callers request "whatever's current".
- `status` lets us track additional lifecycle state (`active`, `deprecated`, `disabled`). `ServiceStatus` is a small enum.
- `registered_at` provides ordering for debugging and clean-up tooling.

### Enforcing Uniqueness

`HashModel` does not provide compound unique constraints, so we introduce a small uniqueness index:

1. Compose an index key: `blazing:index:service:{name}:{version}`.
2. During registration, call `SETNX` against that key with the service's `pk`. If the command returns `0`, a row already exists and the registrar should return it (or raise if the metadata differs).
3. When deleting a version, remove the index key as well.

Because `SETNX` is atomic, this pattern prevents duplicate `(name, version)` rows even if multiple publishers attempt to register the same version concurrently.

### Maintaining the Latest Pointer

When we mark a new version as latest we must demote the previous one. We take a per-service Redis lock to serialize these updates and keep the race window small:

```python
lock_key = f"blazing:lock:service:{name}"
async with redis_client.lock(lock_key, timeout=10):
    existing = await ServiceDAO.find(
        (ServiceDAO.name == name) & (ServiceDAO.version == version)
    ).first()
    if existing:
        return existing, False

    record = ServiceDAO(
        name=name,
        version=version,
        target_module_name=module,
        target_class_name=klass,
        methods=json.dumps(methods),
    )
    await record.save()

    previous_latest = await ServiceDAO.find(
        (ServiceDAO.name == name) & (ServiceDAO.latest == True)
    ).first()
    if previous_latest:
        await Util.update_fields_in_transaction(
            ServiceDAO,
            previous_latest.pk,
            {"latest": False}
        )

    await Util.update_fields_in_transaction(
        ServiceDAO,
        record.pk,
        {"latest": True, "status": ServiceStatus.active}
    )
```

The lock works in tandem with the uniqueness index. Even if the lock is briefly contested, `SETNX` ensures we never produce duplicate versions, while the lock guarantees at most one version carries the `latest` flag.

## Runtime Behaviour

### Registration Flow

1. `@app.service` runs during application bootstrap and schedules the async registration helper.
2. The helper computes metadata (import path, declared methods) and calls `ServiceDAO.get_or_create(name=name, version=version)`.
3. Inside the lock, the helper inserts the new row, demotes the old latest (if one exists), updates metadata fields, and releases the lock.
4. All consumers (routes, workers, CLI) now see both the new revision and any historical revisions.

### Fetching Services

`Services.fetch_all_services` gains a `version_pins` parameter while keeping the default behaviour intact:

```python
class Services:
    @classmethod
    async def fetch_all_services(cls, connectors, *, version_pins=None):
        version_pins = version_pins or {}

        pinned_rows = await cls._lookup_versions(version_pins)

        latest_rows = await ServiceDAO.find(ServiceDAO.latest == True).all()

        rows = cls._merge_rows(pinned_rows, latest_rows)
        return await cls._instantiate(rows, connectors)
```

- `version_pins` is a mapping `{service_name: version}`. Callers can pin as many or as few services as they need.
- Services not explicitly pinned continue to use the latest version.
- Instantiation reuses connector instances; we do not rebuild connectors inside routes.

### Decorator APIs

Both decorators remain backwards compatible with zero-argument usage:

```python
def service(self, cls=None, *, version="1.0"):
    if cls is None:
        return functools.partial(self.service, version=version)
    # existing registration logic...

def route(self, _func=None, *, version_pins=None):
    def decorator(route_func):
        ...
    if _func is None:
        return decorator
    return decorator(_func)
```

- Existing code that uses `@app.service` or `@app.route` without parentheses keeps working.
- Publishers opt into versioning by writing `@app.service(version="2.1.0")`.
- Routes that require a specific revision provide `@app.route(version_pins={"MyService": "1.5"})`.

### Programmatic Access

Add `Blazing.interact(service_name, version=None)`:

- With `version=None`, the method returns the latest revision.
- With `version="x.y"`, it returns that specific revision or raises `ValueError` if it does not exist.
- The helper wraps `ServiceDAO.find` and reuses `Services._instantiate` so the caller receives a fully initialised service instance that shares connectors with the rest of the app.

## Management Tooling

A lightweight CLI (`blazing-cli services ...`) keeps operators away from raw Redis:

1. `list [--all] <service>` - show every version, its status, whether it is latest, and `registered_at`.
2. `deprecate <service> <version>` - flip `status` to `deprecated`. Routes may log warnings when loading deprecated versions.
3. `delete <service> <version>` - remove the row and associated uniqueness index (guard against deleting the current latest unless `--force` is provided).

Future extensions could include commands to pin versions for specific environments or to export/import version metadata.

## Migration Strategy

1. Introduce the new fields with defaults (`version="1.0"`, `latest=True`, `status=active`, `registered_at=utc_now()`).
2. Run a migration script that:
   - Iterates over existing rows.
   - Sets a default version for rows missing one.
   - Ensures only a single row per service name retains `latest=True` (pick the most recently touched record).
   - Seeds the uniqueness index for every `(name, version)` pair.
3. Deploy the updated decorators and runtime logic once the data backfill is complete.

The migration is idempotent and can be rerun during deploys if needed.

## Testing Strategy

- Unit tests for `ServiceDAO.get_or_create` covering new registrations, duplicate registrations, latest flag transitions, and lock behaviour.
- Integration tests that publish multiple versions of the same service, execute routes with and without pins, and assert that the expected implementation is invoked.
- Regression tests for decorator ergonomics (`@app.route` without parentheses, multiple routes pinning different versions).
- CLI tests that stub Redis and verify list/deprecate/delete flows.

## Observability

- Emit structured logs whenever a service version is registered (`name`, `version`, `latest`, `status`).
- Add counters such as `service_version.registered` and `service_version.deprecated`, tagged by service name.
- When a route loads a deprecated version, log a warning so operators can identify lingering pins.

## Open Questions

1. **Version Naming** - do we enforce a naming convention (semver) or keep the field free-form?
2. **Auto-Deprecation** - should we automatically mark the previous latest as `deprecated`, or leave that decision to operators?
3. **Retention Policy** - do we need an automated cleanup job for very old versions?
4. **Connector Compatibility** - if a service upgrade requires different connector configuration, how do we express that? One option is to version connectors separately and allow routes to pin connectors alongside services.

These answers will influence future CLI features and deployment automation but are not blockers for the initial implementation described above.
