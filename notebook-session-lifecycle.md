# Notebook Session Lifecycle & Automatic Cleanup

## Overview

Pyodide Jupyter notebook sessions now support automatic cleanup when clients disconnect, preventing resource leaks from abandoned sessions.

## Architecture

### Session Lifecycle States

```
Client Connect → Create Session → Execute Cells → Heartbeat Loop → Disconnect → Cleanup
                      ↓                                ↓
                 Register Client ID          Track lastHeartbeat
```

### Cleanup Triggers

Sessions are automatically cleaned up in these scenarios:

1. **Explicit Disconnect**: Client calls `POST /notebook/disconnect`
2. **Heartbeat Timeout**: No heartbeat for `NOTEBOOK_HEARTBEAT_TIMEOUT_MS` (default: 5 minutes)
3. **Session Idle Timeout**: No activity for `NOTEBOOK_SESSION_TIMEOUT_MS` (default: 30 minutes)

## Environment Variables

```bash
# Heartbeat timeout - sessions without heartbeat are cleaned up after this duration
NOTEBOOK_HEARTBEAT_TIMEOUT_MS=300000  # 5 minutes (default)

# Session idle timeout - fallback cleanup for sessions without client tracking
NOTEBOOK_SESSION_TIMEOUT_MS=1800000   # 30 minutes (default)

# Max concurrent sessions per worker
NOTEBOOK_MAX_SESSIONS=10              # default
```

## API Endpoints

### 1. Create Session with Client Tracking

```http
POST /notebook/session
Content-Type: application/json

{
  "client_id": "550e8400-e29b-41d4-a716-446655440000",  // UUID v4
  "app_id": "my-app",
  "unit_pk": "unit-123",
  "token": "auth-token"
}
```

**Response:**
```json
{
  "session_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "created_at": "2026-02-08T14:30:00.000Z",
  "status": "idle"
}
```

### 2. Heartbeat (Keep Alive)

Clients **MUST** call this periodically (recommended: every 30-60 seconds) to prevent session cleanup.

```http
POST /notebook/heartbeat
Content-Type: application/json

{
  "client_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "success": true,
  "session_count": 2  // Number of sessions owned by this client
}
```

### 3. Explicit Disconnect

Immediately destroys all sessions owned by the client.

```http
POST /notebook/disconnect
Content-Type: application/json

{
  "client_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "success": true,
  "sessions_destroyed": 2
}
```

## Client Implementation Examples

### JavaScript/TypeScript Client

```typescript
class NotebookClient {
  private clientId: string;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private sessions: Set<string> = new Set();

  constructor(private baseUrl: string) {
    // Generate unique client ID (UUID v4)
    this.clientId = crypto.randomUUID();
  }

  async connect(): Promise<void> {
    // Start heartbeat loop (every 30 seconds)
    this.heartbeatInterval = setInterval(() => {
      this.sendHeartbeat();
    }, 30000);

    // Send initial heartbeat
    await this.sendHeartbeat();

    // Register cleanup on page unload
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => {
        this.disconnect();
      });
    }
  }

  async createSession(options?: {
    appId?: string;
    unitPk?: string;
    token?: string;
  }): Promise<string> {
    const response = await fetch(`${this.baseUrl}/notebook/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client_id: this.clientId,
        app_id: options?.appId,
        unit_pk: options?.unitPk,
        token: options?.token,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to create session: ${response.statusText}`);
    }

    const data = await response.json();
    this.sessions.add(data.session_id);
    return data.session_id;
  }

  async sendHeartbeat(): Promise<void> {
    try {
      const response = await fetch(`${this.baseUrl}/notebook/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: this.clientId }),
      });

      if (!response.ok) {
        console.error('Heartbeat failed:', response.statusText);
      }
    } catch (error) {
      console.error('Heartbeat error:', error);
    }
  }

  async disconnect(): Promise<void> {
    // Stop heartbeat
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }

    // Send explicit disconnect
    try {
      await fetch(`${this.baseUrl}/notebook/disconnect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: this.clientId }),
        // Use keepalive to ensure request completes even if page is closing
        keepalive: true,
      });
    } catch (error) {
      console.error('Disconnect error:', error);
    }
  }

  async executeCell(sessionId: string, code: string): Promise<any> {
    const response = await fetch(
      `${this.baseUrl}/notebook/session/${sessionId}/execute`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      }
    );

    if (!response.ok) {
      throw new Error(`Cell execution failed: ${response.statusText}`);
    }

    return response.json();
  }
}

// Usage
const client = new NotebookClient('http://localhost:8001');
await client.connect();

const sessionId = await client.createSession();
const cellOutput = await client.executeCell(sessionId, 'print("Hello, World!")');

// When done (optional - heartbeat timeout will cleanup automatically)
await client.disconnect();
```

### Python Client

```python
import uuid
import time
import atexit
import requests
from threading import Thread, Event


class NotebookClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client_id = str(uuid.uuid4())
        self.sessions = set()
        self._heartbeat_thread = None
        self._stop_event = Event()

    def connect(self):
        """Start heartbeat loop and register cleanup."""
        # Start heartbeat thread
        self._stop_event.clear()
        self._heartbeat_thread = Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        # Register cleanup on exit
        atexit.register(self.disconnect)

    def _heartbeat_loop(self):
        """Send heartbeat every 30 seconds."""
        while not self._stop_event.wait(timeout=30):
            try:
                self._send_heartbeat()
            except Exception as e:
                print(f"Heartbeat error: {e}")

    def _send_heartbeat(self):
        """Send a single heartbeat request."""
        response = requests.post(
            f"{self.base_url}/notebook/heartbeat",
            json={"client_id": self.client_id},
            timeout=5,
        )
        response.raise_for_status()

    def create_session(
        self,
        app_id: str = None,
        unit_pk: str = None,
        token: str = None,
    ) -> str:
        """Create a new notebook session."""
        response = requests.post(
            f"{self.base_url}/notebook/session",
            json={
                "client_id": self.client_id,
                "app_id": app_id,
                "unit_pk": unit_pk,
                "token": token,
            },
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        session_id = data["session_id"]
        self.sessions.add(session_id)
        return session_id

    def execute_cell(self, session_id: str, code: str) -> dict:
        """Execute a code cell in a session."""
        response = requests.post(
            f"{self.base_url}/notebook/session/{session_id}/execute",
            json={"code": code},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def disconnect(self):
        """Stop heartbeat and cleanup all sessions."""
        # Stop heartbeat thread
        if self._heartbeat_thread:
            self._stop_event.set()
            self._heartbeat_thread.join(timeout=2)

        # Send explicit disconnect
        try:
            requests.post(
                f"{self.base_url}/notebook/disconnect",
                json={"client_id": self.client_id},
                timeout=5,
            )
        except Exception as e:
            print(f"Disconnect error: {e}")


# Usage
client = NotebookClient("http://localhost:8001")
client.connect()

session_id = client.create_session()
result = client.execute_cell(session_id, "print('Hello, World!')")

# Cleanup happens automatically on exit
```

## Migration Guide

### For Existing Clients (Backward Compatible)

Existing clients that **don't** send `client_id` will continue to work with the old behavior:
- Sessions timeout after `NOTEBOOK_SESSION_TIMEOUT_MS` (30 min default)
- No automatic cleanup on disconnect

### For New Clients (Recommended)

1. Generate a unique `client_id` (UUID v4)
2. Pass `client_id` when creating sessions
3. Send periodic heartbeats (every 30-60s)
4. Call disconnect on page unload / process exit

## Monitoring

Session stats are available at the health endpoint:

```http
GET /health
```

Includes:
- `notebook.active_sessions`: Current session count
- `notebook.executing_sessions`: Sessions currently executing cells
- `notebook.max_sessions`: Maximum allowed sessions
- `notebook.utilization_pct`: Capacity utilization percentage

## Best Practices

1. **Always use `client_id`** - Prevents orphaned sessions
2. **Heartbeat interval: 30-60 seconds** - Balances network overhead vs responsiveness
3. **Register cleanup handlers** - Use `beforeunload`, `atexit`, or signal handlers
4. **Monitor utilization** - Alert if approaching `max_sessions` limit
5. **Tune timeouts** - Adjust `NOTEBOOK_HEARTBEAT_TIMEOUT_MS` based on your use case

## Troubleshooting

### Sessions still not cleaning up

1. **Check client_id is being sent**: Verify requests include `client_id` field
2. **Verify heartbeat is running**: Check logs for heartbeat POST requests
3. **Check timeout settings**: Ensure `NOTEBOOK_HEARTBEAT_TIMEOUT_MS` is configured
4. **Review cleanup logs**: Look for "Cleaned up X session(s)" messages

### Premature session cleanup

1. **Heartbeat too slow**: Reduce heartbeat interval (< `NOTEBOOK_HEARTBEAT_TIMEOUT_MS`)
2. **Network issues**: Check for failed heartbeat requests
3. **Clock skew**: Verify server and client clocks are synchronized
