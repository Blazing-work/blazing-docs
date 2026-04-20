# Arrow Flight Security Assessment

**Date:** 2025-12-15
**Status:** ⚠️ **VULNERABLE** - Multi-tenant isolation NOT implemented
**Priority:** HIGH - Critical security gap for production deployments

---

## Executive Summary

Arrow Flight currently has **NO multi-tenant security hardening**. Any tenant can access any other tenant's data if they know or guess the primary key. This is a critical security vulnerability for production multi-tenant deployments.

**Risk Level:** 🔴 **HIGH**
**Impact:** Cross-tenant data leakage, unauthorized access to sensitive data
**Effort to Fix:** 4-6 hours (Phase 1 - Multi-tenant isolation)

---

## Current Security Status

### ❌ Missing Security Features

| Feature | Status | Impact |
|---------|--------|--------|
| Multi-tenant key isolation | ❌ NOT IMPLEMENTED | Tenants can access each other's data |
| app_id namespace in addresses | ❌ NOT IMPLEMENTED | No tenant boundaries enforced |
| Cross-tenant access validation | ❌ NOT IMPLEMENTED | No PermissionError on unauthorized access |
| Authentication | ❌ NOT IMPLEMENTED | No identity verification |
| Authorization/ACL | ❌ NOT IMPLEMENTED | No role-based permissions |
| Audit logging | ❌ NOT IMPLEMENTED | No tracking of data access |
| TLS/mTLS encryption | ❌ NOT IMPLEMENTED | Unencrypted gRPC connections |

### ✅ Existing Security Features

| Feature | Status | Notes |
|---------|--------|-------|
| Memory limits | ✅ IMPLEMENTED | 10 GB cap prevents DoS (memory exhaustion) |
| TTL-based expiration | ✅ IMPLEMENTED | 1 hour default, prevents data accumulation |
| Capacity enforcement | ✅ IMPLEMENTED | Rejects uploads when buffer full |
| Thread-safe storage | ✅ IMPLEMENTED | Concurrent access protected by locks |

---

## Vulnerability Details

### Critical Vulnerability: Cross-Tenant Data Access

**Attack Vector:**
```python
# Tenant A stores sensitive data
set_app_id("tenant-a")
df_secret = pd.DataFrame({"ssn": ["123-45-6789"], "salary": [150000]})
address = await store_to_arrow(df_secret, "payroll-2024")
# Returns: arrow|arrow-flight:8815|payroll-2024|arrow-flight:8816

# Tenant B discovers/guesses the key and steals data
set_app_id("tenant-b")
address_stolen = "arrow|arrow-flight:8815|payroll-2024|arrow-flight:8816"
stolen_data = await fetch_from_arrow(address_stolen)
# SUCCESS ❌ - No validation prevents this attack!
```

**Root Cause:** Primary keys have NO app_id namespace

**Current Address Format (INSECURE):**
```
arrow|grpc_endpoint|pk|ipc_endpoint
Example: arrow|arrow-flight:8815|payroll-2024|arrow-flight:8816
                              ↑
                              NO app_id - any tenant can use this!
```

### Comparison with Redis-Data (Secure)

Redis-data has proper multi-tenant isolation:

**Redis-Data Address Format (SECURE):**
```
RedisIndirect|app_id|pk
Example: RedisIndirect|tenant-a|payroll-2024
                       ↑
                       app_id namespace - enforces tenant boundaries
```

**Validation Code ([redis_client.py:254-271](../src/blazing_executor/data_fetching/redis_client.py#L254-L271)):**
```python
# Parse address with app_id
parts = address.split('|')
address_app_id = parts[1]  # Extract tenant from address
address_pk = parts[2]

# Validate against current context
current_app_id = get_app_id()
if address_app_id != current_app_id:
    raise PermissionError(
        f"Storage address app_id '{address_app_id}' does not match "
        f"current context app_id '{current_app_id}'"
    )
```

**Arrow Flight has NONE of this validation!**

---

## Architecture Analysis

### Current Implementation

**Files Involved:**
1. **[src/blazing_executor/data_fetching/arrow_client.py](../src/blazing_executor/data_fetching/arrow_client.py)** - Client functions
2. **[docker/start_arrow_flight.py](../docker/start_arrow_flight.py)** - Flight server
3. **[docker-compose.yml](../docker-compose.yml)** - Service configuration

**Address Format Parsing ([arrow_client.py:66-74](../src/blazing_executor/data_fetching/arrow_client.py#L66-L74)):**
```python
# Parse address: arrow|grpc_endpoint|pk|ipc_endpoint
parts = address.split('|')
if len(parts) != 4 or parts[0] != 'arrow':
    raise ValueError(f"Invalid Arrow Flight address format...")

grpc_endpoint = parts[1]
primary_key = parts[2]      # ❌ NO app_id extracted
ipc_endpoint = parts[3]     # Reserved for future streaming
```

**Storage ([arrow_client.py:99-162](../src/blazing_executor/data_fetching/arrow_client.py#L99-L162)):**
```python
async def store_to_arrow(data: Any, primary_key: str, ...) -> str:
    # ❌ NO app_id context check
    # ❌ primary_key used directly without namespace

    descriptor = flight.FlightDescriptor.for_path(primary_key.encode('utf-8'))
    writer, _ = client.do_put(descriptor, table.schema)
    writer.write_table(table)

    return f"arrow|{grpc_endpoint}|{primary_key}|{ipc_endpoint}"
    #                              ↑
    #                              NO app_id in address!
```

**Retrieval ([arrow_client.py:44-96](../src/blazing_executor/data_fetching/arrow_client.py#L44-L96)):**
```python
async def fetch_from_arrow(address: str) -> Any:
    parts = address.split('|')
    primary_key = parts[2]  # ❌ NO app_id validation

    ticket = flight.Ticket(primary_key.encode('utf-8'))
    flight_reader = client.do_get(ticket)  # ❌ NO permission check!
    return flight_reader.read_all().to_pandas()
```

**Server Storage ([start_arrow_flight.py:45-46](../docker/start_arrow_flight.py#L45-L46)):**
```python
# In-memory storage: primary_key -> (data_bytes, expires_at, size_bytes)
self._data_store: Dict[str, Tuple[bytes, float, int]] = {}
#                      ↑
#                      Keys are plain strings - NO tenant namespace!
```

### IPC Endpoint Clarification

**Question:** Does Arrow Flight support both gRPC AND IPC protocols?

**Answer:** No, there is only ONE protocol.

**Arrow Flight Architecture:**
- **Transport Layer:** gRPC (port 8815) - handles network communication
- **Serialization Format:** Arrow IPC (Inter-Process Communication format) - columnar binary encoding

**Address Format Breakdown:**
```
arrow|grpc_endpoint|pk|ipc_endpoint
      ↓                 ↓
   grpc://arrow-flight:8815  (ACTIVE - used for data transfer)
   arrow-flight:8816         (RESERVED - placeholder for future streaming)
```

**Current Behavior:**
- Client connects to gRPC endpoint (port 8815)
- Uses Arrow Flight protocol over gRPC (do_put, do_get)
- Data serialized using Arrow IPC format internally
- IPC endpoint (port 8816) is **not used** - reserved for future feature

**Future Streaming Feature (why IPC endpoint exists):**
The IPC endpoint was reserved for potential enhancement:
- **Current:** Batch transfer (entire table at once)
- **Future:** Streaming transfer (incremental record batches)
- **Benefit:** Lower latency for real-time analytics

---

## Recommended Security Hardening

### Phase 1: Multi-Tenant Key Isolation (CRITICAL)

**Priority:** HIGH
**Effort:** 4-6 hours
**Impact:** Prevents cross-tenant data access

#### 1.1 Update Address Format

**New Format:**
```
arrow|grpc_endpoint|app_id|pk|ipc_endpoint
Example: arrow|arrow-flight:8815|tenant-a|op-123|arrow-flight:8816
```

#### 1.2 Modify [arrow_client.py](../src/blazing_executor/data_fetching/arrow_client.py)

**Changes Required:**

**A. Update `store_to_arrow()` (lines 99-162):**
```python
async def store_to_arrow(data: Any, primary_key: str, ...) -> str:
    """Store data to Arrow Flight server with multi-tenant isolation."""
    # Get current app_id from context
    from blazing_service.data_access.app_context import get_app_id
    app_id = get_app_id()
    if not app_id:
        raise ValueError("app_id context not set - call set_app_id() before storing")

    # Namespace primary key with app_id
    namespaced_key = f"{app_id}:{primary_key}"

    # Store with namespaced key
    descriptor = flight.FlightDescriptor.for_path(namespaced_key.encode('utf-8'))
    writer, _ = client.do_put(descriptor, table.schema)
    writer.write_table(table)

    # Return address with app_id
    return f"arrow|{grpc_endpoint}|{app_id}|{primary_key}|{ipc_endpoint}"
```

**B. Update `fetch_from_arrow()` (lines 44-96):**
```python
async def fetch_from_arrow(address: str) -> Any:
    """Fetch data from Arrow Flight server with multi-tenant validation."""
    # Parse address: arrow|grpc|app_id|pk|ipc
    parts = address.split('|')
    if len(parts) != 5 or parts[0] != 'arrow':
        raise ValueError(
            f"Invalid Arrow Flight address format. "
            f"Expected: arrow|grpc|app_id|pk|ipc, got: {address}"
        )

    grpc_endpoint = parts[1]
    address_app_id = parts[2]
    primary_key = parts[3]
    ipc_endpoint = parts[4]

    # Validate app_id matches current context
    from blazing_service.data_access.app_context import get_app_id
    current_app_id = get_app_id()
    if not current_app_id:
        raise ValueError("app_id context not set - call set_app_id() before fetching")

    if address_app_id != current_app_id:
        raise PermissionError(
            f"Arrow Flight address app_id '{address_app_id}' does not match "
            f"current context app_id '{current_app_id}'. Cross-tenant access denied."
        )

    # Fetch with namespaced key
    namespaced_key = f"{address_app_id}:{primary_key}"
    ticket = flight.Ticket(namespaced_key.encode('utf-8'))
    flight_reader = client.do_get(ticket)
    return flight_reader.read_all().to_pandas()
```

#### 1.3 Update Server ([start_arrow_flight.py](../docker/start_arrow_flight.py))

**No changes required!** Server stores keys as-is. Client-side enforcement is sufficient because:
- Server is trusted infrastructure (not exposed to tenants)
- Client validates app_id before constructing keys
- Keys automatically namespaced: `{app_id}:{pk}` format

#### 1.4 Update Tests

**Create new test file:** `tests/test_arrow_flight_security.py`

**Test Coverage Required:**
1. Multi-tenant key isolation (same pattern as `test_redis_data_security.py`)
2. Cross-tenant access prevention (PermissionError on mismatch)
3. app_id context validation (raises if context not set)
4. Address format validation (5 parts required)

**Example Test:**
```python
@pytest.mark.asyncio
async def test_cannot_fetch_other_tenant_arrow_data(self):
    """Test that tenant B cannot access tenant A's Arrow Flight data."""
    from blazing_executor.data_fetching.arrow_client import fetch_from_arrow
    from blazing_service.data_access.app_context import set_app_id, clear_app_id

    # Address created by tenant-a
    address_tenant_a = "arrow|arrow-flight:8815|tenant-a|payroll-2024|arrow-flight:8816"

    # Try to access as tenant-b
    clear_app_id(force=True)
    set_app_id("tenant-b", lock=False)

    # Should raise PermissionError
    with pytest.raises(PermissionError, match="does not match current context"):
        await fetch_from_arrow(address_tenant_a)

    clear_app_id(force=True)
```

#### 1.5 Update Existing Tests

**Files to Update:**
- `tests/test_arrow_client_unit.py` - Update address format in all tests
- `tests/test_z_arrow_flight_e2e.py` - Add app_id context management
- `tests/test_z_arrow_flight_client.py` - Update address parsing tests

**Pattern:**
```python
from blazing_service.data_access.app_context import set_app_id, clear_app_id

clear_app_id(force=True)
set_app_id("default", lock=False)

# Test code here
# Use format: arrow|grpc|default|pk|ipc

clear_app_id(force=True)
```

---

### Phase 2: Authentication & Authorization (OPTIONAL)

**Priority:** MEDIUM (for high-security deployments)
**Effort:** 8-12 hours
**Impact:** Defense in depth, compliance requirements

#### 2.1 Add Token-Based Authentication

**Implementation:**
1. Arrow Flight supports middleware for authentication
2. Add JWT token validation in Flight server
3. Map tokens to app_id for authorization

**Server Changes:**
```python
class BlazingFlightServer(flight.FlightServerBase):
    def __init__(self, location: str, ...):
        # Add middleware for token validation
        middleware = {
            "authentication": TokenAuthMiddleware()
        }
        super().__init__(location, middleware=middleware)
```

#### 2.2 Add TLS Encryption

**Implementation:**
1. Generate SSL/TLS certificates
2. Configure gRPC with TLS
3. Update client connection strings

**Docker Compose:**
```yaml
arrow-flight:
  environment:
    - ARROW_FLIGHT_TLS_CERT=/certs/server.crt
    - ARROW_FLIGHT_TLS_KEY=/certs/server.key
  volumes:
    - ./certs:/certs:ro
```

#### 2.3 Add Audit Logging

**Implementation:**
```python
def do_get(self, context, ticket):
    """Retrieve data with audit logging."""
    pk = ticket.ticket.decode('utf-8')
    user_id = context.peer_identity()  # From auth middleware

    # Log access
    logger.info(
        "arrow_flight_access",
        extra={
            "user_id": user_id,
            "primary_key": pk,
            "action": "fetch",
            "timestamp": time.time()
        }
    )

    # Continue with fetch...
```

---

## Testing Strategy

### Unit Tests (New File: `tests/test_arrow_flight_security.py`)

**Test Classes:**
1. `TestArrowKeyIsolation` - Multi-tenant key namespacing
2. `TestArrowCrossTenantPrevention` - PermissionError on unauthorized access
3. `TestArrowAppIdContext` - Context validation
4. `TestArrowAddressFormat` - 5-part address parsing

**Test Count:** ~15-20 tests

### Integration Tests (Update: `tests/test_z_arrow_flight_e2e.py`)

**Test Scenarios:**
1. Store and fetch with matching app_id (should succeed)
2. Fetch with wrong app_id (should fail with PermissionError)
3. Store without app_id context (should fail with ValueError)
4. Address with old 4-part format (should fail with ValueError)

### Migration Tests

**Verify:**
- All existing Arrow Flight tests updated with app_id context
- No tests using old 4-part address format
- All assertions updated for new 5-part format

---

## Deployment Checklist

### Pre-Deployment

- [ ] Code review for multi-tenant changes
- [ ] All unit tests passing (including new security tests)
- [ ] All integration tests passing
- [ ] Performance testing (ensure no regression)
- [ ] Documentation updated

### Deployment Steps

1. [ ] Deploy updated `arrow_client.py` to all executor containers
2. [ ] Restart Arrow Flight server (no code changes needed)
3. [ ] Run smoke tests with multi-tenant workloads
4. [ ] Monitor logs for PermissionError (expected if migration incomplete)
5. [ ] Verify cross-tenant isolation working correctly

### Post-Deployment

- [ ] Monitor error rates for PermissionError
- [ ] Audit access logs for suspicious patterns
- [ ] Performance metrics (latency, throughput)
- [ ] Update security documentation

---

## Security Impact Summary

### Before Hardening (Current State)

| Attack Vector | Exploitability | Impact | Risk Level |
|---------------|----------------|--------|------------|
| Cross-tenant data access | HIGH (trivial) | HIGH (data leakage) | 🔴 CRITICAL |
| Primary key guessing | MEDIUM | HIGH (unauthorized access) | 🔴 HIGH |
| Data tampering | HIGH (no auth) | HIGH (integrity violation) | 🔴 HIGH |
| Eavesdropping | HIGH (no TLS) | MEDIUM (unencrypted gRPC) | 🟡 MEDIUM |

### After Phase 1 (Multi-Tenant Isolation)

| Attack Vector | Exploitability | Impact | Risk Level |
|---------------|----------------|--------|------------|
| Cross-tenant data access | ❌ BLOCKED | N/A | ✅ MITIGATED |
| Primary key guessing | LOW (must guess app_id + pk) | MEDIUM | 🟡 MEDIUM |
| Data tampering | HIGH (no auth) | HIGH | 🔴 HIGH |
| Eavesdropping | HIGH (no TLS) | MEDIUM | 🟡 MEDIUM |

### After Phase 2 (Auth + TLS)

| Attack Vector | Exploitability | Impact | Risk Level |
|---------------|----------------|--------|------------|
| Cross-tenant data access | ❌ BLOCKED | N/A | ✅ MITIGATED |
| Primary key guessing | ❌ BLOCKED (auth required) | N/A | ✅ MITIGATED |
| Data tampering | ❌ BLOCKED (auth required) | N/A | ✅ MITIGATED |
| Eavesdropping | ❌ BLOCKED (TLS) | N/A | ✅ MITIGATED |

---

## Comparison with Redis Security

### Redis-Data Security (IMPLEMENTED) ✅

| Feature | Status | Implementation |
|---------|--------|----------------|
| Multi-tenant isolation | ✅ | `RedisIndirect\|app_id\|pk` format |
| Cross-tenant validation | ✅ | PermissionError on mismatch |
| ACL users | ✅ | admin, executor, coordinator, api (4 roles) |
| Password authentication | ✅ | 32-character random passwords |
| Command restrictions | ✅ | Executor blocked from FLUSHDB, CONFIG, etc. |
| Key pattern restrictions | ✅ | `~blazing:*:unit_definition:Storage:*` |

**Lessons from Redis-Data Implementation:**
1. Multi-tenant isolation is **foundational** - must be first
2. app_id context management is **critical** - every access needs validation
3. Test migration is **extensive** - all tests need app_id context
4. Security documentation is **essential** - deployment guide prevents mistakes

### Arrow Flight Security (NOT IMPLEMENTED) ❌

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-tenant isolation | ❌ | No app_id in addresses |
| Cross-tenant validation | ❌ | No PermissionError checks |
| Authentication | ❌ | Open access |
| Authorization | ❌ | No role-based permissions |
| TLS encryption | ❌ | Unencrypted gRPC |

**Gap:** Arrow Flight is ~6 months behind Redis-Data in security maturity.

---

## Recommendations

### Immediate Actions (Week 1)

1. **🔴 CRITICAL:** Implement Phase 1 (multi-tenant isolation)
2. **🔴 CRITICAL:** Create security test suite (`test_arrow_flight_security.py`)
3. **🟡 HIGH:** Update all existing tests with app_id context
4. **🟡 HIGH:** Document deployment process

### Short-Term (Month 1)

1. **🟡 MEDIUM:** Add monitoring for PermissionError (detect attacks)
2. **🟡 MEDIUM:** Performance testing with multi-tenant workloads
3. **🟢 LOW:** Create security runbook for incident response

### Long-Term (Quarter 1)

1. **🟡 MEDIUM:** Implement Phase 2 (authentication + TLS)
2. **🟡 MEDIUM:** Add audit logging for compliance
3. **🟢 LOW:** Security penetration testing

---

## References

### Internal Documentation
- [Redis-Data Security Deployment Guide](redis-data-security-deployment.md)
- [Redis-Data Security Plan](redis-data-security-plan.md)
- [Arrow Flight Setup Guide](arrow-flight-setup.md)
- [Multi-Tenant Architecture](../src/blazing_service/data_access/app_context.py)

### External Resources
- [Arrow Flight Documentation](https://arrow.apache.org/docs/python/flight.html)
- [gRPC Security](https://grpc.io/docs/guides/auth/)
- [OWASP Multi-Tenancy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multitenant_Architecture_Cheat_Sheet.html)

---

**Document Status:** ✅ COMPLETE
**Next Review:** After Phase 1 implementation
**Owner:** Security Team
