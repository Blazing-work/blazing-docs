# Redis-Data Security Hardening Plan

**Date:** 2024-12-15
**Status:** 🚧 PLANNING
**Target:** Apply same security measures from main Redis to redis-data

---

## Current Architecture

### Main Redis (Coordination/Metadata)
- **Image:** redis/redis-stack:latest
- **Purpose:** DAOs, queues, worker state, search indexes
- **Port:** 6379 (+ 8002 for RedisInsight)
- **Access:** API, Foreman, Executor (via blazing-network + executor-internal)
- **Storage:** Persistent volume (redis-data)

### Redis-Data (Large Payloads)
- **Image:** redis:7-alpine
- **Purpose:** StorageDAO (args/kwargs/results), large data caching
- **Port:** 6380 → 6379 (internal)
- **Access:** API, Foreman, Executor (via blazing-network + executor-internal)
- **Storage:** Persistent volume (redis-data-storage)

---

## Security Gaps Identified

### ❌ Gap 1: No Authentication
**Risk:** Anyone with network access can read/write/delete data
**Impact:** HIGH - Complete data breach, data manipulation

**Current State:**
```yaml
redis-data:
  image: redis:7-alpine
  command: redis-server --save 60 1 --loglevel warning --maxmemory 2gb --maxmemory-policy allkeys-lru
  # No --requirepass or ACL configuration
```

**Solution:** Add password authentication + ACL rules

---

### ❌ Gap 2: No Protected Mode
**Risk:** Accepts connections from any IP if no bind address specified
**Impact:** HIGH - Exposure to network-level attacks

**Current State:** Default protected-mode (yes) but no bind restriction

**Solution:** Add `--protected-mode yes` + `--bind 127.0.0.1` (Docker internal only)

---

### ❌ Gap 3: No Multi-Tenant Key Isolation
**Risk:** Tenant A can read/modify Tenant B's cached data
**Impact:** CRITICAL - Cross-tenant data leaks

**Current State:** StorageDAO uses keys like `storage:{pk}` without app_id prefix

**Solution:** Update StorageDAO to use `storage:{app_id}:{pk}` format

---

### ❌ Gap 4: No TLS Encryption
**Risk:** Data transmitted in plaintext between services
**Impact:** MEDIUM - Network sniffing risk (mitigated by Docker network isolation)

**Current State:** Redis protocol in plaintext

**Solution:** Add TLS with self-signed certs for Docker internal communication

---

### ❌ Gap 5: No Connection Limits
**Risk:** Resource exhaustion via connection flooding
**Impact:** MEDIUM - DoS attack vector

**Current State:** No maxclients limit

**Solution:** Add `--maxclients 1000`

---

### ❌ Gap 6: No Command Restrictions
**Risk:** Executor can run dangerous commands (FLUSHDB, CONFIG, SHUTDOWN)
**Impact:** HIGH - Data loss, service disruption

**Current State:** All commands allowed

**Solution:** Use ACL to restrict executor to GET/SET/DEL/EXPIRE only

---

## Recommended Security Measures

### Phase 1: Authentication & Authorization (CRITICAL)

#### 1.1 Add Password Authentication
```yaml
redis-data:
  command: redis-server --requirepass ${REDIS_DATA_PASSWORD:-blazing-dev-data-password}
```

**Environment Variables:**
```yaml
api:
  environment:
    - DATA_REDIS_PASSWORD=blazing-dev-data-password

foreman:
  environment:
    - DATA_REDIS_PASSWORD=blazing-dev-data-password

executor:
  environment:
    - DATA_REDIS_PASSWORD=blazing-dev-data-password
```

**Code Changes Required:**
- Update `src/blazing_executor/data_fetching/redis_client.py` to use password
- Update `src/blazing_service/util/util.py` (if accessing redis-data)

---

#### 1.2 Implement ACL Rules

**Create:** `docker/redis-data-acl.conf`
```acl
# Default user (disabled)
user default off

# Admin user (foreman/API) - full access
user admin on >${REDIS_DATA_ADMIN_PASSWORD:-admin-dev-password} ~* +@all

# Executor user (restricted) - data access only
user executor on >${REDIS_DATA_EXECUTOR_PASSWORD:-executor-dev-password} ~storage:* -@all +get +set +del +expire +ttl +exists
```

**Update docker-compose.yml:**
```yaml
redis-data:
  volumes:
    - redis-data-storage:/data
    - ./docker/redis-data-acl.conf:/usr/local/etc/redis/users.acl
  command: redis-server --aclfile /usr/local/etc/redis/users.acl --save 60 1 --loglevel warning --maxmemory 2gb --maxmemory-policy allkeys-lru
```

---

### Phase 2: Network Hardening (HIGH PRIORITY)

#### 2.1 Restrict Bind Address
```yaml
redis-data:
  command: redis-server --bind 0.0.0.0 --protected-mode yes --requirepass ${REDIS_DATA_PASSWORD}
```

**Note:** In Docker networks, `--bind 0.0.0.0` is safe (only accessible within Docker network)

---

#### 2.2 Add Connection Limits
```yaml
redis-data:
  command: redis-server ... --maxclients 1000 --timeout 300
```

---

### Phase 3: Multi-Tenant Key Isolation (CRITICAL)

#### 3.1 Update StorageDAO Key Format

**Current:**
```python
# src/blazing_executor/data_fetching/redis_client.py
key = f"storage:{pk}"
```

**New:**
```python
# Add app_id prefix
from blazing_service.data_access.app_context import get_app_id

app_id = get_app_id()
key = f"storage:{app_id}:{pk}"
```

**Impact:** All StorageDAO operations must be updated:
- `store_to_redis_indirect()`
- `fetch_from_redis_indirect()`
- Delete/cleanup operations

---

#### 3.2 Add Key Validation

```python
# Validate that operation's app_id matches storage key
def validate_storage_key(operation_pk: str, storage_key: str):
    """Ensure storage key belongs to operation's tenant."""
    operation_dao = await OperationDAO.get(operation_pk)
    operation_app_id = operation_dao.key().split(":")[1]

    storage_app_id = storage_key.split(":")[1]

    if operation_app_id != storage_app_id:
        raise PermissionError(
            f"Storage key {storage_key} does not belong to operation's tenant {operation_app_id}"
        )
```

---

### Phase 4: TLS Encryption (MEDIUM PRIORITY)

#### 4.1 Generate Self-Signed Certificates
```bash
cd docker/certs
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout redis-data-key.pem \
  -out redis-data-cert.pem \
  -subj "/CN=redis-data"
```

#### 4.2 Update Redis Configuration
```yaml
redis-data:
  volumes:
    - ./docker/certs:/certs:ro
  command: redis-server --tls-port 6380 --port 0 --tls-cert-file /certs/redis-data-cert.pem --tls-key-file /certs/redis-data-key.pem
```

#### 4.3 Update Clients
```python
# Use redis:// for non-TLS (current)
# Use rediss:// for TLS (future)
DATA_REDIS_URL = "rediss://redis-data:6380"
```

---

### Phase 5: Monitoring & Auditing (LOW PRIORITY)

#### 5.1 Enable Redis Slowlog
```yaml
redis-data:
  command: redis-server ... --slowlog-log-slower-than 10000 --slowlog-max-len 128
```

#### 5.2 Add Key Expiry Monitoring
- Monitor keys with TTL approaching expiration
- Alert on unexpected key deletions
- Track memory usage per app_id

---

## Implementation Priority

### 🔴 CRITICAL (Do First)
1. **Multi-Tenant Key Isolation** (Phase 3)
   - Update StorageDAO key format: `storage:{app_id}:{pk}`
   - Add validation in all data access paths
   - **Estimated Time:** 4-6 hours
   - **Files to Modify:**
     - `src/blazing_executor/data_fetching/redis_client.py`
     - `src/blazing_service/util/util.py` (if applicable)

2. **ACL Rules** (Phase 1.2)
   - Restrict executor to data operations only
   - Prevent FLUSHDB, CONFIG, SHUTDOWN
   - **Estimated Time:** 2-3 hours

### 🟡 HIGH (Do Second)
3. **Password Authentication** (Phase 1.1)
   - Add requirepass to redis-data
   - Update all clients
   - **Estimated Time:** 2 hours

4. **Network Hardening** (Phase 2)
   - Connection limits, timeout, protected-mode
   - **Estimated Time:** 1 hour

### 🟢 MEDIUM (Do Later)
5. **TLS Encryption** (Phase 4)
   - Generate certs, configure TLS
   - **Estimated Time:** 3-4 hours

### 🔵 LOW (Optional)
6. **Monitoring** (Phase 5)
   - Slowlog, auditing
   - **Estimated Time:** 2-3 hours

---

## Testing Requirements

### Security Tests to Add

1. **Cross-Tenant Storage Access** (`tests/test_redis_data_security.py`)
   ```python
   async def test_storage_key_isolation():
       """Test that tenant-a cannot access tenant-b's storage."""
       # Store data as tenant-a
       set_app_id("tenant-a")
       storage_key_a = await store_to_redis_indirect(data_a, pk_a)

       # Try to access as tenant-b
       set_app_id("tenant-b")
       with pytest.raises(PermissionError):
           await fetch_from_redis_indirect(storage_key_a)
   ```

2. **ACL Command Restrictions**
   ```python
   async def test_executor_cannot_flush_redis_data():
       """Test that executor user cannot run FLUSHDB."""
       # Connect as executor user
       client = redis.from_url(
           "redis://executor:executor-dev-password@redis-data:6379"
       )
       with pytest.raises(redis.ResponseError, match="NOPERM"):
           await client.flushdb()
   ```

3. **Password Authentication**
   ```python
   async def test_redis_data_requires_password():
       """Test that redis-data rejects unauthenticated connections."""
       client = redis.from_url("redis://redis-data:6379")  # No password
       with pytest.raises(redis.AuthenticationError):
           await client.ping()
   ```

---

## Migration Plan

### Step 1: Add Multi-Tenant Keys (No Breaking Changes)
- Deploy new code that writes with `storage:{app_id}:{pk}` format
- Old code can still read old keys (fallback logic)
- No data migration needed (old keys expire naturally with TTL)

### Step 2: Add ACL (Graceful Degradation)
- Deploy ACL config with backward-compatible default user
- Gradually migrate services to use new ACL users
- Disable default user once all services migrated

### Step 3: Add Password (Rolling Update)
- Add password to redis-data config
- Update clients to use password
- No downtime if done in correct order (clients first, then server)

---

## Comparison with Main Redis

| Security Feature | Main Redis | Redis-Data (Current) | Redis-Data (Target) |
|------------------|-----------|----------------------|---------------------|
| Authentication | ❌ None | ❌ None | ✅ ACL users |
| Network Isolation | ✅ Docker networks | ✅ Docker networks | ✅ Same |
| Memory Limits | ✅ 2GB LRU | ✅ 2GB LRU | ✅ Same |
| Protected Mode | ⚠️ Default | ⚠️ Default | ✅ Explicit |
| Command Restrictions | ❌ None | ❌ None | ✅ ACL |
| Multi-Tenant Keys | ✅ app_id prefix | ❌ None | ✅ app_id prefix |
| TLS | ❌ None | ❌ None | 🟡 Optional |
| Connection Limits | ❌ None | ❌ None | ✅ maxclients |
| Monitoring | ⚠️ Basic | ⚠️ Basic | ✅ Slowlog |

---

## Success Criteria

✅ **Phase 1 Complete When:**
- Executor cannot run FLUSHDB, CONFIG, SHUTDOWN
- All connections require password
- Security tests pass

✅ **Phase 2 Complete When:**
- Connection limits prevent DoS
- Protected mode explicitly enabled

✅ **Phase 3 Complete When:**
- StorageDAO uses `storage:{app_id}:{pk}` format
- Cross-tenant access tests fail with PermissionError
- All existing E2E tests still pass

✅ **Phase 4 Complete When:**
- TLS certificates generated
- All clients use rediss:// protocol
- Network sniffing tests show encrypted traffic

---

## Rollback Plan

If security hardening causes issues:

1. **ACL Issues**: Restore default user temporarily
2. **Password Issues**: Remove --requirepass, restart redis-data
3. **Key Format Issues**: Add fallback logic to try both formats
4. **TLS Issues**: Revert to plain Redis protocol

**Monitoring During Rollout:**
- Watch redis-data connection errors
- Monitor StorageDAO operation failures
- Track E2E test pass rate

---

## Next Steps

**Immediate Actions:**
1. ✅ Create this security plan document
2. [ ] Review plan with team
3. [ ] Create `tests/test_redis_data_security.py`
4. [ ] Implement Phase 1 (ACL) in development environment
5. [ ] Implement Phase 3 (Multi-tenant keys) in development
6. [ ] Run full test suite
7. [ ] Deploy to staging for validation
8. [ ] Production deployment (with rollback plan ready)

---

**Document Owner:** Blazing Security Team
**Last Updated:** 2024-12-15
**Next Review:** After Phase 1 implementation
