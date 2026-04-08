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
# First request (cache miss)
curl http://localhost:8080/api/stats

# Second request within 5 minutes (cache hit)
curl http://localhost:8080/api/stats
```

## Response

```json
{
  "statistics": {
    "total_users": 15234,
    "active_users": 8912,
    "total_requests": 1250000,
    "avg_response_time_ms": 142.5,
    "cache_hit_rate": 0.87
  },
  "computed_at": "2026-02-03T12:00:00Z",
  "message": "Statistics computed from last 24 hours"
}
```

## Notes

- Server runs until interrupted (Ctrl+C)
- First request: `X-Cache: MISS` header (computed fresh)
- Subsequent requests: `X-Cache: HIT` header (served from cache)
- Cache TTL: 300 seconds (5 minutes)
- Cache key includes: HTTP method, path, query params, Accept headers
- Only GET requests cached by default
- Only 200, 301, 302 status codes cached by default
- Response includes `Age` header showing cache entry age in seconds
- In production, use Redis for distributed caching across multiple instances
- Responses with `Authorization` or `Cookie` headers are not cached (private data)
