# Blazing Multi-Region Orchestrator Architecture

**Spanner as API Orchestrator for Regional Blazing Clusters**

## Overview

This architecture enables global, multi-region Blazing deployments while keeping each region's Blazing instance completely standalone and unchanged. Spanner acts as a lightweight **API orchestrator** that routes requests to regional Blazing APIs, tracks unit assignments, and handles failover.

### Key Principle

**"Unit = Atomic Regional Execution"**
- Each unit executes entirely within one region
- Inter-station data transfers stay local (Arrow Flight within region)
- Only initial submission and final result retrieval cross regions
- Massive cost & performance benefits from data locality

## Architecture Diagram

```
┌──────────────────────────────────────────────────┐
│  Client                                           │
│  - Submits units via Orchestrator API            │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│  Spanner Orchestrator (Lightweight Gateway)      │
│  - Tracks: unit_id → region mapping              │
│  - Routes: Forwards to regional Blazing APIs     │
│  - Health: GET /v1/health on each region         │
│  - Failover: Resubmit to different region        │
└──────────────┬────────────┬───────────────┬──────┘
               │            │               │
        ┌──────▼────┐ ┌────▼─────┐  ┌─────▼──────┐
        │us-central1│ │europe-west│ │asia-east1  │
        │Blazing API│ │Blazing API│ │Blazing API │
        └──────┬────┘ └────┬─────┘  └─────┬──────┘
               │            │               │
        ┌──────▼────────────▼───────────────▼──────┐
        │  Each region: Standalone Blazing          │
        │  - Redis cluster                          │
        │  - Coordinator + Workers                      │
        │  - FastAPI server (EXISTING!)             │
        │  - Worker mix optimization                │
        │  - btop monitoring                        │
        └───────────────────────────────────────────┘
```

## How It Works

### 1. Unit Submission

**Client → Orchestrator**:
```python
POST https://orchestrator.blazing.io/v1/jobs
{
  "route": "portfolio_optimization",
  "args": {"symbols": ["AAPL", "GOOGL"]},
  "region_hint": "us-central1"  # Optional
}
```

**Orchestrator Logic**:
```python
# 1. Select target region (load-based, affinity, or hint)
region = assign_region(args, region_hint)

# 2. Store mapping in Spanner
await spanner.insert(global_units, {
    "unit_id": unit_id,
    "region": region,
    "status": "SUBMITTED"
})

# 3. Forward to regional Blazing API (EXISTING ENDPOINT!)
response = await httpx.post(
    f"https://{region}-blazing.io/v1/jobs",
    headers={"Authorization": f"Bearer {region_token}"},
    json={"route": route, "args": args}
)

regional_unit_id = response.json()["job_id"]

# 4. Update mapping
await spanner.update({
    "unit_id": unit_id,
    "regional_unit_id": regional_unit_id,
    "status": "PROCESSING"
})

return {"unit_id": unit_id, "region": region}
```

### 2. Result Retrieval

**Client → Orchestrator**:
```python
GET https://orchestrator.blazing.io/v1/jobs/{unit_id}
```

**Orchestrator Logic**:
```python
# 1. Look up region from Spanner
unit = await spanner.get(unit_id)

# 2. Forward to regional API (EXISTING ENDPOINT!)
response = await httpx.get(
    f"https://{unit.region}-blazing.io/v1/jobs/{unit.regional_unit_id}",
    headers={"Authorization": f"Bearer {region_token}"}
)

return response.json()
```

### 3. Health Checks

**Orchestrator Health Loop**:
```python
async def health_check_loop():
    while True:
        for region in REGIONS:
            try:
                response = await httpx.get(
                    f"https://{region}-blazing.io/v1/health",
                    timeout=5.0
                )
                if response.status_code == 200:
                    mark_healthy(region)
                else:
                    mark_unhealthy(region)
            except Exception:
                mark_unhealthy(region)

        await asyncio.sleep(10)  # Check every 10s
```

### 4. Automatic Failover

**Scenario**: Region goes down while unit is processing

```python
async def failover_monitor():
    while True:
        # Find units in unhealthy regions
        stuck_units = await spanner.query(
            "SELECT * FROM global_units "
            "WHERE status = 'PROCESSING' "
            "AND region IN (SELECT region FROM region_health WHERE status = 'UNHEALTHY')"
        )

        for unit in stuck_units:
            # Cancel in old region (best effort)
            try:
                await httpx.delete(
                    f"https://{unit.region}-blazing.io/v1/jobs/{unit.regional_unit_id}"
                )
            except:
                pass  # Region is down anyway

            # Resubmit to healthy region
            new_region = select_healthy_region()
            response = await httpx.post(
                f"https://{new_region}-blazing.io/v1/jobs",
                json={"route": unit.route, "args": unit.args}
            )

            # Update mapping
            await spanner.update({
                "unit_id": unit.unit_id,
                "region": new_region,
                "regional_unit_id": response.json()["job_id"],
                "failover_count": unit.failover_count + 1
            })

        await asyncio.sleep(30)
```

## Regional Blazing (Unchanged)

Each region runs **completely standalone Blazing** with:
- ✅ Existing Redis cluster
- ✅ Existing Coordinator + worker mix optimizer
- ✅ Existing FastAPI server
- ✅ Existing btop monitoring (now via API!)
- ✅ **ZERO code changes to core Blazing**

**Only addition needed**: Health endpoint (20 LOC)

```python
# In server.py
@app.get("/v1/health")
async def health_check():
    """Health check for orchestrator monitoring."""
    try:
        # Check Redis
        await get_redis().ping()

        # Check if Coordinator is running
        foremen = await CoordinatorDAO.find().all()
        active_foremen = [f for f in foremen if f.status == "RUNNING"]

        return {
            "status": "healthy",
            "redis": "connected",
            "foremen": len(active_foremen),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(503, f"Unhealthy: {e}")
```

## Spanner Orchestrator Service

### Minimal FastAPI Gateway (~500 lines)

**orchestrator/main.py**:
```python
from fastapi import FastAPI, HTTPException
import httpx
from google.cloud import spanner

app = FastAPI()

REGIONS = {
    "us-central1": "https://us-central1-blazing.io",
    "europe-west1": "https://europe-west1-blazing.io",
    "asia-east1": "https://asia-east1-blazing.io"
}

@app.post("/v1/jobs")
async def submit_unit(request: JobRequest):
    """Forward unit submission to regional Blazing API."""
    region = assign_region(request.args, request.region_hint)

    # Store in Spanner
    unit_id = generate_id()
    await spanner.execute_update(
        "INSERT INTO global_units (unit_id, region, status, route, args) "
        "VALUES (@id, @region, 'SUBMITTED', @route, @args)",
        params={"id": unit_id, "region": region, "route": request.route, "args": request.args}
    )

    # Forward to regional API
    try:
        response = await httpx.post(
            f"{REGIONS[region]}/v1/jobs",
            headers={"Authorization": f"Bearer {get_region_token(region)}"},
            json={"route": request.route, "args": request.args},
            timeout=30.0
        )
        response.raise_for_status()
        regional_unit_id = response.json()["job_id"]

        # Update with regional ID
        await spanner.execute_update(
            "UPDATE global_units SET regional_unit_id = @rid, status = 'PROCESSING' "
            "WHERE unit_id = @id",
            params={"rid": regional_unit_id, "id": unit_id}
        )

        return {"unit_id": unit_id, "region": region}
    except Exception as e:
        await spanner.execute_update(
            "UPDATE global_units SET status = 'FAILED', error = @err WHERE unit_id = @id",
            params={"err": str(e), "id": unit_id}
        )
        raise HTTPException(500, f"Failed to submit to region {region}: {e}")

@app.get("/v1/jobs/{unit_id}")
async def get_result(unit_id: str):
    """Proxy result retrieval to regional API."""
    row = await spanner.execute_sql(
        "SELECT region, regional_unit_id, status FROM global_units WHERE unit_id = @id",
        params={"id": unit_id}
    ).one()

    if not row:
        raise HTTPException(404, "Unit not found")

    region, regional_id, status = row

    if status == "FAILED":
        return {"status": "FAILED", "error": "Unit failed"}

    # Forward to regional API
    response = await httpx.get(
        f"{REGIONS[region]}/v1/jobs/{regional_id}",
        headers={"Authorization": f"Bearer {get_region_token(region)}"},
        timeout=10.0
    )

    return response.json()

@app.get("/v1/health")
async def health():
    """Aggregate health of all regions."""
    health_status = {}
    for region, url in REGIONS.items():
        try:
            response = await httpx.get(f"{url}/v1/health", timeout=3.0)
            health_status[region] = "healthy" if response.status_code == 200 else "unhealthy"
        except:
            health_status[region] = "unreachable"

    return {"orchestrator": "healthy", "regions": health_status}
```

## Spanner Schema

### Simple 2-Table Design

```sql
-- Global unit tracking
CREATE TABLE global_units (
  unit_id STRING(36) NOT NULL,
  region STRING(50) NOT NULL,
  regional_unit_id STRING(36),  -- ID in the regional Blazing
  route STRING(100) NOT NULL,
  args JSON,
  status STRING(20) NOT NULL,  -- SUBMITTED, PROCESSING, DONE, FAILED
  submitted_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  error STRING(MAX),
  failover_count INT64 DEFAULT 0
) PRIMARY KEY (unit_id);

-- Region health tracking
CREATE TABLE region_health (
  region STRING(50) NOT NULL,
  status STRING(20) NOT NULL,  -- HEALTHY, UNHEALTHY
  last_check TIMESTAMP NOT NULL,
  last_error STRING(MAX)
) PRIMARY KEY (region);
```

## Data Locality Strategy

### Why It Matters

**Example**: 3-station pipeline with 100MB intermediate data

**Without regional isolation (❌ Bad)**:
```
Station 1 (us-central1) → 100MB → GCS
Station 2 (europe-west1) ← 100MB download ($12 egress) → 100MB → GCS
Station 3 (us-central1) ← 100MB download ($12 egress)

Total egress: $24 per unit
Latency: ~10s of cross-region transfers
```

**With regional isolation (✅ Good)**:
```
Station 1 (us-central1) → 100MB → local Arrow Flight (free, <100ms)
Station 2 (us-central1) ← 100MB local → 100MB → local Arrow Flight
Station 3 (us-central1) ← 100MB local

Total egress: $0 (all local)
Latency: <1s of local transfers
```

**At 1000 units/day**: $24k/year saved + massive latency improvement

### Unit Assignment Strategy

```python
async def assign_region(args: Dict, region_hint: Optional[str]) -> str:
    """Assign unit to region considering data locality."""

    # Strategy 1: Data locality (where is input data?)
    if "dataframe_ref" in args:
        ref = args["dataframe_ref"]
        if ref.startswith("gs://blazing-us-central1/"):
            return "us-central1"

    # Strategy 2: Chain locality (where did parent execute?)
    if "depends_on_unit" in args:
        parent_unit = await spanner.get_unit(args["depends_on_unit"])
        return parent_unit.region  # Keep in same region!

    # Strategy 3: Client hint
    if region_hint:
        return region_hint

    # Strategy 4: Load balancing (fallback)
    return await get_least_loaded_region()
```

## Client Experience

### Same API, Works Everywhere

**Standalone Mode** (single region):
```python
client = BlazingClient("https://my-blazing.io", token)
unit = await client.submit("my_route", args)
result = await client.get_result(unit.id)
```

**Federated Mode** (multi-region):
```python
client = BlazingClient("https://orchestrator.blazing.io", token)
unit = await client.submit("my_route", args)  # Same API!
result = await client.get_result(unit.id)     # Same API!
```

**Zero client code changes!** Just point to orchestrator URL.

## Monitoring

### Regional btop (Existing)

```bash
# Monitor specific region
btop --api-url https://us-central1-blazing.io --api-token $TOKEN

# Shows:
# - Worker mix for that region
# - Queue depths
# - Throughput
# - Worker mix decisions
```

### Global Dashboard (New)

```python
class GlobalBtop:
    async def render():
        # Fetch from Spanner
        global_stats = await spanner.query(
            "SELECT region, status, COUNT(*) "
            "FROM global_units GROUP BY region, status"
        )

        # Fetch regional worker metrics via API
        regional_metrics = await asyncio.gather(*[
            httpx.get(f"{url}/v1/metrics/worker-mix")
            for url in REGIONS.values()
        ])

        # Render combined dashboard
        # - Total units per region
        # - Regional health
        # - Aggregated worker mix stats
```

## Implementation Plan

### Phase 1: Orchestrator Core (2-3 days)

**Components**:
1. FastAPI orchestrator service (~500 LOC)
2. Spanner schema (2 tables)
3. Health check endpoint in Blazing server.py (~20 LOC)
4. Unit tests for orchestrator

**Deliverable**: Working orchestrator that routes to 1 region

### Phase 2: Multi-Region Support (1-2 days)

**Components**:
1. Region assignment logic (load-based, affinity, hints)
2. Health check loop
3. Failover monitor
4. Multi-region integration tests

**Deliverable**: Orchestrator managing 2+ regions with failover

### Phase 3: Production Readiness (1-2 days)

**Components**:
1. Authentication/authorization
2. Rate limiting
3. Observability (metrics, tracing)
4. Global monitoring dashboard
5. Deployment documentation

**Deliverable**: Production-ready orchestrator

**Total Timeline**: 4-7 days

## Cost Analysis

### Spanner Costs

**Baseline** (eur3 configuration):
- 1000 processing units ≈ $2,400/month
- Writes: ~$0.50/million mutations
- Reads: Free

**Optimization**:
- Batch health checks (1 write per 10 regions)
- TTL-based cleanup (delete old units after 7 days)
- Cache frequent queries in orchestrator memory
- Use secondary indexes sparingly

**Estimated monthly cost**: $2,500-3,000 at 10k units/day

### Regional Blazing Costs

**Per region** (unchanged):
- Redis: $50-200/month (managed)
- Compute: Based on actual usage
- Arrow Flight: Free (local transfers)

**With data locality**:
- Cross-region egress: ~$0 (vs $60k/year without isolation)
- Storage: GCS Standard ($0.02/GB/month)

## Benefits Summary

### ✅ Zero Changes to Blazing Core
- Each region runs existing code
- No new dependencies
- No performance penalty
- All existing features work

### ✅ Federation is Optional
```python
# Standalone (current)
Blazing(...) → Works as-is

# Federated (new)
Blazing(...) + Orchestrator → Enhanced capabilities
```

### ✅ Regional Data Locality
- Units execute entirely within one region
- Inter-station transfers stay local (Arrow Flight)
- Massive cost & latency savings

### ✅ Automatic Failover
- Health checks via `/v1/health`
- Automatic resubmission to healthy regions
- No data loss (idempotent station functions)

### ✅ Simple Architecture
- Orchestrator is just an API proxy (~500 LOC)
- Spanner schema is minimal (2 tables)
- Easy to understand and maintain

### ✅ Easy Migration
```
Phase 1: Deploy standalone Blazing to multiple regions
Phase 2: Deploy orchestrator (points to regional APIs)
Phase 3: Update clients to use orchestrator URL
```

No downtime, gradual rollout.

## Alternatives Considered

### ❌ Data Layer Integration (Rejected)
- **Approach**: Spanner as primary database, replace Redis
- **Why rejected**: Massive refactoring, performance impact, high risk

### ❌ Shared Redis Cluster (Rejected)
- **Approach**: Multi-region Redis with cross-region replication
- **Why rejected**: Complex, expensive, weak consistency

### ✅ API Orchestrator (Selected)
- **Approach**: Spanner routes to regional Blazing APIs
- **Why selected**: Simple, no Blazing changes, leverages existing API

## Production Hardening

The orchestrator implements production-grade reliability patterns to handle failure modes at scale.

### 1. Idempotency End-to-End

**Problem**: Client retry or orchestrator crash can cause duplicate submissions.

**Solution**: Idempotency keys at all layers.

```python
# Client → Orchestrator
POST /v1/jobs
Headers: Idempotency-Key: {client-generated-key}

# Orchestrator checks Spanner
existing = spanner.get_by_idempotency_key(key)
if existing: return existing

# Orchestrator → Regional API (forwards same key)
POST https://region/v1/jobs
Headers: Idempotency-Key: {same-key}

# Regional API checks Redis
job_id = redis.get(f"idem:{key}")
if job_id: return existing_job(job_id)
```

**Result**: Safe retries at all layers, no duplicate execution.

### 2. Dispatch Leases

**Problem**: Multiple orchestrator instances can dispatch the same unit concurrently.

**Solution**: Lease-based dispatch with atomic claim.

```python
# Claim lease (atomic transaction)
claimed = spanner.update(
    "UPDATE global_units "
    "SET status='DISPATCHING', lease_owner=@me, lease_until=@exp "
    "WHERE unit_id=@id AND (status='SUBMITTED' OR lease_until < @now)"
)

if not claimed:
    return  # Another instance claimed it

# Submit to region
regional_id = await region_client.submit(...)

# Release lease, move to PROCESSING
spanner.update("SET status='PROCESSING', regional_unit_id=@rid WHERE unit_id=@id")
```

**Result**: No double-dispatch, even with multiple orchestrator instances.

### 3. Mapping Recovery

**Problem**: Submit succeeds but orchestrator crashes before writing `regional_unit_id`.

**Solution**: Use idempotency key to recover mapping.

```python
# On status query, if regional_unit_id is missing:
if not unit.regional_unit_id:
    # Query regional API by idempotency key
    regional_id = await region.lookup_by_idem_key(unit.idempotency_key)
    if regional_id:
        spanner.set_regional_id(unit_id, regional_id)
```

**Result**: No lost mappings, graceful recovery from partial failures.

### 4. Circuit Breakers

**Problem**: Failing region causes cascading failures.

**Solution**: Circuit breaker per region with state machine.

```python
class CircuitBreaker:
    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= threshold:
            self.state = OPEN  # Stop sending requests

    def is_open(self):
        if self.state == OPEN and time_since_last_failure > recovery_timeout:
            self.state = HALF_OPEN  # Try again
        return self.state == OPEN
```

**States**: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing) → CLOSED

**Result**: Fault isolation, fast fail for unhealthy regions.

### 5. Brownout Detection

**Problem**: Region is slow but not failing (HTTP 200 with high latency).

**Solution**: Track p95 latency and error rate, three-tier health model.

```python
def determine_status(p95_ms, error_rate):
    if error_rate >= 0.5:
        return "UNHEALTHY"  # No new jobs
    elif p95_ms >= 1000:
        return "DEGRADED"   # Lower weight in load balancing
    else:
        return "HEALTHY"    # Full weight
```

**Result**: Routes away from degraded regions before they fail completely.

### 6. Automatic Failover

**Problem**: Region fails while unit is processing.

**Solution**: Failover monitor with lease-based claiming.

```python
async def failover_loop():
    # Find units in PROCESSING state in UNHEALTHY regions
    stuck_units = spanner.query(
        "SELECT * FROM global_units u "
        "JOIN region_health r ON u.region = r.region "
        "WHERE u.status='PROCESSING' AND r.status='UNHEALTHY'"
    )

    for unit in stuck_units:
        # Check max failovers (prevent infinite loops)
        if unit.failover_count >= 2:
            mark_failed(unit, "MAX_FAILOVERS_EXCEEDED")
            continue

        # Claim lease to prevent concurrent failover
        if not claim_dispatch_lease(unit.unit_id):
            continue  # Another instance handling it

        # Cancel in old region (best effort)
        try:
            await old_region.cancel_job(unit.regional_unit_id)
        except:
            pass  # Region is down anyway

        # Resubmit to healthy region
        new_region = select_healthy_region()
        regional_id = await new_region.submit(unit.route, unit.args, unit.idempotency_key)

        # Update mapping
        spanner.update("SET regional_unit_id=@rid, region=@r, failover_count+=1")
```

**Result**: Automatic recovery from regional outages, max 2 failovers per unit.

### 7. Capacity-Aware Routing

**Problem**: Hot clients can saturate a single region.

**Solution**: Track inflight count, enforce per-region caps.

```python
def assign_region(args, hint):
    # Strategy 1: Data locality
    if "dataframe_ref" in args and "gs://blazing-us-central1/" in args["dataframe_ref"]:
        return "us-central1"

    # Strategy 2: Chain locality (same region as parent)
    if "depends_on_unit" in args:
        parent_region = spanner.get_unit(args["depends_on_unit"]).region
        if is_available(parent_region):
            return parent_region

    # Strategy 3: Load balancing with capacity limits
    regions = get_healthy_regions()
    weights = [
        (100 if r.status=="HEALTHY" else 30) *  # Deweight DEGRADED
        (1.0 - r.inflight/MAX_INFLIGHT)         # Deweight loaded
        for r in regions
        if r.inflight < MAX_INFLIGHT           # Hard cap
    ]
    return weighted_random(regions, weights)
```

**Result**: Even load distribution, prevents single-region saturation.

### 8. Request Signing

**Problem**: Replay attacks if orchestrator ↔ region traffic is intercepted.

**Solution**: HMAC signing with nonce + timestamp.

```python
def sign_request(method, path, body, nonce, timestamp):
    message = f"{method}|{path}|{body}|{nonce}|{timestamp}"
    return hmac.sha256(secret, message).hexdigest()

# Orchestrator adds headers
headers = {
    "Authorization": f"Bearer {token}",
    "x-request-id": uuid4(),
    "x-nonce": uuid4(),
    "x-timestamp": utcnow().isoformat(),
    "x-signature": sign_request(...)
}

# Regional API verifies
expected_sig = sign_request(method, path, body, nonce, timestamp)
if headers["x-signature"] != expected_sig:
    return 401  # Invalid signature
```

**Result**: Replay protection, request authenticity.

### Summary of Hardening

| Pattern | Prevents | Cost (LOC) |
|---------|----------|-----------|
| Idempotency keys | Duplicate execution | ~50 |
| Dispatch leases | Double-dispatch | ~80 |
| Mapping recovery | Lost mappings | ~30 |
| Circuit breakers | Cascading failures | ~100 |
| Brownout detection | Slow degradation | ~80 |
| Automatic failover | Regional outages | ~120 |
| Capacity-aware routing | Region saturation | ~80 |
| Request signing | Replay attacks | ~50 |

**Total**: ~590 LOC of production hardening
**Result**: Production-ready orchestrator that handles all common failure modes

## Implementation Status

✅ **Phase 1: Regional Blazing Updates**
- Added `/v1/health` endpoint (20 LOC)
- Added idempotency support to `/v1/jobs` (50 LOC)

✅ **Phase 2: Orchestrator Core**
- Spanner schema with leases and brownout tracking
- DAO layer with atomic lease acquisition (~200 LOC)
- Regional HTTP client with circuit breakers (~200 LOC)
- Region assignment with locality and capacity awareness (~180 LOC)
- Health monitoring with brownout detection (~150 LOC)
- Failover monitor with lease-based claiming (~120 LOC)
- FastAPI application with all endpoints (~300 LOC)

**Total**: ~1,220 LOC (orchestrator + regional updates)

## Next Steps

1. ✅ Add `/v1/health` endpoint to Blazing
2. ✅ Add idempotency support to Blazing
3. ✅ Build orchestrator service
4. ⏳ Write unit tests for orchestrator
5. ⏳ Write integration tests (orchestrator + 2 regions)
6. ⏳ Deploy to staging environment
7. ⏳ Run chaos tests (kill region during PROCESSING)
8. ⏳ Deploy to production

Ready for testing and deployment!
