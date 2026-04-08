# Expected Output

## Running

```bash
python flow.py
```

## Output

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

## Example Requests

```bash
# Health check
curl http://localhost:8080/health

# Get user by ID
curl -X POST http://localhost:8080/users/get \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1}'

# Create new user
curl -X POST http://localhost:8080/users/create \
  -H "Content-Type: application/json" \
  -d '{"name": "Diana", "email": "diana@example.com"}'

# Process data
curl -X POST http://localhost:8080/data/process \
  -H "Content-Type: application/json" \
  -d '{"data": [1, 2, 3, 4, 5], "operation": "average"}'
```

## Example Responses

### Health Check
```json
{
  "status": "healthy",
  "service": "example-api",
  "version": "1.0.0"
}
```

### Get User
```json
{
  "success": true,
  "user": {
    "id": 1,
    "name": "Alice",
    "email": "alice@example.com"
  }
}
```

### Create User
```json
{
  "success": true,
  "user": {
    "id": 999,
    "name": "Diana",
    "email": "diana@example.com",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

### Process Data
```json
{
  "operation": "average",
  "input": [1, 2, 3, 4, 5],
  "result": 3.0,
  "count": 5
}
```

## Notes

- All endpoints default to POST method
- Each `@app.endpoint(path="/route")` decorator creates a new HTTP route
- Function parameters become JSON body fields
- Server runs until interrupted (Ctrl+C)
- Multiple endpoints can be registered on the same app instance
- Each endpoint is backed by a Blazing workflow that can call steps
- Use `create_asgi_app()` to generate the ASGI application for uvicorn
