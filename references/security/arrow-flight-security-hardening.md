# Arrow Flight Security Hardening Reference

> **Status:** Planning Phase
> **Priority:** CRITICAL for multi-tenant deployments
> **Last Updated:** 2025-12-15

## Executive Summary

Apache Arrow Flight is used in Blazing for high-performance columnar data transfer between executors and the coordinator. Currently, the Arrow Flight server has **no security hardening** - it accepts connections from any client without authentication, authorization, or encryption.

This document outlines the security gaps and provides a phased implementation plan to bring Arrow Flight security in line with the Redis ACL security model already implemented for coordination and data Redis instances.

---

## Current Security State

### Comparison Matrix

| Security Feature | Redis (Coordination) | Redis-Data | Arrow Flight |
|-----------------|---------------------|------------|--------------|
| **ACL Roles** | ✅ admin, executor, coordinator, api | ✅ admin, executor, coordinator, api | ❌ NONE |
| **Authentication** | ✅ Username + password | ✅ Username + password | ❌ NONE |
| **Multi-tenant (app_id)** | ✅ Key prefixes `blazing:{app_id}:*` | ✅ `RedisIndirect\|{app_id}\|{pk}` | ❌ NONE |
| **Command Restrictions** | ✅ Per-role ACL | ✅ Per-role ACL | ❌ NONE |
| **Key Pattern Restrictions** | ✅ `~blazing:*` | ✅ `~blazing:*` | ❌ NONE |
| **Encryption (TLS)** | ⚠️ Optional | ⚠️ Optional | ❌ NONE |
| **Audit Logging** | ⚠️ Redis slowlog | ⚠️ Redis slowlog | ❌ NONE |

### Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARROW FLIGHT SERVER                          │
│                                                                 │
│  Ports:                                                         │
│    - 8815: gRPC endpoint (unencrypted, no auth)                │
│    - 8816: IPC endpoint (reserved)                             │
│                                                                 │
│  Storage: In-memory dict with TTL (ephemeral)                  │
│  Memory Cap: 10 GB default                                     │
│                                                                 │
│  SECURITY: ❌ COMPLETELY OPEN                                  │
│    - No authentication                                          │
│    - No authorization                                           │
│    - No multi-tenant isolation                                  │
│    - No encryption                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Critical Vulnerabilities

### 1. Cross-Tenant Data Access (CRITICAL)

**Current Address Format:**
```
arrow|{grpc_host}:{grpc_port}|{primary_key}|{ipc_host}:{ipc_port}
```

**Example:**
```
arrow|arrow-flight:8815|payroll-2024|arrow-flight:8816
```

**Attack Scenario:**
```python
# Tenant A stores sensitive payroll data
await store_to_arrow(df_payroll, "payroll-2024")

# Tenant B guesses the key and steals data
stolen_data = await fetch_from_arrow("arrow|arrow-flight:8815|payroll-2024|arrow-flight:8816")
# SUCCESS - No validation! ❌
```

**Why Redis-Data is Secure:**
```python
# redis_client.py validates app_id
address_app_id = parts[1]  # Extract from RedisIndirect|{app_id}|{pk}
current_app_id = get_app_id()
if address_app_id != current_app_id:
    raise PermissionError(f"Access denied: address app_id '{address_app_id}' != current '{current_app_id}'")
```

### 2. No Authentication

- Server accepts ANY gRPC connection
- No JWT token validation
- No client certificates
- Any network host can connect

### 3. No Encryption

- gRPC connections are plaintext
- Data visible to network eavesdropping
- MITM attacks possible

### 4. No Rate Limiting

- Clients can exhaust 10 GB memory quota
- No per-tenant quotas
- DoS vulnerability

---

## Implementation Plan

### Phase 1: Multi-Tenant Key Isolation (CRITICAL)

**Priority:** P0 - Must have before any multi-tenant deployment
**Effort:** 4-6 hours
**Risk if Skipped:** Complete data breach between tenants

#### Changes Required

**1. Update Address Format (5 parts instead of 4):**

```
# OLD (4 parts - no app_id)
arrow|{grpc}|{pk}|{ipc}

# NEW (5 parts - includes app_id)
arrow|{grpc}|{app_id}|{pk}|{ipc}
```

**2. Python Client Updates (`src/blazing_executor/data_fetching/arrow_client.py`):**

```python
async def store_to_arrow(data, primary_key: str, app_id: str = None) -> str:
    """Store data to Arrow Flight with app_id namespace."""
    app_id = app_id or get_app_id()

    # Include app_id in the storage key
    namespaced_key = f"{app_id}|{primary_key}"

    # ... store with namespaced_key ...

    # Return 5-part address
    return f"arrow|{grpc_host}:{grpc_port}|{app_id}|{primary_key}|{ipc_host}:{ipc_port}"

async def fetch_from_arrow(address: str) -> Any:
    """Fetch data from Arrow Flight with app_id validation."""
    parts = address.split('|')

    if len(parts) == 5:
        # New format: arrow|grpc|app_id|pk|ipc
        _, grpc_addr, address_app_id, pk, ipc_addr = parts
    elif len(parts) == 4:
        # Legacy format: arrow|grpc|pk|ipc (default app_id)
        _, grpc_addr, pk, ipc_addr = parts
        address_app_id = "default"
    else:
        raise ValueError(f"Invalid Arrow address format: {address}")

    # SECURITY: Validate app_id matches current context
    current_app_id = get_app_id()
    if address_app_id != current_app_id:
        raise PermissionError(
            f"Arrow Flight access denied: address app_id '{address_app_id}' "
            f"does not match current app_id '{current_app_id}'"
        )

    namespaced_key = f"{address_app_id}|{pk}"
    # ... fetch using namespaced_key ...
```

**3. JavaScript Client Updates (`docker/pyodide-executor/arrow_flight_client.mjs`):**

```javascript
function parseArrowAddress(address) {
    const parts = address.split('|');

    if (parts.length === 5) {
        // New format: arrow|grpc|app_id|pk|ipc
        return {
            grpcEndpoint: parts[1],
            appId: parts[2],
            primaryKey: parts[3],
            ipcEndpoint: parts[4]
        };
    } else if (parts.length === 4) {
        // Legacy format: arrow|grpc|pk|ipc
        return {
            grpcEndpoint: parts[1],
            appId: 'default',
            primaryKey: parts[2],
            ipcEndpoint: parts[3]
        };
    }

    throw new Error(`Invalid Arrow address format: ${address}`);
}

async function fetchFromArrow(address, currentAppId) {
    const parsed = parseArrowAddress(address);

    // SECURITY: Validate app_id
    if (parsed.appId !== currentAppId) {
        throw new Error(
            `Arrow Flight access denied: address app_id '${parsed.appId}' ` +
            `does not match current app_id '${currentAppId}'`
        );
    }

    const namespacedKey = `${parsed.appId}|${parsed.primaryKey}`;
    // ... fetch using namespacedKey ...
}
```

**4. Server Updates (`docker/start_arrow_flight.py`):**

```python
class BlazingFlightServer(pa.flight.FlightServerBase):
    def do_put(self, context, descriptor, reader, writer):
        # Key is now namespaced: {app_id}|{pk}
        key = descriptor.path[0].decode('utf-8')
        # Validate format
        if '|' not in key:
            raise pa.flight.FlightUnavailableError(
                "Invalid key format: must be {app_id}|{pk}"
            )
        # ... store data ...

    def do_get(self, context, ticket):
        key = ticket.ticket.decode('utf-8')
        # Key is namespaced: {app_id}|{pk}
        if '|' not in key:
            raise pa.flight.FlightUnavailableError(
                "Invalid key format: must be {app_id}|{pk}"
            )
        # ... return data ...
```

---

### Phase 2: JWT Authentication (HIGH)

**Priority:** P1 - Required for production
**Effort:** 8-12 hours
**Risk if Skipped:** Unauthorized access from any network host

#### Changes Required

**1. Add JWT Middleware to Arrow Flight Server:**

```python
import jwt
from functools import wraps

class AuthenticatedFlightServer(pa.flight.FlightServerBase):
    def __init__(self, jwt_secret: str, **kwargs):
        super().__init__(**kwargs)
        self._jwt_secret = jwt_secret

    def _validate_token(self, context) -> dict:
        """Extract and validate JWT from gRPC metadata."""
        # Arrow Flight passes headers in context.peer_identity()
        # or via custom middleware
        headers = dict(context.peer_identity() or [])
        auth_header = headers.get(b'authorization', b'').decode()

        if not auth_header.startswith('Bearer '):
            raise pa.flight.FlightUnauthenticatedError("Missing Bearer token")

        token = auth_header[7:]
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=['HS256'])
            return payload
        except jwt.InvalidTokenError as e:
            raise pa.flight.FlightUnauthenticatedError(f"Invalid token: {e}")

    def do_put(self, context, descriptor, reader, writer):
        payload = self._validate_token(context)
        app_id = payload.get('app_id', 'default')
        # ... validate key starts with app_id| ...

    def do_get(self, context, ticket):
        payload = self._validate_token(context)
        app_id = payload.get('app_id', 'default')
        # ... validate key starts with app_id| ...
```

**2. Update Clients to Pass JWT:**

```python
# Python client
async def store_to_arrow(data, primary_key: str, token: str) -> str:
    options = pa.flight.FlightCallOptions(
        headers=[(b"authorization", f"Bearer {token}".encode())]
    )
    client = pa.flight.connect(grpc_endpoint)
    # ... use options in calls ...
```

```javascript
// JavaScript client
async function storeToArrow(data, primaryKey, token) {
    const metadata = new grpc.Metadata();
    metadata.add('authorization', `Bearer ${token}`);
    // ... use metadata in calls ...
}
```

**3. Environment Configuration:**

```yaml
# docker-compose.yml
arrow-flight:
  environment:
    - ARROW_FLIGHT_JWT_SECRET=${JWT_SECRET}
    - ARROW_FLIGHT_REQUIRE_AUTH=true
```

---

### Phase 3: TLS Encryption (HIGH)

**Priority:** P1 - Required for production
**Effort:** 3-4 hours
**Risk if Skipped:** Data visible to network eavesdropping

#### Changes Required

**1. Generate Certificates:**

```bash
# docker/generate-arrow-flight-certs.sh
#!/bin/bash
openssl req -x509 -newkey rsa:4096 -keyout arrow-flight-key.pem \
    -out arrow-flight-cert.pem -days 365 -nodes \
    -subj "/CN=arrow-flight"
```

**2. Configure Server TLS:**

```python
# start_arrow_flight.py
server = BlazingFlightServer(
    location=f"grpc+tls://{host}:{port}",
    tls_certificates=[(cert_bytes, key_bytes)]
)
```

**3. Update Client Connections:**

```python
# Python - use grpc+tls://
client = pa.flight.connect(
    f"grpc+tls://{host}:{port}",
    tls_root_certs=root_cert_bytes
)
```

**4. Docker Compose:**

```yaml
arrow-flight:
  environment:
    - ARROW_FLIGHT_TLS_CERT=/certs/arrow-flight-cert.pem
    - ARROW_FLIGHT_TLS_KEY=/certs/arrow-flight-key.pem
  volumes:
    - ./certs:/certs:ro
```

---

### Phase 4: Audit Logging & Rate Limiting (MEDIUM)

**Priority:** P2 - Recommended for compliance
**Effort:** 3-4 hours

#### Audit Logging

```python
import logging
import json
from datetime import datetime

audit_logger = logging.getLogger('arrow_flight_audit')

def log_access(action: str, app_id: str, key: str, size: int, client_ip: str):
    audit_logger.info(json.dumps({
        'timestamp': datetime.utcnow().isoformat(),
        'action': action,  # 'store', 'fetch', 'delete'
        'app_id': app_id,
        'key': key,
        'size_bytes': size,
        'client_ip': client_ip
    }))
```

#### Rate Limiting

```python
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self, max_requests_per_minute: int = 1000, max_bytes_per_minute: int = 1_000_000_000):
        self._requests = defaultdict(list)
        self._bytes = defaultdict(list)
        self._max_requests = max_requests_per_minute
        self._max_bytes = max_bytes_per_minute

    def check(self, app_id: str, size_bytes: int = 0):
        now = time.time()
        minute_ago = now - 60

        # Clean old entries
        self._requests[app_id] = [t for t in self._requests[app_id] if t > minute_ago]
        self._bytes[app_id] = [(t, s) for t, s in self._bytes[app_id] if t > minute_ago]

        # Check limits
        if len(self._requests[app_id]) >= self._max_requests:
            raise pa.flight.FlightUnavailableError(f"Rate limit exceeded for {app_id}")

        total_bytes = sum(s for _, s in self._bytes[app_id])
        if total_bytes + size_bytes > self._max_bytes:
            raise pa.flight.FlightUnavailableError(f"Bandwidth limit exceeded for {app_id}")

        # Record this request
        self._requests[app_id].append(now)
        if size_bytes > 0:
            self._bytes[app_id].append((now, size_bytes))
```

---

## Files to Modify

| Phase | File | Changes |
|-------|------|---------|
| 1 | `docker/start_arrow_flight.py` | Add app_id namespace to keys |
| 1 | `src/blazing_executor/data_fetching/arrow_client.py` | 5-part address format, app_id validation |
| 1 | `docker/pyodide-executor/arrow_flight_client.mjs` | 5-part address parsing, app_id validation |
| 1 | `src/blazing_service/data_access/data_access.py` | Update address generation |
| 2 | `docker/start_arrow_flight.py` | JWT validation middleware |
| 2 | `docker/docker-compose.yml` | JWT_SECRET environment variable |
| 2 | `src/blazing_executor/data_fetching/arrow_client.py` | Pass JWT in requests |
| 2 | `docker/pyodide-executor/arrow_flight_client.mjs` | Pass JWT in requests |
| 3 | `docker/generate-arrow-flight-certs.sh` | New file - certificate generation |
| 3 | `docker/start_arrow_flight.py` | TLS configuration |
| 3 | `docker/docker-compose.yml` | Mount certificates, TLS config |
| 4 | `docker/start_arrow_flight.py` | Audit logging, rate limiter |

---

## Testing Requirements

### Phase 1 Tests

```python
# tests/test_arrow_flight_security.py

@pytest.mark.asyncio
async def test_cross_tenant_access_blocked():
    """Verify tenant A cannot access tenant B's data."""
    # Store as tenant A
    set_app_id("tenant-a")
    address = await store_to_arrow(df, "secret-data")

    # Try to fetch as tenant B
    set_app_id("tenant-b")
    with pytest.raises(PermissionError, match="app_id.*does not match"):
        await fetch_from_arrow(address)

@pytest.mark.asyncio
async def test_legacy_address_format_backwards_compatible():
    """Verify old 4-part addresses still work with default app_id."""
    set_app_id("default")
    legacy_address = "arrow|localhost:8815|old-key|localhost:8816"
    # Should not raise
    await fetch_from_arrow(legacy_address)
```

### Phase 2 Tests

```python
@pytest.mark.asyncio
async def test_unauthenticated_request_rejected():
    """Verify requests without JWT are rejected."""
    with pytest.raises(FlightUnauthenticatedError):
        await store_to_arrow(df, "key", token=None)

@pytest.mark.asyncio
async def test_invalid_token_rejected():
    """Verify requests with invalid JWT are rejected."""
    with pytest.raises(FlightUnauthenticatedError):
        await store_to_arrow(df, "key", token="invalid-token")
```

---

## Rollout Strategy

1. **Development:** Implement Phase 1 (multi-tenant isolation) first
2. **Staging:** Deploy and test all 4 phases
3. **Production:**
   - Phase 1: Deploy immediately (no client changes needed if using default app_id)
   - Phase 2-3: Deploy with client updates
   - Phase 4: Enable monitoring

---

## References

- [Apache Arrow Flight Security](https://arrow.apache.org/docs/format/Flight.html#security)
- [gRPC Authentication](https://grpc.io/docs/guides/auth/)
- [Redis ACL Documentation](https://redis.io/docs/management/security/acl/)
- Internal: `docs/redis-architecture.md` - Redis security implementation
- Internal: `docs/multi-tenant-security.md` - Multi-tenant isolation patterns
