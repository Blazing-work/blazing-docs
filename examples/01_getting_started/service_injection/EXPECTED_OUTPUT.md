# Expected Output

## Running

```bash
python flow.py
```

## Output

```
Hello, Bob! (ID: 2)
```

## Notes

- The `services` parameter is automatically passed through the workflow chain
- Custom services can be any Python object with methods or attributes
- Services are typically used for:
  - Database connections
  - API clients
  - Configuration objects
  - Shared state between steps
- All `@app.step` and `@app.workflow` functions must accept `services=None` parameter
- When calling steps from workflows, always forward services: `await step(arg, services=services)`
- In this example, we create a simple `DatabaseService` class and pass it via a `CustomServices` object
- The workflow can then access `services.database` in any step
