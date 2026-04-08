# API Reference

This document provides a detailed reference for Blazing's public API.

## `Blazing` Class

The main entry point for a Blazing application.

### `Blazing(redis_config, encryption_key=None, connector_configs=None, ...)`

Initializes the Blazing application.

**Arguments:**

*   `redis_config` (dict): Configuration for the Redis connection (e.g., `{'host': 'localhost', 'port': 6379}`).
*   `encryption_key` (str, optional): A key for encrypting and decrypting sensitive data, such as connector credentials.
*   `connector_configs` (list, optional): A list of configurations for connectors.
*   `flushall` (bool, optional): If `True`, it will flush the entire Redis database on `publish()`. Defaults to `False`.

### `async with app:`

The `Blazing` object can be used as an async context manager. This is the recommended way to ensure that resources are properly managed.

### `app.publish()`

Registers all decorated workflows, steps, and services in Redis. This should be called before starting the Coordinator.

### `app.run(workflow_name, *args, **kwargs)`

Creates and enqueues a new task for a specified route.

**Arguments:**

*   `workflow_name` (str): The name of the workflow to execute.
*   `*args`, `**kwargs`: The arguments to pass to the route function.

**Returns:**

*   A `Unit` object that represents the execution of the workflow.

### `unit.wait_for_result()`

Waits for the `Unit` of work to complete and returns its result.

**Returns:**

*   The result of the workflow's execution.

---

## Decorators

### `@app.workflow`

A decorator to register an `async` function as a workflow.

**Usage:**

```python
@app.workflow
async def my_workflow(arg1, services=None):
    # ...
```

**Requirements:**

*   The decorated function must be `async` (`@app.workflow` enforces this at decoration time).
*   Declare `services=None` when the function needs service injection; it is optional.

### `@app.step`

A decorator to register a function as a step.

**Usage:**

```python
@app.step
async def my_async_step(data, services=None):
    # ...

@app.step
def my_blocking_step(data, services=None):
    # ...
```

**Requirements:**

*   The decorated function can be `async` (routes to NON-BLOCKING worker) or synchronous (routes to BLOCKING worker).
*   Declare `services=None` when the step needs service injection; it is optional.

### `@app.service`

A decorator to register a class as a service.

**Usage:**

```python
@app.service
class MyService(BaseService):
    def __init__(self, connector_instances=None):
        # ...
```

**Requirements:**

*   The decorated class should typically inherit from `BaseService`.

---

## `BaseService` Class

A base class for creating services.

**Usage:**

```python
from blazing import BaseService

# Service with connectors — declare connector_instances
class MyService(BaseService):
    def __init__(self, connector_instances=None):
        self.db_connection = (connector_instances or {}).get("my_db")

    def my_method(self):
        # ...

# Pure-compute service — connector_instances omitted entirely
class MathService(BaseService):
    async def add(self, a: float, b: float) -> float:
        return a + b
```

`connector_instances` is **optional**. Declare it when your service needs connectors; omit it for pure-compute services. The executor injects it automatically when declared.
