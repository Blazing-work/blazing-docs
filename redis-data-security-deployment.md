# Redis-Data Security Deployment Guide

**Status**: ✅ COMPLETE - Ready for deployment
**Date**: 2024-12-15

This guide walks through deploying the new Redis-data security hardening:
- Multi-tenant key isolation
- ACL role-based access control
- Password authentication
- Command restrictions

---

## 🔒 Security Features Implemented

### Phase 1: Multi-Tenant Key Isolation ✅
- **Address format**: `RedisIndirect|{app_id}|{pk}` (was: `RedisIndirect|{pk}`)
- **Storage keys**: `blazing:{app_id}:unit_definition:Storage:{pk}`
- **Cross-tenant validation**: Address app_id must match execution context app_id
- **Test coverage**: 17 tests (all passing)

### Phase 2: ACL + Password Authentication ✅
- **ACL users**: admin, executor, coordinator, api (4 roles)
- **Command restrictions**:
  - Executor: GET, SET, DEL, HGET, HSET, HDEL, HGETALL, HEXISTS, EXPIRE, TTL, PING, EXISTS
  - Blocked: FLUSHDB, CONFIG, SHUTDOWN, ACL, SCRIPT, KEYS (for executor)
- **Key patterns**: `~blazing:*:unit_definition:Storage:*` (multi-tenant access at app layer)
- **Password strength**: 32-character random passwords (base64)

---

## 📋 Deployment Steps

### Step 1: Generate Redis Passwords

```bash
# Generate secure random passwords
cd /Users/jonathanborduas/code/blazing
./docker/generate-redis-passwords.sh

# This creates .env.redis-passwords with 4 passwords:
# - REDIS_ADMIN_PASSWORD (full access)
# - REDIS_DATA_EXECUTOR_PASSWORD (executor user)
# - REDIS_DATA_COORDINATOR_PASSWORD (coordinator user)
# - REDIS_DATA_API_PASSWORD (api user)
```

**Output:**
```
✓ Passwords generated and saved to: .env.redis-passwords
✓ File permissions set to 600 (owner read/write only)
```

### Step 2: Load Environment Variables

```bash
# Source the password file
source .env.redis-passwords

# Or add to docker-compose.yml env_file:
# env_file:
#   - .env.redis-passwords
```

**Verification:**
```bash
echo $REDIS_DATA_EXECUTOR_PASSWORD
# Should output 32-character password
```

### Step 3: Restart Redis-Data Container

```bash
# Stop and remove old container (WARNING: This deletes all data!)
docker-compose stop redis-data
docker-compose rm -f redis-data

# Start with new ACL configuration
docker-compose up -d redis-data

# Check logs for ACL initialization
docker logs blazing-redis-data
```

**Expected logs:**
```
Redis Data Entrypoint - Applying ACL configuration...
✓ ACL configuration prepared with passwords
✓ Users configured: admin, executor, coordinator, api
✓ Server initialized
```

### Step 4: Restart Services That Use Redis-Data

```bash
# Restart all services that connect to redis-data
docker-compose restart executor coordinator api pyodide-executor arrow-flight

# Check health
docker-compose ps
```

**Expected status:**
```
NAME                 STATUS
blazing-redis-data   Up (healthy)
blazing-executor     Up (healthy)
blazing-coordinator      Up (healthy)
blazing-api          Up (healthy)
```

### Step 5: Verify ACL Permissions

```bash
# Test executor user (should succeed)
docker exec blazing-redis-data redis-cli \
  -u executor \
  -a "$REDIS_DATA_EXECUTOR_PASSWORD" \
  HGET blazing:test-app:unit_definition:Storage:test-key value

# Test executor trying forbidden command (should fail)
docker exec blazing-redis-data redis-cli \
  -u executor \
  -a "$REDIS_DATA_EXECUTOR_PASSWORD" \
  FLUSHDB
# Expected: (error) NOPERM this user has no permissions to run the 'flushdb' command
```

### Step 6: Run Security Tests

```bash
# Run all redis-data security tests
uv run pytest tests/test_redis_data_security.py -v

# Expected: 17 passed
```

---

## 🔐 ACL User Roles

### 1. **admin** - Operations & Monitoring
- **Access**: ALL commands (`+@all`)
- **Keys**: ALL (`~*`)
- **Usage**: Manual operations, monitoring, migrations
- **Credentials**: `REDIS_ADMIN_PASSWORD`

```bash
# Example: Manual data inspection
docker exec blazing-redis-data redis-cli \
  -u admin \
  -a "$REDIS_ADMIN_PASSWORD" \
  KEYS "blazing:*"
```

### 2. **executor** - Code Execution Containers
- **Access**: GET, SET, DEL, HGET, HSET, HDEL, HGETALL, HEXISTS, EXPIRE, TTL, PING, EXISTS
- **Keys**: `~blazing:*:unit_definition:Storage:*`, `~blazing:*:route_definition:Service:*`
- **Usage**: Docker executor, Pyodide executor
- **Credentials**: `REDIS_DATA_EXECUTOR_PASSWORD`

**Blocked commands**: FLUSHDB, CONFIG, SHUTDOWN, ACL, SCRIPT, KEYS

### 3. **coordinator** - Background Workers
- **Access**: All executor permissions + KEYS, SCAN, DBSIZE, INFO
- **Keys**: `~blazing:*` (all patterns)
- **Usage**: Coordinator workers, statistics aggregation
- **Credentials**: `REDIS_DATA_COORDINATOR_PASSWORD`

### 4. **api** - FastAPI Endpoints
- **Access**: Same as coordinator
- **Keys**: `~blazing:*`
- **Usage**: REST API endpoints
- **Credentials**: `REDIS_DATA_API_PASSWORD`

---

## 🧪 Testing & Verification

### Test 1: Multi-Tenant Isolation

```python
# Tenant A stores data
from blazing_service.data_access.app_context import set_app_id
from blazing_executor.data_fetching.redis_client import store_to_address

set_app_id("tenant-a")
address_a = await store_to_address({"secret": "data"}, "key-123")
# Returns: "RedisIndirect|tenant-a|key-123"

# Tenant B tries to access
set_app_id("tenant-b")
result = await fetch_from_address(address_a)
# Raises: PermissionError: Storage address app_id 'tenant-a' does not match current context app_id 'tenant-b'
```

### Test 2: ACL Command Restrictions

```bash
# Executor cannot run FLUSHDB
docker exec blazing-executor redis-cli \
  -u executor \
  -a "$REDIS_DATA_EXECUTOR_PASSWORD" \
  FLUSHDB
# Expected: (error) NOPERM

# Admin CAN run FLUSHDB
docker exec blazing-redis-data redis-cli \
  -u admin \
  -a "$REDIS_ADMIN_PASSWORD" \
  FLUSHDB
# Expected: OK
```

### Test 3: Password Authentication

```bash
# No password = connection refused
docker exec blazing-redis-data redis-cli PING
# Expected: (error) NOAUTH Authentication required

# Correct password = success
docker exec blazing-redis-data redis-cli \
  -u executor \
  -a "$REDIS_DATA_EXECUTOR_PASSWORD" \
  PING
# Expected: PONG
```

---

## 🚨 Security Warnings

### ⚠️ Password Storage
- **NEVER commit** `.env.redis-passwords` to git
- File is in `.gitignore` ✅
- File permissions: 600 (owner read/write only) ✅
- Rotate passwords regularly in production

### ⚠️ Multi-Tenant Isolation
- ACL allows cross-app_id key access at **Redis level** (e.g., `~blazing:*:...`)
- **Application layer** enforces app_id validation (redis_client.py:271)
- This design allows coordinator to access all tenants for statistics/monitoring
- Executor is restricted by validation in `fetch_from_address()`

### ⚠️ Data Loss Risk
- Restarting redis-data with ACL **DELETES ALL DATA** (no persistence configured)
- For production: Enable AOF (`--appendonly yes`) or RDB snapshots
- Always backup before ACL changes

---

## 🔧 Troubleshooting

### Issue: Services Can't Connect to Redis-Data

**Symptoms:**
```
redis.exceptions.ConnectionError: Error connecting to redis-data:6379
```

**Fix:**
```bash
# Check if password env vars are set
echo $REDIS_DATA_EXECUTOR_PASSWORD

# Source password file
source .env.redis-passwords

# Restart services
docker-compose restart executor coordinator api
```

### Issue: ACL Permission Denied

**Symptoms:**
```
(error) NOPERM this user has no permissions to run the 'hget' command
```

**Fix:**
```bash
# Check ACL configuration
docker exec blazing-redis-data redis-cli \
  -u admin \
  -a "$REDIS_ADMIN_PASSWORD" \
  ACL LIST

# Verify user permissions
docker exec blazing-redis-data redis-cli \
  -u admin \
  -a "$REDIS_ADMIN_PASSWORD" \
  ACL GETUSER executor
```

### Issue: Cross-Tenant Access Denied

**Symptoms:**
```
PermissionError: Storage address app_id 'tenant-a' does not match current context app_id 'tenant-b'
```

**This is EXPECTED behavior** - multi-tenant isolation is working correctly!

---

## 📊 Security Audit Checklist

- [x] Multi-tenant key isolation implemented
- [x] Cross-tenant validation prevents unauthorized access
- [x] ACL users created with least-privilege access
- [x] Dangerous commands blocked (FLUSHDB, CONFIG, SHUTDOWN)
- [x] Password authentication required
- [x] Passwords are strong (32 characters)
- [x] Password file in .gitignore
- [x] 17 security tests passing
- [x] All services updated with ACL credentials
- [ ] Production: Enable AOF/RDB persistence
- [ ] Production: Rotate passwords regularly
- [ ] Production: Monitor ACL violations
- [ ] Production: Set up alerting for failed auth attempts

---

## 📝 Files Modified

### New Files Created ✅
- `docker/redis-data-acl.conf` - ACL user definitions
- `docker/redis-data-entrypoint.sh` - Password injection script
- `docker/generate-redis-passwords.sh` - Password generator
- `.env.redis-passwords` - Generated passwords (gitignored)
- `tests/test_redis_data_security.py` - Security test suite
- `docs/redis-data-security-deployment.md` - This guide

### Modified Files ✅
- `src/blazing_executor/data_fetching/redis_client.py` - Multi-tenant isolation
- `docker-compose.yml` - ACL configuration + passwords
- `.gitignore` - Added `.env.redis-passwords`

---

## 🎯 Next Steps (Optional Enhancements)

### Phase 3: TLS Encryption (Future)
- Redis SSL/TLS for encrypted connections
- Certificate-based authentication
- Estimated effort: 4-6 hours

### Phase 4: Monitoring & Alerting (Future)
- RedisInsight dashboards for ACL violations
- Prometheus metrics for auth failures
- Estimated effort: 3-4 hours

### Phase 5: Rate Limiting (Future)
- Per-user connection limits
- Command throttling
- Estimated effort: 2-3 hours

---

**Deployment Status**: ✅ READY FOR PRODUCTION (after testing)

For questions or issues, see [docs/redis-data-security-plan.md](redis-data-security-plan.md)
