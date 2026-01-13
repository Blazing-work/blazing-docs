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

*   The decorated function must be `async`.
*   The decorated function must accept a `services` keyword argument.

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

*   The decorated function can be `async` (for I/O-bound tasks) or synchronous (for CPU-bound tasks).
*   The decorated function must accept a `services` keyword argument.

### `@app.service`

A decorator to register a class as a service.

**Usage:**

```python
@app.service
class MyService(BaseService):
    def __init__(self, connector_instances):
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

class MyService(BaseService):
    def __init__(self, connector_instances):
        self.db_connection = connector_instances["my_db"]

    def my_method(self):
        # ...
```

The `__init__` method of a service receives a dictionary of `connector_instances` that have been configured for the application.
