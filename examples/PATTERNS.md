# Blazing Patterns Reference

**This is the canonical reference for Blazing Flow patterns. All examples MUST follow these patterns.**

This document establishes the one correct way to use each Blazing feature. When in doubt, refer to this document for the authoritative pattern. All code examples in this repository should match these patterns exactly.

## Table of Contents

- [Core Patterns](#core-patterns)
  - [Basic Workflow](#basic-workflow)
  - [Step Definition](#step-definition)
  - [Workflow Execution](#workflow-execution)
  - [Service Injection](#service-injection)
- [Endpoint Patterns](#endpoint-patterns)
  - [Basic HTTP Endpoint](#basic-http-endpoint)
  - [Middleware](#middleware)
  - [Authentication](#authentication)
- [Sandbox Patterns](#sandbox-patterns)
  - [Sandboxed Step](#sandboxed-step)
  - [Full Sandbox Flow](#full-sandbox-flow)
- [Anti-Patterns](#anti-patterns)

---

## Core Patterns

### Basic Workflow

**Correct Pattern:**

```python
from blazing import Blazing
import asyncio

async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def double(x: int, services=None):
        """Double a number."""
        return x * 2

    @app.step
    async def add_ten(x: int, services=None):
        """Add 10 to a number."""
        return x + 10

    @app.workflow
    async def process_number(x: int, services=None):
        """Workflow: double then add 10."""
        doubled = await double(x, services=services)
        result = await add_ten(doubled, services=services)
        return result

    await app.publish()

    # Execute workflow
    result = await app.process_number(5).wait_result()
    print(result)  # 20

if __name__ == "__main__":
    asyncio.run(main())
```

**Key Elements:**
- Use `@app.workflow` decorator for orchestration functions
- Use `@app.step` decorator for computation units
- Use `app.publish()` to deploy workflows
- Use `async def main()` pattern with `asyncio.run(main())`
- Workflows must be `async def`; steps support both `async def` (NON-BLOCKING) and `def` (BLOCKING)
- Declare `services=None` on a function when it needs service injection; it is optional

**Incorrect Patterns:**

```python
# ❌ WRONG: Using deprecated imports
from blazing import task, workflow  # NO - these are deprecated

# ❌ WRONG: Using app.run() instead of app.publish()
await app.run()  # NO - app.run() is deprecated, use app.publish()
```

---

### Step Definition

**Correct Pattern:**

```python
@app.step
async def process_data(data: dict, services=None):
    """Process data with full type hints and services injection."""
    # Access services if needed
    if services and services.connectors:
        postgres = services.connectors.postgres
        # Use connector...

    return {"processed": True, "data": data}
```

**Key Elements:**
- Use `@app.step` decorator (not `@app.task` which is deprecated)
- `async def` for I/O-bound work (routes to NON-BLOCKING worker); `def` for CPU-bound work (routes to BLOCKING worker)
- Declare `services=None` when the step needs to use connectors or auth context
- Use type hints for parameters and return values
- Include docstring

**Incorrect Patterns:**

```python
# ❌ WRONG: Using deprecated @task decorator
from blazing import task
@task
async def process_data(data):
    pass
```

---

### Workflow Execution

There are three correct ways to execute workflows:

**Option 1: app.publish() with direct invocation (Recommended):**

```python
async def main():
    app = Blazing()

    @app.workflow
    async def my_workflow(x: int, services=None):
        return x * 2

    await app.publish()

    # Execute with wait_result()
    result = await app.my_workflow(5).wait_result()
    print(result)  # 10
```

**Option 2: Using asyncio.run() with workflow function:**

```python
async def main():
    app = Blazing()

    @app.workflow
    async def my_workflow(x: int, services=None):
        return x * 2

    await app.publish()

    # Execute the workflow function directly
    result = await my_workflow(5, services=None)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

**Option 3: SyncBlazing for prototyping (NOT for production):**

```python
from blazing import SyncBlazing

def main():
    app = SyncBlazing()  # Synchronous wrapper

    @app.step
    async def double(x: int, services=None):
        return x * 2

    @app.workflow
    async def my_workflow(x: int, services=None):
        return await double(x, services=services)

    app.publish()  # Synchronous - no await
    result = app.my_workflow(5)  # Synchronous - no await
    print(result)

if __name__ == "__main__":
    main()
```

**Note:** `SyncBlazing` is designed for learning and prototyping. For production code, use the async `Blazing` class with `asyncio.run()`.

**Incorrect Patterns:**

```python
# ❌ WRONG: Using app.run() instead of app.publish()
await app.run()  # NO - deprecated, use app.publish()

# ❌ WRONG: Importing deprecated workflow/task decorators
from blazing import workflow, task  # NO - these imports are deprecated
```

---

### Service Injection

**Correct Pattern:**

```python
from blazing import Blazing

async def main():
    app = Blazing()

    @app.step
    async def query_database(user_id: int, services=None):
        """Query database using injected service."""
        # Access connectors via services parameter
        if services and services.connectors:
            postgres = services.connectors.postgres
            result = await postgres.fetch_one(
                "SELECT * FROM users WHERE id = $1",
                user_id
            )
            return result
        return None

    @app.workflow
    async def get_user(user_id: int, services=None):
        """Workflow with service injection."""
        # Access auth context
        if services and services.auth_context:
            current_user = services.auth_context.user_id
            print(f"Request by user: {current_user}")

        # Call step with services forwarding
        user = await query_database(user_id, services=services)
        return user

    await app.publish()
```

**Key Elements:**
- Declare `services=None` on any function that needs to access connectors or auth context
- Access services via `services.connectors`, `services.auth_context`, etc.
- Forward services when calling steps that use it: `await step(arg, services=services)`
- Check if services is not None before accessing attributes

**Incorrect Patterns:**

```python
# ❌ WRONG: Calling a service-dependent step without declaring services
@app.step
async def query_database(user_id: int):  # needs services but didn't declare it
    pass

# ❌ WRONG: Not forwarding services to sub-steps
@app.workflow
async def get_user(user_id: int, services=None):
    user = await query_database(user_id)  # NO - missing services=services
    return user
```

---

## Endpoint Patterns

### Basic HTTP Endpoint

**Correct Pattern:**

```python
from blazing import Blazing
from blazing.web import create_asgi_app

async def main():
    app = Blazing()

    @app.endpoint(path="/health")
    @app.workflow
    async def health_check(services=None):
        """HTTP endpoint at POST /health"""
        return {"status": "healthy", "version": "1.0.0"}

    @app.endpoint(path="/calculate")
    @app.workflow
    async def calculate(x: int, y: int, services=None):
        """HTTP endpoint at POST /calculate with JSON body."""
        return {"result": x + y}

    await app.publish()
    fastapi_app = await create_asgi_app(app, title="My API")

    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

**Key Elements:**
- Use `@app.endpoint(path="/route")` decorator before `@app.workflow`
- Default method is POST
- Function parameters become request body fields (JSON)
- Use `create_asgi_app()` to create ASGI application
- Must call `app.publish()` before creating ASGI app

---

### Middleware

**Per-Endpoint Middleware (Recommended):**

```python
from blazing import Blazing
from blazing.middleware import (
    RateLimitMiddleware,
    CacheMiddleware,
    TimeoutMiddleware,
)

async def main():
    app = Blazing()

    @app.endpoint(
        path="/api/data",
        middleware=[
            RateLimitMiddleware(requests_per_minute=100),
            CacheMiddleware(ttl=60),
            TimeoutMiddleware(timeout_seconds=30),
        ]
    )
    @app.workflow
    async def get_data(services=None):
        return {"data": "example"}

    await app.publish()
```

**App-Level Middleware:**

```python
from blazing import Blazing
from blazing.middleware import (
    CORSMiddleware,
    LoggingMiddleware,
    CompressionMiddleware,
)

async def main():
    app = Blazing()

    # Add middleware to all endpoints
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        LoggingMiddleware,
        log_level="INFO",
    )
    app.add_middleware(
        CompressionMiddleware,
        min_size=1000,
    )

    @app.endpoint(path="/data")
    @app.workflow
    async def get_data(services=None):
        return {"data": "example"}

    await app.publish()
```

**Available Middleware Classes:**

From `blazing.middleware`:
- `CORSMiddleware` - Cross-Origin Resource Sharing
- `RateLimitMiddleware` - Request rate limiting
- `CacheMiddleware` - Response caching
- `TimeoutMiddleware` - Request timeout enforcement
- `RetryMiddleware` - Automatic retry with backoff
- `CircuitBreakerMiddleware` - Circuit breaker pattern
- `LoggingMiddleware` - Request/response logging
- `CompressionMiddleware` - Response compression

**Key Elements:**
- Per-endpoint: Pass `middleware=[...]` to `@app.endpoint()`
- App-level: Call `app.add_middleware(MiddlewareClass, **config)`
- Import middleware classes from `blazing.middleware`

---

### Authentication

**Correct Pattern:**

```python
from blazing import Blazing
from blazing.auth import JWTAuth, APIKeyAuth, OAuth2Auth, BasicAuth, AuthContext

async def main():
    app = Blazing()

    # JWT Authentication
    @app.endpoint(
        path="/internal/data",
        auth=JWTAuth(
            secret_key="your-secret-key",
            algorithm="HS256",
        )
    )
    @app.workflow
    async def get_internal_data(services=None):
        # Access authenticated user via services
        if services and services.auth_context:
            user_id = services.auth_context.user_id
            return {"user_id": user_id, "data": "sensitive"}
        return {"error": "Not authenticated"}

    # API Key Authentication
    @app.endpoint(
        path="/webhook",
        auth=APIKeyAuth(
            header="X-API-Key",
            keys=["key1", "key2"],
        )
    )
    @app.workflow
    async def webhook_handler(services=None):
        return {"status": "received"}

    # Multiple auth strategies (try in order)
    @app.endpoint(
        path="/flexible",
        auth=[JWTAuth(), APIKeyAuth()],
    )
    @app.workflow
    async def flexible_endpoint(services=None):
        return {"status": "ok"}

    # Custom auth handler
    async def custom_auth(request) -> AuthContext | None:
        token = request.headers.get("X-Custom-Token")
        if validate_custom_token(token):
            return AuthContext(user_id="custom-user")
        return None

    @app.endpoint(
        path="/custom",
        auth=custom_auth,
    )
    @app.workflow
    async def custom_endpoint(services=None):
        return {"status": "ok"}

    await app.publish()

def validate_custom_token(token):
    return token == "valid-token"
```

**Available Auth Strategies:**

From `blazing.auth`:
- `JWTAuth` - JWT token validation
- `APIKeyAuth` - API key validation (header or query param)
- `OAuth2Auth` - OAuth2 authentication flow
- `BasicAuth` - HTTP Basic authentication
- `CompositeAuth` - Multiple auth strategies combined
- `NoAuth` - Explicitly disable authentication
- `AuthContext` - Authentication context object

**Key Elements:**
- Use `auth=` parameter on `@app.endpoint()` decorator (NOT `auth_handler=` which is deprecated)
- Import auth strategies from `blazing.auth`
- Access authenticated user via `services.auth_context`
- Custom auth handlers must return `AuthContext | None`

**Incorrect Patterns:**

```python
# ❌ WRONG: Using deprecated auth_handler parameter
@app.endpoint(path="/secure", auth_handler=verify_jwt)  # NO - use auth=

# ❌ WRONG: Using old parameter name
@app.endpoint(path="/secure", auth_handler=JWTAuth())  # NO - use auth=
```

---

## Sandbox Patterns

### Sandboxed Step

**Correct Pattern:**

```python
from blazing import Blazing
from blazing import execute_signed_function

async def main():
    app = Blazing()

    @app.step(sandboxed=True)
    async def untrusted_computation(code: str, services=None):
        """Execute untrusted code in Pyodide sandbox."""
        result = await execute_signed_function(
            code,
            timeout=5.0,
        )
        return result

    @app.workflow
    async def safe_execution(user_code: str, services=None):
        """Safely execute user-provided code."""
        result = await untrusted_computation(user_code, services=services)
        return result

    await app.publish()
```

**Key Elements:**
- Use `@app.step(sandboxed=True)` for steps that execute untrusted code
- Use `execute_signed_function()` to execute code in Pyodide sandbox
- Sandbox provides memory isolation and limited API access
- Specify timeout to prevent infinite loops

---

### Full Sandbox Flow

**Correct Pattern:**

```python
from blazing import Blazing
from blazing import (
    serialize_user_function,
    execute_signed_function,
    create_signing_key,
)

async def main():
    app = Blazing(
        signing_key=create_signing_key(),
        enable_attestation=True,
    )

    # Serialize user function client-side
    def user_function(x: int) -> int:
        return x * 2

    serialized = serialize_user_function(user_function)

    @app.step(sandboxed=True)
    async def execute_user_code(serialized_func: str, args: list, services=None):
        """Execute serialized user function in sandbox."""
        result = await execute_signed_function(
            serialized_func,
            args=args,
            timeout=10.0,
        )
        return result

    @app.workflow
    async def run_user_workflow(func_code: str, input_data: list, services=None):
        """Workflow that executes user-provided functions safely."""
        result = await execute_user_code(func_code, input_data, services=services)
        return result

    await app.publish()

    # Execute with serialized function
    result = await app.run_user_workflow(serialized, [5]).wait_result()
    print(result)  # 10
```

**Key Elements:**
- Use `serialize_user_function()` to serialize untrusted functions
- Use `create_signing_key()` to generate signing key for attestation
- Pass `signing_key` and `enable_attestation=True` to Blazing constructor
- Use `@app.step(sandboxed=True)` for execution step
- Use `execute_signed_function()` with serialized code
- Specify timeout for safety

---

## Anti-Patterns

**Common mistakes to avoid:**

### 1. Using app.run() instead of app.publish()

```python
# ❌ WRONG
await app.run()

# ✅ CORRECT
await app.publish()
```

`app.run()` is deprecated. Always use `app.publish()`.

---

### 2. Using deprecated imports

```python
# ❌ WRONG
from blazing import task, workflow

@task
async def my_task():
    pass

@workflow
async def my_workflow():
    pass

# ✅ CORRECT
from blazing import Blazing

app = Blazing()

@app.step
async def my_step(services=None):
    pass

@app.workflow
async def my_workflow(services=None):
    pass
```

The standalone `task` and `workflow` decorators are deprecated. Use `@app.step` and `@app.workflow` instead.

---

### 3. Using auth_handler parameter

```python
# ❌ WRONG
@app.endpoint(path="/secure", auth_handler=verify_jwt)

# ✅ CORRECT
from blazing.auth import JWTAuth

@app.endpoint(path="/secure", auth=JWTAuth())
```

The `auth_handler=` parameter is deprecated. Use `auth=` instead.

---

### 4. Missing services parameter

```python
# ❌ WRONG
@app.step
async def my_step(x: int):
    return x * 2

@app.workflow
async def my_workflow(x: int):
    return await my_step(x)

# ✅ CORRECT
@app.step
async def my_step(x: int, services=None):
    return x * 2

@app.workflow
async def my_workflow(x: int, services=None):
    return await my_step(x, services=services)
```

Declare `services=None` on functions that need service injection, and forward it to sub-steps that also use services.

---

### 5. Synchronous workflow functions

```python
# ❌ WRONG: workflows must be async
@app.workflow
def my_workflow(x: int, services=None):  # NO - @app.workflow enforces async
    return x * 2

# ✅ CORRECT: workflow is async
@app.workflow
async def my_workflow(x: int, services=None):
    return await my_step(x, services=services)

# ✅ ALSO CORRECT: sync @app.step routes to BLOCKING worker
@app.step
def my_step(x: int, services=None):
    return x * 2  # CPU-bound work, runs on blocking worker pool
```

`@app.workflow` enforces `async def` at decoration time. `@app.step` accepts both — sync steps default to the BLOCKING worker queue, async steps default to NON-BLOCKING.

---

### 6. Not forwarding services to sub-steps

```python
# ❌ WRONG
@app.workflow
async def my_workflow(x: int, services=None):
    # Missing services=services argument
    result = await my_step(x)
    return result

# ✅ CORRECT
@app.workflow
async def my_workflow(x: int, services=None):
    # Forward services to sub-step
    result = await my_step(x, services=services)
    return result
```

Always forward the `services` parameter when calling steps from workflows.

---

## Summary

**Core Rules:**
1. Use `@app.step` and `@app.workflow` decorators (not deprecated standalone decorators)
2. Use `app.publish()` to deploy (not deprecated `app.run()`)
3. Workflows must be `async def`; steps support both `async def` (NON-BLOCKING) and `def` (BLOCKING). Declare `services=None` when a function needs service injection
4. Always forward `services` when calling sub-steps
5. Use `auth=` parameter for authentication (not deprecated `auth_handler=`)
6. Import middleware from `blazing.middleware`
7. Import auth strategies from `blazing.auth`
8. Use `@app.step(sandboxed=True)` for untrusted code execution
9. Use `asyncio.run(main())` for async execution
10. Use `SyncBlazing` only for prototyping, not production

**Quick Reference Imports:**

```python
# Core
from blazing import Blazing, SyncBlazing

# Web
from blazing.web import create_asgi_app

# Middleware
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

# Authentication
from blazing.auth import (
    JWTAuth,
    APIKeyAuth,
    OAuth2Auth,
    BasicAuth,
    CompositeAuth,
    AuthContext,
    NoAuth,
)

# Sandbox
from blazing import (
    run_sandboxed,
    serialize_user_function,
    execute_signed_function,
    create_signing_key,
)
```
