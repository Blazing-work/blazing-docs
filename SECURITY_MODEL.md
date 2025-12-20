# Blazing Security Model

This document describes the security architecture for Blazing's multi-tenant worker pool system.

## Overview

Blazing implements a **defense-in-depth** security model with multiple layers of protection:

1. **JWT Authentication** - All API requests require valid tokens
2. **Customer Isolation** - Docker-level tenant boundaries
3. **App ID Context Locking** - Request-scoped namespace protection
4. **Rate Limiting** - Protection against abuse
5. **Audit Logging** - Security event tracking

## Security Assessment Score: 85/100 (STRONG)

Last assessed: 2025-12-16

---

## 1. JWT Authentication

### Token Requirements
- **Algorithm**: HS256
- **Minimum Secret Length**: 32 characters
- **Required Claims**: `app_id`, `exp`
- **Optional Claims**: `customer_id` (for customer isolation)

### Production Requirements
```bash
# REQUIRED: Set a strong secret (minimum 32 characters)
export BLAZING_JWT_SECRET="your-32+-character-secret-here"

# Production fails immediately if not set
```

### Weak Secret Detection
The system checks JWT secrets against known weak patterns:
- Common test tokens (`test-token`, `dev-secret`)
- Short secrets (< 32 characters)
- Secrets with low entropy

---

## 2. Customer Isolation (Phase 10)

### Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                 CUSTOMER_ID: acme-corp                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │           Docker Container: blazing-coordinator-acme          │  │
│  │                                                           │  │
│  │   Coordinator (customer_id=acme-corp)                        │  │
│  │     ├── AppWorkerPool (app_id=acme-prod)                 │  │
│  │     ├── AppWorkerPool (app_id=acme-staging)              │  │
│  │     └── AppWorkerPool (app_id=acme-dev)                  │  │
│  │                                                           │  │
│  │   CANNOT see: beta-corp-*, other-customer-*              │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Functions

#### `set_customer_context(customer_id, owned_app_ids)`
- Called ONCE at worker startup
- **Immutable** - cannot be changed after set
- Defines the set of app_ids this worker can access

#### `is_app_id_owned(app_id)`
- Validates if an app_id belongs to the current customer
- Returns `True` in legacy mode (no customer isolation)
- Returns `True/False` based on `owned_app_ids` set

### Deployment
```yaml
# Customer-specific coordinator
coordinator-acme:
  environment:
    - CUSTOMER_ID=acme-corp
    - REDIS_URL=redis://redis:6379
```

---

## 3. App ID Context Locking

### Purpose
Prevents malicious code from switching to another tenant's namespace mid-request.

### How It Works
```python
# In verify_token() - locks context for request lifetime
set_app_id(app_id, lock=True)

# Any attempt to change app_id raises PermissionError
set_app_id("other-tenant")  # BLOCKED!
```

### Security Model
```
Request → JWT Validation → set_app_id(lock=True) → DAO Operations
                                    ↓
                         All DAO operations use
                         locked app_id namespace
```

### Redis Key Namespacing
All data is stored with app_id prefix:
```
blazing:{app_id}:route_definition:Station:{pk}
blazing:{app_id}:unit_definition:Operation:{pk}
blazing:{app_id}:execution:WorkerThread:{pk}
```

---

## 4. Rate Limiting

### Protected Endpoints
| Endpoint | Rate Limit |
|----------|------------|
| `/v1/registry/sync` | ✅ Expensive endpoint limit |
| `/v1/metrics/worker-mix` | ✅ Expensive endpoint limit |
| `/v1/metrics/worker-lifecycle` | ✅ Expensive endpoint limit |
| `/v1/metrics/app-pools` | ✅ Expensive endpoint limit |
| `/v1/metrics/workers/actual` | ✅ Expensive endpoint limit |
| `/v1/metrics/queues` | ✅ Expensive endpoint limit |
| `/v1/auth/*` | ✅ Auth endpoint limit |

### Configuration
```bash
# Rate limiting configuration
BLAZING_RATE_LIMIT_RPS=100      # Requests per second
BLAZING_RATE_LIMIT_BURST=200    # Burst size
BLAZING_RATE_LIMIT_WINDOW=1.0   # Window in seconds
```

---

## 5. Audit Logging

### Event Types
| Event Type | Description |
|------------|-------------|
| `AUTH_SUCCESS` | Successful authentication |
| `AUTH_FAILURE` | Failed authentication attempt |
| `ACCESS_GRANTED` | Authorization check passed |
| `ACCESS_DENIED` | Authorization check failed |
| `CROSS_TENANT_BLOCKED` | Cross-tenant access attempt blocked |
| `RATE_LIMIT_EXCEEDED` | Rate limit hit |
| `CONFIG_CHANGE` | Security configuration changed |

### Logged Operations
- Customer context changes (`set_customer_context`)
- App ID context changes (blocked attempts only)
- Cross-tenant access attempts
- Rate limit events

### Configuration
```bash
# Audit log level
BLAZING_AUDIT_LOG_LEVEL=INFO

# Optional: File output
BLAZING_AUDIT_LOG_FILE=/var/log/blazing/audit.log
```

### Log Format
```json
{
  "timestamp": "2025-12-16T10:30:00.000Z",
  "event_type": "CROSS_TENANT_BLOCKED",
  "app_id": "acme-corp",
  "resource": "app_context",
  "action": "set_app_id",
  "outcome": "blocked",
  "details": {
    "customer_id": "acme-corp",
    "attempted_app_id": "beta-main",
    "reason": "app_id_not_owned"
  }
}
```

---

## 6. Data Endpoint Security

### Tenant Filtering
All data listing endpoints filter results by customer ownership:

| Endpoint | Filtering |
|----------|-----------|
| `GET /v1/data/services` | ✅ Filtered by owned app_ids |
| `GET /v1/data/stations` | ✅ Filtered by owned app_ids |
| `GET /v1/data/routes` | ✅ Filtered by owned app_ids |
| `GET /v1/ui/stations` | ✅ Filtered by owned app_ids |
| `GET /v1/ui/routes` | ✅ Filtered by owned app_ids |
| `GET /v1/ui/services` | ✅ Filtered by owned app_ids |

### Implementation Pattern
```python
# Get owned app_ids from request context
owned_app_ids = await get_owned_app_ids_for_request(request)

# Filter results
for item in items:
    item_app_id = extract_app_id_from_key(item.key())
    if owned_app_ids is not None and item_app_id not in owned_app_ids:
        continue  # Skip - not owned by this customer
```

---

## 7. Sandboxed Execution

### Trust Boundaries
```
YOUR INFRASTRUCTURE (trusted)
└── Coordinator / Coordinator

────────────────────────────────

TENANT'S CODE (semi-trusted)
└── Services + Connectors
    Runs on TRUSTED workers

────────────────────────────────

USER'S CODE (untrusted)
└── Stations / Routes in Pyodide sandbox
    Runs on SANDBOXED workers
```

### Worker Types
| Type | Trust Level | Execution |
|------|-------------|-----------|
| BLOCKING | Trusted | Docker executor |
| NON_BLOCKING | Trusted | Docker executor |
| BLOCKING_SANDBOXED | Untrusted | Pyodide WASM |
| NON_BLOCKING_SANDBOXED | Untrusted | Pyodide WASM |

---

## Security Checklist

### Deployment
- [ ] Set strong `BLAZING_JWT_SECRET` (32+ characters)
- [ ] Configure `CUSTOMER_ID` for tenant isolation
- [ ] Enable audit logging
- [ ] Review rate limit settings

### Development
- [ ] Never commit secrets to version control
- [ ] Use environment variables for configuration
- [ ] Test with multiple tenant scenarios

---

## Vulnerabilities Fixed (2025-12-16)

### VULN-DATA-001: Data Listing Endpoints Leak Cross-Tenant Data
**Severity**: CRITICAL
**Status**: FIXED
**Fix**: Added `get_owned_app_ids_for_request()` filtering to all 6 data listing endpoints

### VULN-DATA-002: System Info Exposes Infrastructure Without Auth
**Severity**: HIGH
**Status**: FIXED
**Fix**: Added `dependencies=[Depends(verify_token)]` to `/v1/system/info`

### VULN-RATE-001: Missing Rate Limiting on Metrics Endpoints
**Severity**: MEDIUM
**Status**: FIXED
**Fix**: Added `rate_limit_expensive_endpoint` to `/v1/metrics/worker-mix`, `/v1/metrics/worker-lifecycle`, `/v1/metrics/app-pools`

### VULN-WORKER-001: Worker App ID Context Not Locked
**Severity**: MEDIUM
**Status**: VERIFIED SECURE
**Analysis**: Workers use `set_customer_context()` which provides equivalent security by locking the customer boundary. Workers legitimately need to switch between owned app_ids when processing operations.

---

## Reporting Security Issues

Please report security vulnerabilities to: https://github.com/anthropics/claude-code/issues

Do NOT create public issues for security vulnerabilities.
