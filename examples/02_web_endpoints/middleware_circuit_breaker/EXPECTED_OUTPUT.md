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
curl http://localhost:8080/api/database
```

## Successful Response (Circuit CLOSED)

```json
{
  "status": "success",
  "data": {
    "user_count": 15234,
    "active_sessions": 892,
    "database_health": "healthy"
  }
}
```

## Circuit Open Response (503)

After 5 consecutive failures, circuit opens:

```json
{
  "detail": "Service temporarily unavailable",
  "circuit_state": "open"
}
```

## Notes

- Server runs until interrupted (Ctrl+C)
- Three circuit states: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery)
- Failure threshold: 5 consecutive failures open the circuit
- Success threshold: 2 consecutive successes close the circuit
- Timeout: After 30 seconds, circuit moves from OPEN to HALF_OPEN to test recovery
- All responses include `X-Circuit-State` header (closed/open/half_open)
- Circuit open response includes `Retry-After` header
- Example simulates intermittent failures (40% chance of database error)
- In production, prevents thundering herd when downstream service is unhealthy
- Fast fail: When circuit is open, requests rejected immediately without calling backend
- Automatic recovery: Circuit tests health periodically and closes when service recovers
