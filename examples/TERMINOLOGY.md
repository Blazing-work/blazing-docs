# Blazing Terminology Glossary

**This glossary defines canonical terms for Blazing Flow. Code (blazing repo) is authoritative. Docs and examples must conform.**

When writing documentation or examples, always use the canonical terms defined here. Deprecated alternatives are listed for reference and should not be used in new code.

## Purpose

This glossary serves as the single source of truth for naming consistency across:
- Source code in the `blazing` repository
- Documentation in the `blazing-docs` repository
- Examples in the `blazing-examples` repository
- User-facing tutorials and guides

**Authority:** The Blazing source code is the ultimate authority. If a term appears in the code but not in this glossary, the code is correct and this glossary should be updated. If this glossary contradicts the code, the code wins.

---

## Core Concepts

| Canonical Term | Definition | Source (code reference) | Deprecated Alternatives |
|----------------|------------|-------------------------|-------------------------|
| **Workflow** | Orchestration function decorated with `@app.workflow`. Coordinates multiple steps and defines execution flow. | `src/blazing/blazing.py` (Blazing.workflow method) | "run", "unit", "job", "flow" |
| **Step** | Individual computation unit decorated with `@app.step`. Performs a single logical operation in a workflow. | `src/blazing/blazing.py` (Blazing.step method) | "task", "operation", "function" |
| **Publish** | Deploy workflow/endpoint via `app.publish()`. Makes workflows and endpoints available for execution on Blazing infrastructure. | `src/blazing/blazing.py` (Blazing.publish method) | "run", "execute", "deploy" |
| **Endpoint** | HTTP route decorated with `@app.endpoint()`. Exposes a workflow as an HTTP API endpoint. | `src/blazing/blazing.py` (Blazing.endpoint method) | "route", "handler", "API" |
| **Service** | External dependency injected via `services` parameter. Base abstraction for any external resource (databases, APIs, etc.). | `src/blazing/base.py` (BaseService class) | "dependency", "resource" |
| **Connector** | Pre-built service for common integrations (postgres, redis, smtp, etc.). Subtype of Service. | `src/blazing/base.py` (BaseConnector class) | *(Connector is specific; avoid "service" when referring to built-in connectors)* |
| **Middleware** | Request/response interceptor applied to endpoints. Handles cross-cutting concerns like CORS, rate limiting, auth. | `src/blazing/middleware/base.py` (Middleware class) | "interceptor", "filter", "plugin" |
| **Auth Strategy** | Authentication method (JWTAuth, APIKeyAuth, etc.). Validates requests and provides auth context. | `src/blazing/auth/strategies.py` (AuthStrategy classes) | "auth handler" (deprecated term), "authenticator" |
| **AuthContext** | Authentication state available via `services.auth_context`. Contains user_id, roles, claims, etc. | `src/blazing/auth/context.py` (AuthContext class) | "auth state", "user context" |
| **Sandbox** | Isolated execution environment for untrusted code. Uses Pyodide WASM runtime for memory isolation. | `@app.step(sandboxed=True)` | "isolated execution", "container", "safe mode" |
| **SyncBlazing** | Synchronous wrapper for prototyping. NOT for production use. Provides blocking API for learning. | `src/blazing/blazing.py` (SyncBlazing class) | *(Use async Blazing for production)* |

---

## Naming Conventions

### Decorator Pattern

All decorators follow the `@app.{noun}` pattern:

```python
@app.workflow  # Orchestration
@app.step      # Computation
@app.endpoint  # HTTP route
```

**NOT:**
- `@workflow` (standalone decorator - deprecated)
- `@task` (old name for step - deprecated)
- `@route` (never used)

### Method Pattern

Instance methods follow the `app.{verb}()` pattern:

```python
app.publish()         # Deploy workflows/endpoints
app.add_middleware()  # Add app-level middleware
app.run()             # DEPRECATED - use publish()
```

**NOT:**
- `app.deploy()` (not used)
- `app.execute()` (not used)

### Parameter Pattern

Declare `services=None` when a function needs service injection (connectors, auth context). It is optional — pure-compute functions can omit it:

```python
# Needs services — declare it
@app.step
async def query_db(user_id: int, services=None):
    return await services.connectors.postgres.fetch_one(...)

# Pure compute — services omitted
@app.step
async def double(x: int):
    return x * 2

@app.workflow
async def my_workflow(x: int, services=None):
    pass

@app.endpoint(path="/api")
@app.workflow
async def my_endpoint(services=None):
    pass
```

When declared, the executor injects it automatically.

---

## Deprecated Terms

The following terms are deprecated and should not be used in new code:

| Deprecated Term | Canonical Replacement | Migration Path |
|-----------------|----------------------|----------------|
| `task` | `step` | Change `@app.task` or `from blazing import task` to `@app.step` |
| `auth_handler` | `auth` (parameter name) | Change `@app.endpoint(path="/api", auth_handler=...)` to `@app.endpoint(path="/api", auth=...)` |
| `app.run()` | `app.publish()` | Change `await app.run()` to `await app.publish()` |
| `from blazing import task` | `@app.step` | Remove `task` from imports, use `@app.step` decorator |
| `from blazing import workflow` | `@app.workflow` | Remove `workflow` from imports, use `@app.workflow` decorator |

### Migration Examples

**Deprecated Task Pattern:**
```python
# ❌ OLD (deprecated)
from blazing import task

@task
async def process_data(x):
    return x * 2
```

**Current Step Pattern:**
```python
# ✅ NEW (canonical)
from blazing import Blazing

app = Blazing()

@app.step
async def process_data(x: int, services=None):
    return x * 2
```

---

**Deprecated Workflow Pattern:**
```python
# ❌ OLD (deprecated)
from blazing import workflow

@workflow
async def my_workflow(x):
    return process_data(x)
```

**Current Workflow Pattern:**
```python
# ✅ NEW (canonical)
@app.workflow
async def my_workflow(x: int, services=None):
    result = await process_data(x, services=services)
    return result
```

---

**Deprecated Auth Handler:**
```python
# ❌ OLD (deprecated)
@app.endpoint(path="/secure", auth_handler=verify_jwt)
@app.workflow
async def secure_endpoint():
    pass
```

**Current Auth Strategy:**
```python
# ✅ NEW (canonical)
from blazing.auth import JWTAuth

@app.endpoint(path="/secure", auth=JWTAuth())
@app.workflow
async def secure_endpoint(services=None):
    pass
```

---

**Deprecated app.run():**
```python
# ❌ OLD (deprecated)
await app.run()
```

**Current app.publish():**
```python
# ✅ NEW (canonical)
await app.publish()
```

---

## Lexicon Evolution

Blazing uses precise terminology that has evolved:

| Concept | v1.x Term | v2.0+ Term | Rationale |
|---------|-----------|------------|-----------|
| Computation unit | `task` | `step` | "Step" better conveys sequential workflow execution |
| Orchestration | `unit` | `workflow` | "Workflow" is more intuitive for orchestration |
| Deployment | `run()` | `publish()` | "Publish" better conveys making workflows available |
| Auth config | `auth_handler` | `auth` | Simplified parameter name, `AuthStrategy` handles logic |

**Backward Compatibility:** Deprecated terms may still work for backward compatibility but will be removed in future versions. New code should always use canonical terms.

---

## Parameter Terminology

### services Parameter

The `services=None` parameter is present on all decorated functions:

```python
@app.step
async def my_step(x: int, services=None):
    # Access injected services
    if services:
        # Auth context
        user_id = services.auth_context.user_id

        # Connectors
        postgres = services.connectors.postgres
        redis = services.connectors.redis

        # Custom services
        custom = services.my_custom_service
```

**NOT:**
- `context` (not used for service injection)
- `deps` (not used)
- `dependencies` (not used)

### Connector Access

Built-in connectors are accessed via `services.connectors.{name}`:

```python
services.connectors.postgres    # PostgreSQL
services.connectors.redis       # Redis
services.connectors.smtp        # SMTP email
services.connectors.s3          # AWS S3
services.connectors.secrets     # Secrets manager
services.connectors.web_search  # Web search
services.connectors.database    # Generic database
services.connectors.code_execution  # Code execution
services.connectors.rest        # REST API
```

**NOT:**
- `services.postgres` (wrong level)
- `app.connectors.postgres` (wrong context)

### Auth Context Access

Authentication state is accessed via `services.auth_context`:

```python
if services and services.auth_context:
    user_id = services.auth_context.user_id
    roles = services.auth_context.roles
    claims = services.auth_context.claims
```

**NOT:**
- `services.auth` (too generic)
- `services.user` (not the pattern)
- `auth_context` (not directly accessible)

---

## Module Organization

Canonical import paths for Blazing components:

### Core SDK
```python
from blazing import Blazing, SyncBlazing
from blazing import BaseService, BaseConnector
```

### Web & Endpoints
```python
from blazing.web import create_asgi_app
```

### Middleware
```python
from blazing.middleware import (
    CORSMiddleware,
    RateLimitMiddleware,
    CacheMiddleware,
    TimeoutMiddleware,
    RetryMiddleware,
    CircuitBreakerMiddleware,
    LoggingMiddleware,
    CompressionMiddleware,
)
```

### Authentication
```python
from blazing.auth import (
    JWTAuth,
    APIKeyAuth,
    OAuth2Auth,
    BasicAuth,
    CompositeAuth,
    AuthContext,
    NoAuth,
)
```

### Sandbox / Dynamic Code
```python
from blazing import (
    run_sandboxed,
    serialize_user_function,
    execute_signed_function,
    create_signing_key,
)
```

### Retry & Backoff
```python
from blazing import (
    RetryConfig,
    retry_with_backoff,
    calculate_full_jitter_delay,
)
```

### GPU & Scheduling
```python
from blazing import (
    GPUType,
    GPUConfig,
    Cron,
    Period,
    Schedule,
)
```

### Local Emulators
```python
from blazing.local import (
    LocalStack,
    LocalRegistry,
    LocalBuildService,
    LocalVolumeService,
    LocalSecretsService,
)
```

---

## Anti-Terms

Terms that should NEVER be used because they're misleading or incorrect:

| Anti-Term | Why It's Wrong | Use Instead |
|-----------|----------------|-------------|
| "job" | Too generic, doesn't distinguish workflow vs step | "workflow" or "step" |
| "function" | Too generic, every decorated thing is a function | "workflow" or "step" |
| "handler" | Implies callbacks, not appropriate for steps | "step" |
| "route" | HTTP-specific, doesn't capture workflow nature | "endpoint" |
| "plugin" | Middleware is built-in, not pluggable architecture | "middleware" |
| "validator" | Auth strategies do more than validation | "auth strategy" |
| "container" | Sandbox is WASM-based, not Docker containers | "sandbox" |

---

## Terminology Checklist

When writing documentation or examples, verify:

- [ ] Used `@app.workflow` not `@workflow` or `from blazing import workflow`
- [ ] Used `@app.step` not `@app.task` or `from blazing import task`
- [ ] Used `app.publish()` not `app.run()`
- [ ] Used `auth=` parameter not `auth_handler=`
- [ ] Functions that use services declare `services=None`; pure-compute functions may omit it
- [ ] Used "step" not "task" in prose
- [ ] Used "workflow" not "job" or "unit" in prose
- [ ] Used "endpoint" not "route" or "handler" in prose
- [ ] Used "auth strategy" not "auth handler" in prose
- [ ] Used "middleware" not "interceptor" or "plugin" in prose
- [ ] Used "sandbox" not "container" or "isolated executor" in prose
- [ ] Import paths match canonical module organization
- [ ] Services accessed via `services.connectors.{name}` pattern
- [ ] Auth context accessed via `services.auth_context` pattern

---

## Quick Reference

**Correct:**
- `@app.workflow` - orchestration decorator
- `@app.step` - computation decorator
- `@app.endpoint` - HTTP endpoint decorator
- `app.publish()` - deploy method
- `auth=` - authentication parameter
- `services=None` - service injection parameter

**Deprecated:**
- `@workflow` - use `@app.workflow`
- `@task` - use `@app.step`
- `app.run()` - use `app.publish()`
- `auth_handler=` - use `auth=`
- `from blazing import workflow, task` - use `@app.workflow`, `@app.step`

---

## Contributing

When adding new terms to this glossary:

1. **Verify against source code** - Check actual class/method names in `src/blazing/`
2. **Add source reference** - Include file path and class/method name
3. **Document deprecated alternatives** - Help users migrate from old patterns
4. **Update checklist** - Add to terminology checklist if it's a common mistake
5. **Maintain alphabetical order** - Keep tables sorted for easy lookup

**Source of truth:** If the code and glossary disagree, the code is correct.
