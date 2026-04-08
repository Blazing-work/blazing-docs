# Expected Output: API Key Authentication

## Running the Example

```bash
python flow.py
```

Server starts on port 8080:

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

## Testing the Endpoints

### 1. Public Endpoint (No Authentication)

```bash
curl -X POST http://localhost:8080/health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### 2. Protected Endpoint Without API Key

```bash
curl -X POST http://localhost:8080/api/data
```

**Response (401 Unauthorized):**
```json
{
  "detail": "Not authenticated"
}
```

### 3. Protected Endpoint With Valid API Key (Header)

```bash
curl -X POST http://localhost:8080/api/data \
  -H "X-API-Key: demo-key-123"
```

**Response (200 OK):**
```json
{
  "message": "Access granted",
  "data": "sensitive information",
  "auth_method": "api_key"
}
```

### 4. Protected Endpoint With Valid API Key (Query Parameter)

```bash
curl -X POST "http://localhost:8080/api/data?api_key=test-key-456"
```

**Response (200 OK):**
```json
{
  "message": "Access granted",
  "data": "sensitive information",
  "auth_method": "api_key"
}
```

### 5. Protected Endpoint With Invalid API Key

```bash
curl -X POST http://localhost:8080/api/data \
  -H "X-API-Key: invalid-key"
```

**Response (401 Unauthorized):**
```json
{
  "detail": "Not authenticated"
}
```

## Notes

- API keys are validated against the static list: `["demo-key-123", "test-key-456"]`
- In production, use hashed keys or database validation instead of static keys
- Both header (`X-API-Key`) and query parameter (`api_key`) authentication are supported
- The `AuthContext` object provides access to authentication metadata
- Public endpoints (like `/health`) require no authentication
