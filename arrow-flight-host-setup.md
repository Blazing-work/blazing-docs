# Arrow Flight - Running on Host (macOS)

## Why Run on Host?

Arrow Flight runs on the **host machine** instead of in Docker to avoid Docker Desktop crashes on macOS. Adding the Arrow Flight container to docker-compose can cause resource exhaustion issues on macOS.

## Quick Start

### 1. Start Docker Services (without Arrow Flight)

```bash
docker-compose up -d
```

This starts:
- Redis (coordination)
- Redis-data (storage)
- API server
- Foreman
- Executor (configured to connect to host.docker.internal:8815)

### 2. Start Arrow Flight on Host

In a separate terminal:

```bash
./run_arrow_flight.sh
```

You should see:

```
Starting Arrow Flight server on host...
  gRPC endpoint: 0.0.0.0:8815
  IPC endpoint:  0.0.0.0:8816
  Data Redis:    localhost:6380

✓ Arrow Flight server initialized at grpc://0.0.0.0:8815
  TTL: 3600s, Max memory: 10.00 GB
  Authentication: OPTIONAL
```

### 3. Verify Connectivity

```bash
# From host
uv run python -c "
import pyarrow.flight as flight
client = flight.connect('grpc://localhost:8815')
print('✓ Connected from host')
"

# Test from inside Docker executor
docker exec blazing-executor python -c "
import pyarrow.flight as flight
client = flight.connect('grpc://host.docker.internal:8815')
print('✓ Connected from Docker')
"
```

## Configuration

### Environment Variables

Arrow Flight configuration is in `run_arrow_flight.sh`:

```bash
# Redis connection (for data storage)
DATA_REDIS_URL=localhost
DATA_REDIS_PORT=6380  # Redis-data port (mapped from Docker)
DATA_REDIS_USERNAME=api
DATA_REDIS_PASSWORD=${REDIS_DATA_API_PASSWORD}

# Arrow Flight server
ARROW_FLIGHT_HOST=0.0.0.0
ARROW_FLIGHT_GRPC_PORT=8815
ARROW_FLIGHT_IPC_PORT=8816

# Authentication (optional)
JWT_SECRET=${JWT_SECRET:-your-secret-key}
ARROW_FLIGHT_REQUIRE_AUTH=false
```

### Docker Executor Configuration

The executor is configured to connect to Arrow Flight on the host via `host.docker.internal`:

```yaml
# docker-compose.yml (executor service)
environment:
  - ARROW_GRPC_ADDRESS=host.docker.internal:8815
  - ARROW_IPC_ADDRESS=host.docker.internal:8816
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         HOST MACHINE                         │
│                                                               │
│  ┌────────────────────┐                                      │
│  │ Arrow Flight       │ :8815 (gRPC)                        │
│  │ (run_arrow_flight) │ :8816 (IPC)                         │
│  └────────┬───────────┘                                      │
│           │                                                   │
│           │ Reads/writes                                     │
│           │                                                   │
│  ┌────────▼────────────────────────────────────────┐        │
│  │         Docker Containers                        │        │
│  │                                                  │        │
│  │  ┌──────────┐    ┌──────────┐    ┌─────────┐  │        │
│  │  │ Executor │────│ Redis    │────│ Foreman │  │        │
│  │  │          │    │ :6379    │    │         │  │        │
│  │  └──────────┘    └──────────┘    └─────────┘  │        │
│  │       │                                         │        │
│  │       │ host.docker.internal:8815               │        │
│  │       └─────────────────────┐                   │        │
│  │                             │                   │        │
│  │  ┌──────────────┐    ┌──────▼──────┐          │        │
│  │  │ Redis-data   │    │ API         │          │        │
│  │  │ :6380        │    │ :8000       │          │        │
│  │  └──────────────┘    └─────────────┘          │        │
│  └─────────────────────────────────────────────────┘        │
│           │                                                   │
│           │ localhost:6380                                   │
│           └──────────────────────────────────────────────────┤
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Port Already in Use

If port 8815 or 8816 is already in use:

```bash
# Find process using port
lsof -i :8815

# Kill it
kill -9 <PID>
```

### Connection Refused from Executor

1. Check Arrow Flight is running:
```bash
lsof -i :8815
```

2. Test from host first:
```bash
uv run python -c "import pyarrow.flight as flight; client = flight.connect('grpc://localhost:8815'); print('OK')"
```

3. Verify executor can resolve host.docker.internal:
```bash
docker exec blazing-executor getent hosts host.docker.internal
```

### Redis Connection Issues

Arrow Flight needs to connect to Redis-data on `localhost:6380`:

```bash
# Check Redis-data is accessible
redis-cli -p 6380 ping
# Should return: PONG
```

If ACL is enabled:

```bash
# Load passwords
source .env.redis-passwords

# Test with credentials
redis-cli -p 6380 --user api --pass "$REDIS_DATA_API_PASSWORD" ping
```

## Production Deployment

For production (Linux servers), Arrow Flight can run in Docker without issues:

1. Uncomment the `arrow-flight` service in docker-compose.yml
2. Remove the host-based setup
3. Change executor environment to:
   ```yaml
   - ARROW_GRPC_ADDRESS=arrow-flight:8815
   - ARROW_IPC_ADDRESS=arrow-flight:8816
   ```

The host-based setup is only needed for macOS development due to Docker Desktop resource constraints.
