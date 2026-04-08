# Blazing Flow Endpoints

**Turn your Blazing Flow workflows into production-ready REST APIs in 3 lines of code.**

Blazing Flow Endpoints wraps your internal workflows with a public-facing FastAPI layer, giving you:
- 🚀 Auto-generated HTTP/WebSocket endpoints
- 🔒 Custom authentication
- 📊 Job status tracking
- ⚡ Async execution model
- 📝 Auto-generated OpenAPI docs

---

## Quick Start

### 1. Install Blazing Flow

```bash
pip install blazing fastapi uvicorn
```

### 2. Create Your First Endpoint

```python
from blazing import Blazing
from blazing.web import create_asgi_app

# Initialize Blazing Flow client
app = Blazing(
    api_url="http://localhost:8000",
    api_token="your-api-token"
)

# Define a workflow and expose it as an endpoint
@app.endpoint(path="/calculate")
@app.workflow
async def calculate(x: int, y: int, services=None):
    """Add two numbers together."""
    return x + y

# Publish workflows to backend
await app.publish()

# Generate FastAPI app
fastapi_app = await create_asgi_app(app)
```

### 3. Run Your API

```bash
uvicorn main:fastapi_app --host 0.0.0.0 --port 8080
```

### 4. Call Your Endpoint

```bash
# Create a job
curl -X POST http://localhost:8080/calculate \
  -H "Content-Type: application/json" \
  -d '{"x": 10, "y": 20}'

# Response:
{
  "job_id": "abc123",
  "status": "pending",
  "created_at": "2025-12-09T10:00:00Z"
}

# Check job status
curl http://localhost:8080/jobs/abc123

# Response:
{
  "job_id": "abc123",
  "status": "completed",
  "result": 30
}
```

**That's it!** Your workflow is now a public REST API.

---

## Core Concepts

### Async Execution Model

Blazing Flow Endpoints uses an **async execution pattern**:

```
POST /calculate     → Returns job_id immediately (non-blocking)
GET /jobs/{job_id}  → Poll for status and results
```

**Why async?** Long-running workflows don't block HTTP connections. Clients get a job ID instantly and check status when ready.

### Workflow → Endpoint Mapping

```python
@app.endpoint(path="/calculate", method="POST")
@app.workflow
async def calculate(x: int, y: int, services=None):
    return x + y
```

| Workflow Parameter | Becomes | HTTP Location |
|-------------------|---------|---------------|
| `x: int` | Request body field | `{"x": 10}` |
| `y: int` | Request body field | `{"y": 20}` |
| `services` | Ignored (internal) | N/A |

**Request model generated automatically** from function signature using Pydantic.

---

## API Reference

### `@app.endpoint()`

Expose a workflow as an HTTP/WebSocket endpoint.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | `str` | ✅ Yes | - | URL path (e.g., `"/calculate"`, `"/v1/users"`) |
| `method` | `str` | No | `"POST"` | HTTP method (`GET`, `POST`, `PUT`, `DELETE`) |
| `auth_handler` | `Callable` | No | `None` | Async function for authentication |
| `enable_websocket` | `bool` | No | `False` | Create WebSocket endpoint at `{path}/ws` |

**Examples:**

```python
# Basic POST endpoint
@app.endpoint(path="/calculate")
@app.workflow
async def calculate(x: int, services=None):
    return x * 2

# GET endpoint
@app.endpoint(path="/users/{user_id}", method="GET")
@app.workflow
async def get_user(user_id: int, services=None):
    return {"id": user_id, "name": "John"}

# With WebSocket
@app.endpoint(path="/stream", enable_websocket=True)
@app.workflow
async def stream_data(value: int, services=None):
    return value * 2
```

### `create_asgi_app()`

Generate a FastAPI application from Blazing Flow workflows.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `blazing_app` | `Blazing` | ✅ Yes | - | Blazing instance with `@endpoint` workflows |
| `title` | `str` | No | `"Blazing Workflow API"` | API title in OpenAPI docs |
| `description` | `str` | No | `""` | API description |
| `version` | `str` | No | `"1.0.0"` | API version |
| `enable_cors` | `bool` | No | `True` | Enable CORS middleware |

**Example:**

```python
fastapi_app = await create_asgi_app(
    app,
    title="My Workflow API",
    description="Production workflows as REST endpoints",
    version="2.0.0",
    enable_cors=True
)
```

---

## Authentication

### Custom Authentication Handler

Protect endpoints with custom authentication logic:

```python
from fastapi.security import HTTPAuthorizationCredentials

async def verify_api_key(credentials: HTTPAuthorizationCredentials) -> bool:
    """Verify API key from Authorization header."""
    if not credentials:
        return False

    # Check against database, validate JWT, etc.
    api_key = credentials.credentials
    return api_key in VALID_API_KEYS  # Your validation logic

@app.endpoint(path="/secure", auth_handler=verify_api_key)
@app.workflow
async def secure_workflow(data: str, services=None):
    return data.upper()
```

**Client usage:**

```bash
curl -X POST http://localhost:8080/secure \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"data": "hello"}'
```

### JWT Authentication Example

```python
import jwt

async def verify_jwt(credentials: HTTPAuthorizationCredentials) -> bool:
    """Verify JWT token."""
    if not credentials:
        return False

    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("user_id") is not None
    except jwt.InvalidTokenError:
        return False

@app.endpoint(path="/admin", auth_handler=verify_jwt)
@app.workflow
async def admin_action(action: str, services=None):
    return f"Action {action} executed"
```

### Multiple Auth Handlers

Different endpoints can have different auth:

```python
@app.endpoint(path="/public")
@app.workflow
async def public_workflow(x: int, services=None):
    return x  # No auth required

@app.endpoint(path="/user", auth_handler=verify_api_key)
@app.workflow
async def user_workflow(x: int, services=None):
    return x * 2  # API key required

@app.endpoint(path="/admin", auth_handler=verify_jwt)
@app.workflow
async def admin_workflow(x: int, services=None):
    return x * 10  # JWT required
```

---

## WebSocket Support

### Enable Real-Time Updates

```python
@app.endpoint(path="/calculate", enable_websocket=True)
@app.workflow
async def calculate(x: int, y: int, services=None):
    return x + y
```

**This creates TWO endpoints:**
- `POST /calculate` - HTTP endpoint (job_id response)
- `WS /calculate/ws` - WebSocket endpoint (real-time updates)

### WebSocket Client Example (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8080/calculate/ws');

// Send workflow parameters
ws.onopen = () => {
    ws.send(JSON.stringify({x: 10, y: 20}));
};

// Receive real-time updates
ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.type === "job_created") {
        console.log("Job created:", message.job_id);
    }

    if (message.type === "status_update") {
        console.log("Status:", message.status);
    }

    if (message.type === "result") {
        console.log("Result:", message.result);
        ws.close();
    }
};
```

### WebSocket Message Types

| Type | When | Fields |
|------|------|--------|
| `job_created` | Job submitted | `job_id`, `status` |
| `status_update` | Status changes | `job_id`, `status` |
| `result` | Job completes | `job_id`, `status`, `result` |
| `error` | Job fails | `job_id`, `status`, `error` |

### WebSocket with Authentication

```python
async def verify_ws_token(credentials: HTTPAuthorizationCredentials) -> bool:
    return credentials and credentials.credentials == "valid-token"

@app.endpoint(
    path="/secure",
    enable_websocket=True,
    auth_handler=verify_ws_token
)
@app.workflow
async def secure_stream(value: int, services=None):
    return value * 2
```

**Client must include auth in initial connection:**

```javascript
const ws = new WebSocket('ws://localhost:8080/secure/ws', {
    headers: {
        'Authorization': 'Bearer valid-token'
    }
});
```

---

## Built-in Endpoints

Every Blazing Flow Endpoints app includes these automatically:

### `GET /jobs/{job_id}`

Get status and result of a job.

```bash
curl http://localhost:8080/jobs/abc123
```

**Response (pending):**
```json
{
  "job_id": "abc123",
  "status": "pending"
}
```

**Response (completed):**
```json
{
  "job_id": "abc123",
  "status": "completed",
  "result": 30
}
```

**Response (failed):**
```json
{
  "job_id": "abc123",
  "status": "failed",
  "error": "Division by zero"
}
```

### `POST /jobs/{job_id}/cancel`

Cancel a running job.

```bash
curl -X POST http://localhost:8080/jobs/abc123/cancel
```

**Response:**
```json
{
  "message": "Job abc123 cancellation requested"
}
```

### `GET /health`

Health check endpoint.

```bash
curl http://localhost:8080/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "blazing-web"
}
```

### `GET /docs`

Interactive Swagger UI documentation (auto-generated).

Visit: `http://localhost:8080/docs`

### `GET /openapi.json`

OpenAPI 3.0 schema (auto-generated).

```bash
curl http://localhost:8080/openapi.json
```

---

## Advanced Features

### Multiple Endpoints per Workflow

Expose the same workflow at multiple paths:

```python
@app.endpoint(path="/v1/calculate")
@app.endpoint(path="/v2/calculate")  # Both work!
@app.workflow
async def calculate(x: int, y: int, services=None):
    return x + y
```

**Use case:** API versioning, backward compatibility.

### Complex Types

Blazing Flow Endpoints auto-generates Pydantic models for complex types:

```python
from typing import List, Dict, Optional

@app.endpoint(path="/process")
@app.workflow
async def process_data(
    items: List[int],
    config: Dict[str, str],
    optional_param: Optional[str] = None,
    services=None
):
    return sum(items)
```

**Request body:**
```json
{
  "items": [1, 2, 3],
  "config": {"mode": "fast"},
  "optional_param": "debug"
}
```

### Path Parameters

```python
@app.endpoint(path="/users/{user_id}/posts/{post_id}", method="GET")
@app.workflow
async def get_post(user_id: int, post_id: int, services=None):
    return {"user": user_id, "post": post_id}
```

**Call:**
```bash
curl http://localhost:8080/users/123/posts/456
```

---

## Deployment

### Docker Compose

```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8080:8080"
    environment:
      - BLAZING_API_URL=http://blazing-backend:8000
      - BLAZING_API_TOKEN=${API_TOKEN}
    command: uvicorn main:fastapi_app --host 0.0.0.0 --port 8080
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: blazing-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: api
        image: your-registry/blazing-api:latest
        ports:
        - containerPort: 8080
        env:
        - name: BLAZING_API_URL
          value: "http://blazing-backend:8000"
        - name: BLAZING_API_TOKEN
          valueFrom:
            secretKeyRef:
              name: blazing-secrets
              key: api-token
```

### Production with Gunicorn

```bash
gunicorn main:fastapi_app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8080 \
  --access-logfile - \
  --error-logfile -
```

### AWS Lambda / Serverless

```python
from mangum import Mangum

# Wrap FastAPI app for serverless
handler = Mangum(fastapi_app)
```

**Deploy with:**
- AWS Lambda + API Gateway
- Google Cloud Functions
- Azure Functions
- Vercel, Netlify, etc.

---

## Configuration

### CORS Configuration

```python
fastapi_app = await create_asgi_app(
    app,
    enable_cors=True  # Default: all origins allowed
)

# Custom CORS configuration
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],  # Specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Custom OpenAPI Metadata

```python
fastapi_app = await create_asgi_app(
    app,
    title="Production Workflow API",
    description="Blazing Flow workflows for data processing",
    version="2.1.0"
)

# Additional metadata
fastapi_app.openapi_tags = [
    {
        "name": "workflows",
        "description": "Workflow execution endpoints"
    }
]
```

---

## Monitoring

### Logging

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.endpoint(path="/calculate")
@app.workflow
async def calculate(x: int, y: int, services=None):
    logger.info(f"Calculating: {x} + {y}")
    result = x + y
    logger.info(f"Result: {result}")
    return result
```

### Metrics (Prometheus)

```python
from prometheus_client import Counter, Histogram

request_count = Counter('workflow_requests_total', 'Total workflow requests')
request_duration = Histogram('workflow_duration_seconds', 'Workflow duration')

@app.endpoint(path="/calculate")
@app.workflow
async def calculate(x: int, y: int, services=None):
    request_count.inc()
    with request_duration.time():
        return x + y
```

---

## Troubleshooting

### Job Stays in "pending" Status

**Symptoms:** Jobs never complete, stuck in "pending"

**Causes:**
1. Coordinator not running
2. No workers available
3. Redis connection issues

**Solutions:**
```bash
# Check coordinator logs
docker logs blazing-coordinator

# Check workers
docker exec blazing-redis redis-cli --scan --pattern "*WorkerThread*"

# Restart coordinator
docker-compose restart coordinator
```

### 401 Unauthorized Errors

**Symptoms:** All requests return 401

**Causes:**
1. Auth handler returning False
2. Missing Authorization header
3. Invalid token format

**Solutions:**
```python
# Debug auth handler
async def debug_auth(credentials):
    print(f"Credentials: {credentials}")
    if credentials:
        print(f"Token: {credentials.credentials}")
    return True  # Temporarily allow all

@app.endpoint(path="/test", auth_handler=debug_auth)
@app.workflow
async def test(x: int, services=None):
    return x
```

### WebSocket Connection Drops

**Symptoms:** WebSocket closes immediately

**Causes:**
1. Authentication failure
2. Invalid JSON sent
3. Timeout during workflow execution

**Solutions:**
- Check WebSocket auth handler
- Verify JSON format: `{"param": value}`
- Increase timeout for long workflows

### Jobs Not Found (404)

**Symptoms:** `GET /jobs/{job_id}` returns 404

**Causes:**
1. Job ID doesn't exist
2. Redis connection lost
3. Job expired (TTL)

**Solutions:**
```bash
# Check if job exists in Redis
docker exec blazing-redis redis-cli GET "blazing:default:unit_definition:Unit:{job_id}"
```

---

## FAQ

**Q: Can I use Blazing Flow Endpoints without Docker?**

A: Yes, but you need Blazing Flow backend running somewhere. The backend handles workflow orchestration. Endpoints just wrap it with HTTP.

**Q: What's the difference between Blazing Flow Endpoints and API Gateway?**

A: Blazing Flow Endpoints transforms **your workflows** into APIs. API Gateway routes **existing APIs**. Different use cases.

**Q: Can I use this in production?**

A: Yes! 77 tests passing, 77% coverage, production-ready.

**Q: How do I handle file uploads?**

A: Use FastAPI's `UploadFile`:

```python
from fastapi import UploadFile

@app.endpoint(path="/upload")
@app.workflow
async def process_file(file: UploadFile, services=None):
    contents = await file.read()
    return {"size": len(contents)}
```

**Q: Can I return DataFrames?**

A: Yes, use Arrow Flight for efficient columnar data transfer. See [Arrow Flight documentation](arrow-flight-setup.md).

**Q: How do I rate limit endpoints?**

A: Use FastAPI middleware:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.endpoint(path="/calculate")
@limiter.limit("10/minute")
@app.workflow
async def calculate(x: int, services=None):
    return x * 2
```

---

## Examples

### Complete Example: Auth + WebSocket + Monitoring

```python
from blazing import Blazing
from blazing.web import create_asgi_app
from fastapi.security import HTTPAuthorizationCredentials
from prometheus_client import Counter
import logging

# Setup
app = Blazing(api_url="http://localhost:8000", api_token="token")
logger = logging.getLogger(__name__)
request_count = Counter('workflow_requests', 'Total requests')

# Authentication
async def verify_token(credentials: HTTPAuthorizationCredentials) -> bool:
    if not credentials:
        return False
    # Your auth logic here
    return credentials.credentials in ["valid-token-1", "valid-token-2"]

# Workflow
@app.endpoint(
    path="/calculate",
    method="POST",
    enable_websocket=True,
    auth_handler=verify_token
)
@app.workflow
async def calculate(x: int, y: int, services=None):
    """Calculate x + y with monitoring."""
    request_count.inc()
    logger.info(f"Calculating: {x} + {y}")
    result = x + y
    logger.info(f"Result: {result}")
    return result

# Deploy
await app.publish()
fastapi_app = await create_asgi_app(
    app,
    title="Production Calculation API",
    version="1.0.0"
)
```

### Run:

```bash
uvicorn main:fastapi_app --host 0.0.0.0 --port 8080 --workers 4
```

### Test:

```bash
# HTTP
curl -X POST http://localhost:8080/calculate \
  -H "Authorization: Bearer valid-token-1" \
  -H "Content-Type: application/json" \
  -d '{"x": 10, "y": 20}'

# WebSocket
wscat -c ws://localhost:8080/calculate/ws \
  -H "Authorization: Bearer valid-token-1"
> {"x": 10, "y": 20}
```

---

## Next Steps

- **[API Reference](api-reference.md)** - Complete decorator and function reference
- **[Authentication Guide](authentication.md)** - JWT, OAuth, custom auth patterns
- **[Deployment Guide](deployment.md)** - Docker, K8s, serverless
- **[Performance Tuning](performance.md)** - Scaling and optimization
- **[Security Best Practices](security.md)** - Production security checklist

---

**Need Help?**
- 📖 [Full Documentation](https://docs.blazing.com)
- 💬 [Community Discord](https://discord.gg/blazing)
- 🐛 [Report Issues](https://github.com/blazing/blazing/issues)
