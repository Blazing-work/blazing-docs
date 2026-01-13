# Blazing Security Features

This document describes the security features implemented for Blazing, providing multi-tenant isolation, authentication, encryption, and monitoring.

## Overview

| Phase | Feature | Status | Tests | Implementation |
|-------|---------|--------|-------|----------------|
| 1 | Multi-tenant key isolation | ✅ Complete | 19 tests | Arrow Flight |
| 2 | JWT authentication | ✅ Complete | 7 tests | Arrow Flight, API |
| 3 | TLS encryption | ✅ Infrastructure Ready | 16 tests | Arrow Flight, Redis |
| 4 | Audit logging & rate limiting | ✅ Complete | 28 tests | Arrow Flight, API |

**Total: 70+ security tests**

**Security Infrastructure:**
- ✅ TLS certificate generation script
- ✅ Docker compose security overlay (`docker-compose.security.yml`)
- ✅ JWT authentication in Arrow Flight server
- ✅ Audit logging with 14 event types
- ✅ Token bucket rate limiting per tenant
- ✅ Multi-tenant isolation with app_id namespacing

---

## Phase 1: Multi-Tenant Key Isolation

### Purpose
Prevent cross-tenant data access in Arrow Flight by including `app_id` in all storage keys.

### Address Format

**New format (5-part):**
```
arrow|{grpc_endpoint}|{app_id}|{primary_key}|{ipc_endpoint}
```

**Legacy format (4-part, defaults to 'default' app_id):**
```
arrow|{grpc_endpoint}|{primary_key}|{ipc_endpoint}
```

### Storage Key Format
```
{app_id}:{primary_key}
```

### Files Modified
- `docker/start_arrow_flight.py` - Server-side key validation
- `src/blazing_executor/data_fetching/arrow_client.py` - Client-side app_id validation
- `docker/pyodide-executor/arrow_flight_client.mjs` - JavaScript client support

### Usage
```python
from blazing_executor.data_fetching.arrow_client import store_to_arrow, fetch_from_arrow

# Store data (app_id from context or explicit)
address = await store_to_arrow(data, "operation-123", app_id="tenant-a")
# Returns: "arrow|localhost:8815|tenant-a|operation-123|localhost:8816"

# Fetch data (validates app_id matches current context)
data = await fetch_from_arrow(address)  # Raises PermissionError if app_id mismatch
```

---

## Phase 2: JWT Authentication

### Purpose
Authenticate Arrow Flight requests using JWT tokens with app_id claim validation.

### Environment Variables
```bash
# Server
BLAZING_JWT_SECRET=your-secret-key
ARROW_FLIGHT_REQUIRE_AUTH=true  # Require authentication

# Client (passed via code)
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Token Claims
JWT tokens must include:
- `app_id` - Must match the storage key's app_id
- `exp` - Expiration timestamp

### Files Modified
- `docker/start_arrow_flight.py` - `_authenticate()` method
- `src/blazing_executor/data_fetching/arrow_client.py` - `token` parameter

### Usage
```python
# Client-side authentication
data = await fetch_from_arrow(address, token="eyJhbG...")
await store_to_arrow(data, "key", token="eyJhbG...")
```

---

## Phase 3: TLS Encryption

### Purpose
Encrypt all network communication using TLS for Redis and Arrow Flight.

### Certificate Generation
```bash
# Generate self-signed certificates for development
./docker/generate-tls-certs.sh

# Files created:
# docker/certs/ca.crt        - Certificate Authority
# docker/certs/redis.crt     - Redis Coordination certificate
# docker/certs/redis-data.crt - Redis Data certificate
# docker/certs/arrow-flight.crt - Arrow Flight certificate
# docker/certs/client.crt    - Client certificate (for mTLS)
```

### Environment Variables

**Redis TLS:**
```bash
REDIS_TLS_ENABLED=true
REDIS_TLS_CA_CERT=/certs/ca.crt
REDIS_TLS_CERT=/certs/client.crt     # For mTLS
REDIS_TLS_KEY=/certs/client.key       # For mTLS
REDIS_TLS_VERIFY_MODE=required        # required|optional|none
```

**Arrow Flight TLS:**
```bash
ARROW_FLIGHT_TLS_ENABLED=true
ARROW_FLIGHT_TLS_CERT=/certs/arrow-flight.crt
ARROW_FLIGHT_TLS_KEY=/certs/arrow-flight.key
ARROW_FLIGHT_TLS_CA=/certs/ca.crt
ARROW_FLIGHT_TLS_REQUIRE_CLIENT_CERT=true  # For mTLS
```

### Files Created
- `src/blazing_service/security/tls.py` - TLS configuration classes
- `docker/generate-tls-certs.sh` - Certificate generation script

### Usage
```python
from blazing_service.security.tls import RedisTLSConfig, build_redis_url

# Redis TLS configuration
config = RedisTLSConfig.from_env('REDIS')
ssl_context = config.create_ssl_context()
url = build_redis_url('localhost', 6379, tls_config=config)
# Returns: "rediss://localhost:6379/0"

# Arrow Flight TLS (automatic from env)
# Connection automatically uses grpc+tls:// when TLS enabled
```

---

## Phase 4: Audit Logging & Rate Limiting

### Purpose
- Log security-relevant events for monitoring and compliance
- Protect against abuse with per-tenant rate limiting

### Audit Events

| Event Type | Description | Log Level |
|------------|-------------|-----------|
| `AUTH_SUCCESS` | Successful authentication | INFO |
| `AUTH_FAILURE` | Failed authentication | WARNING |
| `TOKEN_EXPIRED` | Expired JWT token | WARNING |
| `TOKEN_INVALID` | Invalid JWT token | WARNING |
| `ACCESS_GRANTED` | Successful authorization | INFO |
| `ACCESS_DENIED` | Denied authorization | ERROR |
| `CROSS_TENANT_BLOCKED` | Cross-tenant access blocked | ERROR |
| `DATA_READ` | Data read operation | INFO |
| `DATA_WRITE` | Data write operation | INFO |
| `RATE_LIMIT_WARNING` | Approaching rate limit | WARNING |
| `RATE_LIMIT_EXCEEDED` | Rate limit exceeded | ERROR |

### Audit Log Format
```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "event_type": "CROSS_TENANT_BLOCKED",
  "app_id": "tenant-a",
  "user_id": "user@example.com",
  "source_ip": "192.168.1.100",
  "resource": "arrow_flight",
  "action": "fetch",
  "outcome": "blocked",
  "details": {
    "requesting_app_id": "tenant-a",
    "target_app_id": "tenant-b",
    "reason": "cross_tenant_access_blocked"
  }
}
```

### Rate Limiting Configuration
```bash
BLAZING_RATE_LIMIT_RPS=100     # Requests per second
BLAZING_RATE_LIMIT_BURST=200   # Burst size
BLAZING_RATE_LIMIT_WINDOW=1.0  # Window in seconds
```

### Files Created
- `src/blazing_service/security/audit.py` - Audit logging and rate limiting

### Usage
```python
from blazing_service.security import (
    AuditLogger, check_rate_limit
)

# Audit logging
audit = AuditLogger.get_instance()
audit.log_auth_success(app_id="tenant-123", user_id="user@example.com")
audit.log_cross_tenant_blocked(
    requesting_app_id="tenant-a",
    target_app_id="tenant-b",
    resource="arrow_flight",
    action="fetch"
)

# Rate limiting
allowed, retry_after = check_rate_limit(
    app_id="tenant-123",
    resource="api",
    source_ip="192.168.1.100"
)
if not allowed:
    raise HTTPException(429, headers={"Retry-After": str(retry_after)})
```

---

## Security Package Structure

```
src/blazing_service/security/
├── __init__.py      # Exports all security features
├── tls.py           # TLS configuration classes
└── audit.py         # Audit logging and rate limiting
```

### Importing Security Features
```python
from blazing_service.security import (
    # TLS
    RedisTLSConfig,
    ArrowFlightTLSConfig,
    build_redis_url,
    # Audit
    AuditLogger,
    AuditEvent,
    AuditEventType,
    AuditOutcome,
    # Rate Limiting
    RateLimitConfig,
    TokenBucketRateLimiter,
    get_rate_limiter,
    check_rate_limit,
)
```

---

## Running Security Tests

```bash
# Run all security tests (71 tests)
uv run pytest tests/test_arrow_flight_security.py tests/test_security_audit.py -v

# Run specific test groups
uv run pytest tests/test_arrow_flight_security.py -v  # 43 tests
uv run pytest tests/test_security_audit.py -v         # 28 tests
```

---

## Production Recommendations

1. **TLS Certificates**: Use certificates from a trusted CA (Let's Encrypt, AWS ACM) in production
2. **JWT Secrets**: Use strong, randomly generated secrets (32+ bytes)
3. **Rate Limits**: Tune based on your workload and capacity
4. **Audit Logs**: Forward to a SIEM or log aggregation service
5. **mTLS**: Enable client certificate verification for highest security
6. **Redis ACL**: Use dedicated users per service with minimal permissions
