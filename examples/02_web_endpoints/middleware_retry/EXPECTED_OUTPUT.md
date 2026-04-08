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
curl http://localhost:8080/api/external
```

## Successful Response (after retries if needed)

```json
{
  "status": "success",
  "data": {
    "external_id": "ext-12345",
    "result": "Data successfully retrieved from external service",
    "provider": "example-api"
  }
}
```

## Notes

- Server runs until interrupted (Ctrl+C)
- Automatically retries on 502, 503, 504 status codes
- Maximum 3 retry attempts (4 total requests including original)
- Exponential backoff: 0.1s, 0.2s, 0.4s between attempts
- Jitter adds randomness to prevent retry storms (AWS Full Jitter algorithm)
- Max delay capped at 5 seconds
- Successful response includes `X-Retry-Attempt` header if retries were needed
- Example simulates transient failures (30% chance of 503 error)
- In production, use for proxying requests to unreliable upstream services
- Retry delays: attempt 0: 0-0.1s, attempt 1: 0-0.2s, attempt 2: 0-0.4s
