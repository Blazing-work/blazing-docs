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

## Example Request (Completes Within Timeout)

```bash
curl -X POST http://localhost:8080/api/compute \
  -H "Content-Type: application/json" \
  -d '{"duration": 2.0}'
```

## Successful Response

```json
{
  "status": "success",
  "result": {
    "computation": "completed",
    "duration_seconds": 2.0,
    "value": 42
  }
}
```

## Example Request (Exceeds Timeout)

```bash
curl -X POST http://localhost:8080/api/compute \
  -H "Content-Type: application/json" \
  -d '{"duration": 10.0}'
```

## Timeout Response (504)

```json
{
  "detail": "Computation exceeded time limit",
  "timeout": 5.0
}
```

## Notes

- Server runs until interrupted (Ctrl+C)
- Timeout limit: 5 seconds
- Requests exceeding timeout return 504 Gateway Timeout
- Timeout response includes configured message and timeout value
- Example accepts `duration` parameter to simulate computation time
- In production, use for endpoints with potentially long-running operations
- Prevents resource exhaustion from hanging requests
- Default status code: 504 (Gateway Timeout), configurable via `status_code` parameter
- Timeout enforced via `asyncio.wait_for()` for async operations
