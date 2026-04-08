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
# Connect to a published service
curl -X POST http://localhost:8080/interact/demo \
  -H "Content-Type: application/json" \
  -d '{"service_name": "my-service"}'
```

## Example Response

### Success (service exists)
```json
{
  "service_name": "my-service",
  "connected": true,
  "message": "Successfully connected to service: my-service"
}
```

### Error (service not found)
```json
{
  "service_name": "unknown-service",
  "connected": false,
  "error": "Service unknown-service not found."
}
```

## Notes

- The `app.interact(service_name)` method opens a bidirectional communication channel
- It returns a service instance with connectors initialized
- This is useful for:
  - Reading workflow state mid-execution
  - Sending commands to running workflows
  - Monitoring long-running jobs
  - Interactive debugging and inspection
- The service must be published (via `app.publish()`) before it can be accessed
- Only the latest version of each service is accessible via interact
- Service versioning is handled at the cluster level
- The returned service instance has all connectors available via `services.connectors`
