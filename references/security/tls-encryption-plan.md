# TLS Encryption Plan - All Services

> **Status:** Planning Phase
> **Priority:** HIGH for production deployments
> **Last Updated:** 2025-12-15

## Executive Summary

This document outlines the TLS encryption implementation plan for all Blazing services. Currently, all inter-service communication is unencrypted, which exposes sensitive data to network eavesdropping and man-in-the-middle attacks.

---

## Current State: Encryption Coverage

| Service | Port | Protocol | TLS Status | Risk Level |
|---------|------|----------|------------|------------|
| **Redis (Coordination)** | 6379 | RESP | ❌ None | 🔴 HIGH |
| **Redis-Data** | 6379 | RESP | ❌ None | 🔴 HIGH |
| **Arrow Flight** | 8815 | gRPC | ❌ None | 🔴 HIGH |
| **API Server** | 8000 | HTTP | ❌ None | 🟡 MEDIUM* |
| **Executor** | 8003 | HTTP | ❌ None | 🟡 MEDIUM* |
| **Pyodide Executor** | 8004 | HTTP | ❌ None | 🟡 MEDIUM* |

*HTTP services are lower risk because they're typically behind a TLS-terminating load balancer in production

---

## Data at Risk (Unencrypted)

### Redis (Coordination)
- Station/Route definitions (serialized code)
- Operation metadata and status
- Worker state and assignments
- JWT tokens in transit
- App_id and tenant information

### Redis-Data
- **User data payloads** (args/kwargs for operations)
- Serialized DataFrames and arrays
- Business-critical computation results
- Potentially PII/PHI depending on workload

### Arrow Flight
- **Large columnar datasets** (DataFrames)
- High-value analytical data
- Bulk data transfers (most sensitive due to volume)

---

## Implementation Plan

### Phase 1: Certificate Infrastructure

**Effort:** 2-3 hours
**Dependencies:** None

#### 1.1 Create Certificate Generation Script

```bash
#!/bin/bash
# docker/generate-tls-certs.sh
# Generates self-signed certificates for development/testing
# For production, use certificates from a proper CA

set -e

CERT_DIR="${1:-./certs}"
DAYS_VALID="${2:-365}"
CA_CN="${3:-Blazing CA}"

mkdir -p "$CERT_DIR"

echo "=== Generating Blazing TLS Certificates ==="
echo "Output directory: $CERT_DIR"
echo "Validity: $DAYS_VALID days"

# 1. Generate CA (Certificate Authority)
echo ""
echo "--- Generating Certificate Authority ---"
openssl genrsa -out "$CERT_DIR/ca-key.pem" 4096
openssl req -new -x509 -days "$DAYS_VALID" \
    -key "$CERT_DIR/ca-key.pem" \
    -out "$CERT_DIR/ca-cert.pem" \
    -subj "/CN=$CA_CN/O=Blazing/C=US"

# 2. Generate Redis (Coordination) certificate
echo ""
echo "--- Generating Redis Coordination Certificate ---"
openssl genrsa -out "$CERT_DIR/redis-key.pem" 2048
openssl req -new \
    -key "$CERT_DIR/redis-key.pem" \
    -out "$CERT_DIR/redis.csr" \
    -subj "/CN=redis/O=Blazing/C=US"
openssl x509 -req -days "$DAYS_VALID" \
    -in "$CERT_DIR/redis.csr" \
    -CA "$CERT_DIR/ca-cert.pem" \
    -CAkey "$CERT_DIR/ca-key.pem" \
    -CAcreateserial \
    -out "$CERT_DIR/redis-cert.pem" \
    -extfile <(printf "subjectAltName=DNS:redis,DNS:localhost,DNS:blazing-redis,IP:127.0.0.1")

# 3. Generate Redis-Data certificate
echo ""
echo "--- Generating Redis Data Certificate ---"
openssl genrsa -out "$CERT_DIR/redis-data-key.pem" 2048
openssl req -new \
    -key "$CERT_DIR/redis-data-key.pem" \
    -out "$CERT_DIR/redis-data.csr" \
    -subj "/CN=redis-data/O=Blazing/C=US"
openssl x509 -req -days "$DAYS_VALID" \
    -in "$CERT_DIR/redis-data.csr" \
    -CA "$CERT_DIR/ca-cert.pem" \
    -CAkey "$CERT_DIR/ca-key.pem" \
    -CAcreateserial \
    -out "$CERT_DIR/redis-data-cert.pem" \
    -extfile <(printf "subjectAltName=DNS:redis-data,DNS:localhost,DNS:blazing-redis-data,IP:127.0.0.1")

# 4. Generate Arrow Flight certificate
echo ""
echo "--- Generating Arrow Flight Certificate ---"
openssl genrsa -out "$CERT_DIR/arrow-flight-key.pem" 2048
openssl req -new \
    -key "$CERT_DIR/arrow-flight-key.pem" \
    -out "$CERT_DIR/arrow-flight.csr" \
    -subj "/CN=arrow-flight/O=Blazing/C=US"
openssl x509 -req -days "$DAYS_VALID" \
    -in "$CERT_DIR/arrow-flight.csr" \
    -CA "$CERT_DIR/ca-cert.pem" \
    -CAkey "$CERT_DIR/ca-key.pem" \
    -CAcreateserial \
    -out "$CERT_DIR/arrow-flight-cert.pem" \
    -extfile <(printf "subjectAltName=DNS:arrow-flight,DNS:localhost,DNS:blazing-arrow-flight,IP:127.0.0.1")

# 5. Generate client certificate (for mTLS)
echo ""
echo "--- Generating Client Certificate ---"
openssl genrsa -out "$CERT_DIR/client-key.pem" 2048
openssl req -new \
    -key "$CERT_DIR/client-key.pem" \
    -out "$CERT_DIR/client.csr" \
    -subj "/CN=blazing-client/O=Blazing/C=US"
openssl x509 -req -days "$DAYS_VALID" \
    -in "$CERT_DIR/client.csr" \
    -CA "$CERT_DIR/ca-cert.pem" \
    -CAkey "$CERT_DIR/ca-key.pem" \
    -CAcreateserial \
    -out "$CERT_DIR/client-cert.pem"

# Cleanup CSR files
rm -f "$CERT_DIR"/*.csr

# Set permissions
chmod 600 "$CERT_DIR"/*-key.pem
chmod 644 "$CERT_DIR"/*-cert.pem "$CERT_DIR"/ca-cert.pem

echo ""
echo "=== Certificate Generation Complete ==="
echo ""
echo "Files created:"
ls -la "$CERT_DIR"
echo ""
echo "To use in docker-compose, mount $CERT_DIR to /certs in containers"
```

#### 1.2 Add Certificates to .gitignore

```gitignore
# TLS Certificates (never commit private keys!)
certs/
*.pem
*.csr
*.key
!docker/generate-tls-certs.sh
```

---

### Phase 2: Redis TLS (Coordination + Data)

**Effort:** 4-6 hours
**Dependencies:** Phase 1

#### 2.1 Update Redis Entrypoint Scripts

**docker/redis-entrypoint.sh (Coordination Redis):**

```bash
#!/bin/sh
# Redis (Main/Coordination) Entrypoint Script with TLS

set -e

# ... existing ACL configuration ...

# TLS Configuration
TLS_ENABLED="${REDIS_TLS_ENABLED:-false}"
TLS_CERT_FILE="${REDIS_TLS_CERT_FILE:-/certs/redis-cert.pem}"
TLS_KEY_FILE="${REDIS_TLS_KEY_FILE:-/certs/redis-key.pem}"
TLS_CA_CERT_FILE="${REDIS_TLS_CA_CERT_FILE:-/certs/ca-cert.pem}"
TLS_PORT="${REDIS_TLS_PORT:-6380}"

if [ "$TLS_ENABLED" = "true" ]; then
    echo "✓ TLS enabled on port $TLS_PORT"

    # Verify certificate files exist
    if [ ! -f "$TLS_CERT_FILE" ] || [ ! -f "$TLS_KEY_FILE" ] || [ ! -f "$TLS_CA_CERT_FILE" ]; then
        echo "ERROR: TLS certificate files not found"
        echo "  Expected: $TLS_CERT_FILE, $TLS_KEY_FILE, $TLS_CA_CERT_FILE"
        exit 1
    fi

    exec redis-stack-server \
        --aclfile "$TEMP_ACL_FILE" \
        --port 0 \
        --tls-port "$TLS_PORT" \
        --tls-cert-file "$TLS_CERT_FILE" \
        --tls-key-file "$TLS_KEY_FILE" \
        --tls-ca-cert-file "$TLS_CA_CERT_FILE" \
        --tls-auth-clients optional \
        --save 60 1 \
        --loglevel warning \
        --maxmemory 4gb \
        --maxmemory-policy allkeys-lru \
        --appendonly yes \
        --dir /data
else
    echo "⚠ TLS disabled (set REDIS_TLS_ENABLED=true to enable)"

    exec redis-stack-server \
        --aclfile "$TEMP_ACL_FILE" \
        --save 60 1 \
        --loglevel warning \
        --maxmemory 4gb \
        --maxmemory-policy allkeys-lru \
        --appendonly yes \
        --dir /data
fi
```

**docker/redis-data-entrypoint.sh (Data Redis):**

```bash
#!/bin/sh
# Redis Data Entrypoint Script with TLS

set -e

# ... existing ACL configuration ...

# TLS Configuration
TLS_ENABLED="${REDIS_TLS_ENABLED:-false}"
TLS_CERT_FILE="${REDIS_TLS_CERT_FILE:-/certs/redis-data-cert.pem}"
TLS_KEY_FILE="${REDIS_TLS_KEY_FILE:-/certs/redis-data-key.pem}"
TLS_CA_CERT_FILE="${REDIS_TLS_CA_CERT_FILE:-/certs/ca-cert.pem}"
TLS_PORT="${REDIS_TLS_PORT:-6380}"

if [ "$TLS_ENABLED" = "true" ]; then
    echo "✓ TLS enabled on port $TLS_PORT"

    exec redis-server \
        --aclfile "$TEMP_ACL_FILE" \
        --port 0 \
        --tls-port "$TLS_PORT" \
        --tls-cert-file "$TLS_CERT_FILE" \
        --tls-key-file "$TLS_KEY_FILE" \
        --tls-ca-cert-file "$TLS_CA_CERT_FILE" \
        --tls-auth-clients optional \
        --save 60 1 \
        --loglevel warning \
        --maxmemory 2gb \
        --maxmemory-policy allkeys-lru \
        --appendonly no \
        --dir /data
else
    echo "⚠ TLS disabled (set REDIS_TLS_ENABLED=true to enable)"

    exec redis-server \
        --aclfile "$TEMP_ACL_FILE" \
        --save 60 1 \
        --loglevel warning \
        --maxmemory 2gb \
        --maxmemory-policy allkeys-lru \
        --appendonly no \
        --dir /data
fi
```

#### 2.2 Update Docker Compose

```yaml
# docker-compose.yml additions

services:
  redis:
    # ... existing config ...
    environment:
      # ... existing env vars ...
      - REDIS_TLS_ENABLED=${REDIS_TLS_ENABLED:-false}
      - REDIS_TLS_PORT=6380
    volumes:
      - ./certs:/certs:ro  # Mount certificates read-only
    ports:
      - "6379:6379"   # Non-TLS (disable in production)
      - "6380:6380"   # TLS

  redis-data:
    # ... existing config ...
    environment:
      # ... existing env vars ...
      - REDIS_TLS_ENABLED=${REDIS_TLS_ENABLED:-false}
      - REDIS_TLS_PORT=6380
    volumes:
      - ./certs:/certs:ro
    ports:
      - "6381:6379"   # Non-TLS (disable in production)
      - "6382:6380"   # TLS
```

#### 2.3 Update Python Redis Clients

**src/blazing_service/util/util.py:**

```python
def get_redis_connection(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    username: str = None,
    password: str = None,
    ssl: bool = False,
    ssl_ca_certs: str = None,
    ssl_certfile: str = None,
    ssl_keyfile: str = None,
) -> redis.Redis:
    """Create Redis connection with optional TLS."""
    kwargs = {
        'host': host,
        'port': port,
        'db': db,
        'decode_responses': True,
    }

    if username and password:
        kwargs['username'] = username
        kwargs['password'] = password

    if ssl:
        kwargs['ssl'] = True
        kwargs['ssl_cert_reqs'] = 'required'
        if ssl_ca_certs:
            kwargs['ssl_ca_certs'] = ssl_ca_certs
        if ssl_certfile:
            kwargs['ssl_certfile'] = ssl_certfile
        if ssl_keyfile:
            kwargs['ssl_keyfile'] = ssl_keyfile

    return redis.Redis(**kwargs)
```

**Environment variables for TLS:**

```bash
# .env.tls (create for TLS-enabled deployments)
REDIS_TLS_ENABLED=true
REDIS_TLS_CA_CERT=/certs/ca-cert.pem
REDIS_TLS_CERT=/certs/client-cert.pem
REDIS_TLS_KEY=/certs/client-key.pem
```

---

### Phase 3: Arrow Flight TLS

**Effort:** 3-4 hours
**Dependencies:** Phase 1

#### 3.1 Update Arrow Flight Server

**docker/start_arrow_flight.py:**

```python
import pyarrow.flight as pa_flight
import os

def create_server():
    host = os.getenv('ARROW_FLIGHT_HOST', '0.0.0.0')
    port = int(os.getenv('ARROW_FLIGHT_GRPC_PORT', 8815))
    tls_enabled = os.getenv('ARROW_FLIGHT_TLS_ENABLED', 'false').lower() == 'true'

    if tls_enabled:
        cert_file = os.getenv('ARROW_FLIGHT_TLS_CERT', '/certs/arrow-flight-cert.pem')
        key_file = os.getenv('ARROW_FLIGHT_TLS_KEY', '/certs/arrow-flight-key.pem')

        with open(cert_file, 'rb') as f:
            cert_chain = f.read()
        with open(key_file, 'rb') as f:
            private_key = f.read()

        location = f"grpc+tls://{host}:{port}"
        server = BlazingFlightServer(
            location=location,
            tls_certificates=[(cert_chain, private_key)]
        )
        print(f"✓ Arrow Flight server starting with TLS on {location}")
    else:
        location = f"grpc://{host}:{port}"
        server = BlazingFlightServer(location=location)
        print(f"⚠ Arrow Flight server starting WITHOUT TLS on {location}")

    return server
```

#### 3.2 Update Arrow Flight Clients

**Python Client (`src/blazing_executor/data_fetching/arrow_client.py`):**

```python
import pyarrow.flight as pa_flight
import os

def connect_to_arrow_flight(endpoint: str):
    """Connect to Arrow Flight with optional TLS."""
    tls_enabled = os.getenv('ARROW_FLIGHT_TLS_ENABLED', 'false').lower() == 'true'

    if tls_enabled:
        ca_cert_file = os.getenv('ARROW_FLIGHT_TLS_CA_CERT', '/certs/ca-cert.pem')
        with open(ca_cert_file, 'rb') as f:
            root_certs = f.read()

        # Convert grpc:// to grpc+tls://
        if endpoint.startswith('grpc://'):
            endpoint = 'grpc+tls://' + endpoint[7:]

        return pa_flight.connect(endpoint, tls_root_certs=root_certs)
    else:
        return pa_flight.connect(endpoint)
```

**JavaScript Client (`docker/pyodide-executor/arrow_flight_client.mjs`):**

```javascript
import * as grpc from '@grpc/grpc-js';
import * as fs from 'fs';

function createGrpcCredentials() {
    const tlsEnabled = process.env.ARROW_FLIGHT_TLS_ENABLED === 'true';

    if (tlsEnabled) {
        const caCert = fs.readFileSync(process.env.ARROW_FLIGHT_TLS_CA_CERT || '/certs/ca-cert.pem');
        return grpc.credentials.createSsl(caCert);
    } else {
        return grpc.credentials.createInsecure();
    }
}
```

---

### Phase 4: HTTP Services TLS (Optional)

**Effort:** 2-3 hours
**Dependencies:** Phase 1
**Note:** Often handled by load balancer in production

#### 4.1 API Server with TLS

```python
# Option A: Using uvicorn directly with TLS
# docker/api-entrypoint.sh
if [ "$API_TLS_ENABLED" = "true" ]; then
    exec uvicorn blazing_service.server:app \
        --host 0.0.0.0 \
        --port 8000 \
        --ssl-keyfile /certs/api-key.pem \
        --ssl-certfile /certs/api-cert.pem \
        --workers 4
else
    exec uvicorn blazing_service.server:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 4
fi
```

---

## Docker Compose - Full TLS Configuration

```yaml
# docker-compose.tls.yml (overlay for TLS)
version: '3.8'

services:
  redis:
    environment:
      - REDIS_TLS_ENABLED=true
      - REDIS_TLS_PORT=6380
    volumes:
      - ./certs:/certs:ro
    ports:
      - "6380:6380"  # TLS only

  redis-data:
    environment:
      - REDIS_TLS_ENABLED=true
      - REDIS_TLS_PORT=6380
    volumes:
      - ./certs:/certs:ro
    ports:
      - "6382:6380"  # TLS only

  arrow-flight:
    environment:
      - ARROW_FLIGHT_TLS_ENABLED=true
      - ARROW_FLIGHT_TLS_CERT=/certs/arrow-flight-cert.pem
      - ARROW_FLIGHT_TLS_KEY=/certs/arrow-flight-key.pem
    volumes:
      - ./certs:/certs:ro

  api:
    environment:
      - REDIS_TLS_ENABLED=true
      - REDIS_TLS_CA_CERT=/certs/ca-cert.pem
      - ARROW_FLIGHT_TLS_ENABLED=true
      - ARROW_FLIGHT_TLS_CA_CERT=/certs/ca-cert.pem
    volumes:
      - ./certs:/certs:ro

  coordinator:
    environment:
      - REDIS_TLS_ENABLED=true
      - REDIS_TLS_CA_CERT=/certs/ca-cert.pem
    volumes:
      - ./certs:/certs:ro

  executor:
    environment:
      - REDIS_TLS_ENABLED=true
      - REDIS_TLS_CA_CERT=/certs/ca-cert.pem
      - ARROW_FLIGHT_TLS_ENABLED=true
      - ARROW_FLIGHT_TLS_CA_CERT=/certs/ca-cert.pem
    volumes:
      - ./certs:/certs:ro

  pyodide-executor:
    environment:
      - REDIS_TLS_ENABLED=true
      - ARROW_FLIGHT_TLS_ENABLED=true
    volumes:
      - ./certs:/certs:ro
```

**Usage:**
```bash
# Generate certificates first
./docker/generate-tls-certs.sh ./certs

# Start with TLS overlay
docker-compose -f docker-compose.yml -f docker-compose.tls.yml up -d
```

---

## Environment Variables Summary

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `REDIS_TLS_ENABLED` | All | `false` | Enable TLS for Redis connections |
| `REDIS_TLS_PORT` | Redis | `6380` | TLS-enabled port |
| `REDIS_TLS_CA_CERT` | Clients | `/certs/ca-cert.pem` | CA certificate path |
| `REDIS_TLS_CERT` | Redis | `/certs/redis-cert.pem` | Server certificate |
| `REDIS_TLS_KEY` | Redis | `/certs/redis-key.pem` | Server private key |
| `ARROW_FLIGHT_TLS_ENABLED` | Arrow Flight | `false` | Enable TLS for Arrow Flight |
| `ARROW_FLIGHT_TLS_CERT` | Server | `/certs/arrow-flight-cert.pem` | Server certificate |
| `ARROW_FLIGHT_TLS_KEY` | Server | `/certs/arrow-flight-key.pem` | Server private key |
| `ARROW_FLIGHT_TLS_CA_CERT` | Clients | `/certs/ca-cert.pem` | CA certificate |

---

## Testing TLS Connections

### Redis TLS Test

```bash
# Test Redis TLS connection
redis-cli -h localhost -p 6380 \
    --tls \
    --cacert ./certs/ca-cert.pem \
    --user admin --pass "$REDIS_ADMIN_PASSWORD" \
    PING
```

### Arrow Flight TLS Test

```python
import pyarrow.flight as pa_flight

# Test Arrow Flight TLS connection
with open('./certs/ca-cert.pem', 'rb') as f:
    root_certs = f.read()

client = pa_flight.connect('grpc+tls://localhost:8815', tls_root_certs=root_certs)
print(client.list_flights())
```

---

## Rollout Strategy

### Development Environment
1. Generate self-signed certificates
2. Test with `REDIS_TLS_ENABLED=false` (default)
3. Enable TLS for integration testing

### Staging Environment
1. Use CA-signed certificates (Let's Encrypt or internal CA)
2. Enable TLS for all services
3. Run full E2E test suite

### Production Environment
1. Use properly signed certificates from trusted CA
2. Enable TLS for ALL services (no exceptions)
3. Consider mTLS for service-to-service authentication
4. Rotate certificates before expiration (automate with cert-manager)

---

## Security Considerations

### Certificate Rotation
- Certificates should be rotated every 90-365 days
- Implement graceful reload without downtime
- Use cert-manager in Kubernetes environments

### Private Key Protection
- Never commit private keys to version control
- Use Docker secrets or Kubernetes secrets
- Restrict file permissions (600 for keys)

### Cipher Suites
- Use TLS 1.2+ only
- Disable weak ciphers (RC4, DES, etc.)
- Prefer ECDHE for forward secrecy

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `docker/generate-tls-certs.sh` | CREATE | Certificate generation script |
| `docker/redis-entrypoint.sh` | MODIFY | Add TLS configuration |
| `docker/redis-data-entrypoint.sh` | MODIFY | Add TLS configuration |
| `docker/start_arrow_flight.py` | MODIFY | Add TLS support |
| `docker-compose.tls.yml` | CREATE | TLS overlay compose file |
| `src/blazing_service/util/util.py` | MODIFY | TLS Redis connection |
| `src/blazing_executor/data_fetching/arrow_client.py` | MODIFY | TLS Arrow client |
| `docker/pyodide-executor/datasource_manager.mjs` | MODIFY | TLS Redis client |
| `docker/pyodide-executor/arrow_flight_client.mjs` | MODIFY | TLS gRPC client |
| `.gitignore` | MODIFY | Exclude certificates |

---

## References

- [Redis TLS Documentation](https://redis.io/docs/management/security/encryption/)
- [Apache Arrow Flight Security](https://arrow.apache.org/docs/format/Flight.html#security)
- [gRPC TLS Configuration](https://grpc.io/docs/guides/auth/)
- [OpenSSL Certificate Commands](https://www.openssl.org/docs/man1.1.1/man1/)
