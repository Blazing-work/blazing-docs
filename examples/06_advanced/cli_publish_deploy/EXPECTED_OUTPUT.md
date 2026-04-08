# Expected Output

## Environment Setup

```bash
# Set required environment variables
export BLAZING_API_URL=https://api.blazing.example.com
export BLAZING_API_TOKEN=your-token-here

# Optional: Set orchestrator URL for job routing
export BLAZING_ORCHESTRATOR_URL=https://orchestrator.blazing.example.com
```

## Publishing with CLI

### Auto-discover (searches for app in main.py, app.py, __init__.py)
```bash
blazing publish
```

**Output:**
```
Auto-discovering Blazing app...
✓ Discovered app: flow:app
Publishing workflows to https://api.blazing.example.com...
✓ Published 1 workflow: order_workflow
✓ Published 2 steps: process_order, send_confirmation
Deployment complete!
```

### Explicit app path
```bash
blazing publish --app flow:app
```

**Output:**
```
Loading app from: flow:app
Publishing workflows to https://api.blazing.example.com...
✓ Published 1 workflow: order_workflow
✓ Published 2 steps: process_order, send_confirmation
Deployment complete!
```

### Override credentials inline
```bash
blazing publish --url https://api.example.com --token abc123
```

### Verbose output
```bash
blazing publish --verbose
```

**Output:**
```
Auto-discovering Blazing app...
✓ Discovered app: flow:app
Publishing workflows to https://api.blazing.example.com...
  → Serializing workflow: order_workflow
  → Serializing step: process_order
  → Serializing step: send_confirmation
  → Uploading to remote backend...
  → Validating deployment...
✓ Published 1 workflow: order_workflow
✓ Published 2 steps: process_order, send_confirmation
Deployment complete!
```

## Testing Locally

```bash
python flow.py
```

**Output:**
```json
{
  "order": {
    "order_id": "ORDER-123",
    "amount": 99.99,
    "status": "processed",
    "fee": 2.9997,
    "total": 102.9897
  },
  "confirmation": {
    "order_id": "ORDER-123",
    "email_sent": true,
    "recipient": "customer@example.com"
  },
  "workflow_status": "completed"
}
```

## Notes

- The `blazing publish` command serializes and uploads your workflows to the Blazing backend
- Environment variables take precedence order: CLI flags > environment variables
- **Required environment variables:**
  - `BLAZING_API_URL`: URL of the Blazing control plane API
  - `BLAZING_API_TOKEN`: Authentication token for API access
- **Optional environment variables:**
  - `BLAZING_ORCHESTRATOR_URL`: URL for job routing (optional)
- CLI auto-discovers apps in this order: `main.py:app`, `app.py:app`, `__init__.py:app`, `main.py:application`, `app.py:application`
- Use `--app module.path:attribute` to explicitly specify the app location
- The app instance must be named `app` or `application` for auto-discovery to work
- After publishing, workflows can be invoked remotely without keeping the client running
- Use `--verbose` flag for detailed deployment progress
