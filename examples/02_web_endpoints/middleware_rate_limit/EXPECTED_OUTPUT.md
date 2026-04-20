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
# First request (succeeds)
curl http://localhost:8080/api/data

# After 60 requests in a minute (rate limited)
curl http://localhost:8080/api/data
```

## Successful Response

```json
{
  "status": "success",
  "data": {
    "temperature": 72.5,
    "humidity": 45.2,
    "pressure": 1013.25,
    "timestamp": "2026-02-03T12:00:00Z"
  },
  "message": "Weather data retrieved successfully"
}
```

## Rate Limited Response (429)

```json
{
  "detail": "Rate limit exceeded"
}
```

## Notes

- Server runs until interrupted (Ctrl+C)
- Rate limits tracked per client IP address
- Limit: 60 requests per minute (1 request per second average)
- Successful responses include `X-RateLimit-*` headers showing remaining quota
- Rate limited responses return 429 status with `Retry-After` header
- Headers: `X-RateLimit-Limit-Minute`, `X-RateLimit-Remaining-Minute`, `X-RateLimit-Reset-Minute`
- In production, use Redis for distributed rate limiting across multiple instances
