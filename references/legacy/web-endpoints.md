# Blazing Flow Endpoints for Blazing Workflows

This document describes how to expose Blazing workflows as public HTTP endpoints using the `@app.endpoint` decorator.

## Overview

**Problem**: The internal Blazing API runs in a VPC and is not publicly accessible. How do we expose workflows to external clients?

**Solution**: Wrap Blazing workflows with FastAPI endpoints that provide:
- Public HTTP/WebSocket access
- Async execution model (POST returns job_id, client polls for results)
- Custom authentication (separate from Blazing JWT)
- JSON inputs/outputs for high-level task creation

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  External       │  HTTP   │  FastAPI Layer   │  gRPC   │  Blazing API    │
│  Client         │ ──────> │  (Public)        │ ──────> │  (VPC)          │
│                 │         │  @app.endpoint   │         │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                    │
                                    │ Uses
                                    ▼
                            ┌──────────────────┐
                            │  @app.workflow   │
                            │  Blazing Client  │
                            └──────────────────┘
```

## Quick Start

### 1. Define Workflow with Endpoint Decorator

```python
from blazing import Blazing
from blazing.web import create_asgi_app
from fastapi.security import HTTPAuthorizationCredentials

app = Blazing(api_url="http://localhost:8000", api_token="test-token")

# Define internal steps (not exposed)
@app.step
async def fetch_data(user_id: int, services=None):
    return {"user_id": user_id, "score": 10}

# Define workflow exposed as public endpoint
@app.endpoint(path="/calculate", method="POST")
@app.workflow
async def calculate_score(user_id: int, multiplier: int, services=None):
    """Public workflow accessible at POST /calculate"""
    data = await fetch_data(user_id, services=services)
    return data["score"] * multiplier
```

### 2. Publish and Generate FastAPI App

```python
# Publish workflows to Blazing backend
await app.publish()

# Generate FastAPI app
fastapi_app = await create_asgi_app(app)

# Deploy with uvicorn
import uvicorn
uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)
```

### 3. Call the Endpoint

```bash
# Create a job
curl -X POST http://localhost:8080/calculate \
  -H "Content-Type: application/json" \
  -d '{"user_id": 123, "multiplier": 2}'

# Response: {"job_id": "abc123", "status": "pending", ...}

# Check status
curl http://localhost:8080/jobs/abc123

# Response: {"job_id": "abc123", "status": "completed", "result": 20}
```

## Features

### Custom Authentication

Add authentication to endpoints using the `auth_handler` parameter:

```python
async def verify_api_key(credentials: HTTPAuthorizationCredentials) -> bool:
    """Verify API key from Authorization header."""
    if credentials is None:
        return False
    # Check against database, validate JWT, etc.
    return credentials.credentials == "secret-key"

@app.endpoint(path="/secure", auth_handler=verify_api_key)
@app.workflow
async def secure_workflow(data: str, services=None):
    return data.upper()
```

Client must include `Authorization: Bearer secret-key` header.

### WebSocket Support

Enable WebSocket for real-time progress updates:

```python
@app.endpoint(path="/calculate", enable_websocket=True)
@app.workflow
async def calculate(x: int, y: int, services=None):
    return x + y

# WebSocket endpoint created at: ws://host/calculate/ws
```

Client can connect to WebSocket and receive updates:

```javascript
const ws = new WebSocket('ws://localhost:8080/calculate/ws');

// Send workflow parameters
ws.send(JSON.stringify({user_id: 123, multiplier: 2}));

// Receive updates
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(data);
    // {type: "job_created", job_id: "...", status: "pending"}
    // {type: "status_update", job_id: "...", status: "running"}
    // {type: "result", job_id: "...", status: "completed", result: 20}
};
```

### Multiple Endpoints for Same Workflow

You can expose the same workflow at multiple paths:

```python
@app.endpoint(path="/v1/calculate", method="POST")
@app.endpoint(path="/v2/calculate", method="POST")
@app.workflow
async def calculate(x: int, y: int, services=None):
    return x + y
```

### Different HTTP Methods

```python
@app.endpoint(path="/users", method="POST")
@app.workflow
async def create_user(name: str, email: str, services=None):
    return {"id": 123, "name": name, "email": email}

@app.endpoint(path="/users/{user_id}", method="GET")
@app.workflow
async def get_user(user_id: int, services=None):
    return {"id": user_id, "name": "John"}

@app.endpoint(path="/users/{user_id}", method="DELETE")
@app.workflow
async def delete_user(user_id: int, services=None):
    return {"message": "User deleted"}
```

## Built-in Endpoints

The generated FastAPI app includes these endpoints automatically:

### GET /jobs/{job_id}

Get status and result of a job:

```bash
curl http://localhost:8080/jobs/abc123
```

Response:
```json
{
  "job_id": "abc123",
  "status": "completed",
  "result": 20,
  "error": null
}
```

### POST /jobs/{job_id}/cancel

Cancel a running job:

```bash
curl -X POST http://localhost:8080/jobs/abc123/cancel
```

Response:
```json
{
  "message": "Job abc123 cancellation requested"
}
```

### GET /health

Health check endpoint:

```bash
curl http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "service": "blazing-web"
}
```

## API Reference

### `@app.endpoint()`

Decorator to expose a workflow as a public HTTP endpoint.

**Parameters:**
- `path` (str): HTTP path (e.g., "/calculate", "/v1/scores")
- `method` (str, optional): HTTP method. Default: "POST"
- `auth_handler` (Callable, optional): Async authentication function
- `enable_websocket` (bool, optional): Enable WebSocket endpoint. Default: False

**Returns:** Decorator function

**Example:**
```python
@app.endpoint(path="/calculate", method="POST", enable_websocket=True)
@app.workflow
async def calculate(x: int, y: int, services=None):
    return x + y
```

### `create_asgi_app()`

Generate a FastAPI ASGI application from Blazing workflows.

**Parameters:**
- `blazing_app` (Blazing): Blazing instance with @endpoint decorated workflows
- `title` (str, optional): FastAPI app title. Default: "Blazing Workflow API"
- `description` (str, optional): API description
- `version` (str, optional): API version. Default: "1.0.0"
- `enable_cors` (bool, optional): Enable CORS middleware. Default: True

**Returns:** FastAPI application instance

**Example:**
```python
fastapi_app = await create_asgi_app(
    app,
    title="My Workflow API",
    description="Public endpoints for workflows",
    version="1.0.0"
)
```

## Deployment

### With Uvicorn (Development)

```python
import uvicorn

uvicorn.run(
    fastapi_app,
    host="0.0.0.0",
    port=8080,
    log_level="info"
)
```

### With Gunicorn (Production)

```bash
gunicorn main:fastapi_app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8080
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install blazing fastapi uvicorn

CMD ["uvicorn", "main:fastapi_app", "--host", "0.0.0.0", "--port", "8080"]
```

## Security Considerations

1. **Authentication**: Always use `auth_handler` for production endpoints
2. **CORS**: Configure `allow_origins` in production (don't use `["*"]`)
3. **Rate Limiting**: Add rate limiting middleware (e.g., slowapi)
4. **Input Validation**: Pydantic models auto-generated from workflow signatures
5. **TLS**: Use HTTPS in production (reverse proxy like nginx/traefik)

## Example: Complete Application

See `docs/examples/web_endpoint_example.py` for a complete example.

## Testing

See `tests/test_web_endpoints.py` for unit tests.

Run tests:
```bash
uv run pytest tests/test_web_endpoints.py -v
```

## Limitations

1. **Polling-based status updates**: WebSocket support uses polling internally. For true server-sent events, integrate with Redis pub/sub.
2. **No streaming results**: Results are returned as complete JSON objects. For streaming, consider SSE or custom WebSocket protocol.
3. **Job cleanup**: Jobs persist in Redis until cleaned up. Implement TTL or cleanup jobs for production.

## Future Enhancements

- [ ] Server-sent events (SSE) for status updates
- [ ] Redis pub/sub for real-time notifications
- [ ] Streaming results for large datasets
- [ ] Built-in rate limiting
- [ ] Automatic OpenAPI/Swagger documentation
- [ ] Job history and cleanup policies
