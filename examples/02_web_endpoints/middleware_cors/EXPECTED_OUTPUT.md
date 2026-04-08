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

## Example Request

```bash
# Without Origin header (works but no CORS headers)
curl http://localhost:8080/api/users

# With allowed Origin (receives CORS headers)
curl http://localhost:8080/api/users \
  -H "Origin: http://localhost:3000"

# Preflight OPTIONS request
curl -X OPTIONS http://localhost:8080/api/users \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Authorization"
```

## Response

```json
{
  "users": [
    {"id": 1, "name": "Alice", "role": "admin"},
    {"id": 2, "name": "Bob", "role": "user"},
    {"id": 3, "name": "Charlie", "role": "user"}
  ],
  "count": 3
}
```

## Notes

- Server runs until interrupted (Ctrl+C)
- CORS headers only added when `Origin` header present in request
- Browser automatically sends `Origin` header for cross-origin requests
- Preflight OPTIONS requests receive 200 with CORS headers
- `allow_credentials=True` allows cookies and authorization headers
- Response includes `Access-Control-Allow-Origin: http://localhost:3000` header
