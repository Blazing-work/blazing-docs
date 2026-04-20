# Expected Output

## Running

```bash
python flow.py
```

## Output

```
First request (cache miss):
Cache MISS for user 123 - fetching from database
Result: {'user_id': 123, 'name': 'User123', 'email': 'user123@example.com'}

Second request (cache hit):
Cache HIT for user 123
Result: {'user_id': 123, 'name': 'User123', 'email': 'user123@example.com'}

Cache statistics:
Stats: {'size': 1, 'hits': 1, 'misses': 1, 'hit_rate': 0.5}
```

## Notes

- **Custom services** extend `BaseService` from the `blazing` SDK
- Services are registered using the `@app.service` decorator
- The service class must inherit from `BaseService`
- Services receive `connector_instances` in `__init__` for accessing built-in connectors
- Services are instantiated once and reused across workflow executions
- Steps access services via the `services` parameter: `services.service_name.method()`
- Service naming: The class name (e.g., `Cache`) becomes the lowercase service name (`services.cache`)

**Lifecycle:**
1. Define service class inheriting from `BaseService`
2. Register with `@app.service` decorator
3. Call `app.publish()` to serialize and deploy
4. Service is instantiated on the server with connectors
5. Steps access via `services.service_name`

**Common use cases:**
- Database connection pools
- API clients with authentication
- Caching layers
- Rate limiters
- Custom business logic
- Third-party service integrations

**Advantages:**
- Code reuse across workflows
- Dependency injection
- Testable business logic
- State management between steps
- Access to built-in connectors
