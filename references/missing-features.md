# Blazing: Missing Features Reference

This document catalogs features that Modal.com offers but Blazing currently lacks, with proposed APIs and implementation notes.

---

## Priority 1: Critical Infrastructure

### 1. GPU Support

**Status:** Not Implemented

**Modal API:**
```python
@app.function(gpu="A100")
def train(): ...

@app.function(gpu="H100:4")  # Multi-GPU
def distributed_train(): ...

@app.function(gpu=["H100", "A100-80GB:2"])  # Fallback
def flexible_train(): ...
```

**Proposed Blazing API:**
```python
@app.step(gpu="A100")
async def train(data): ...

@app.step(gpu="H100", gpu_count=4)
async def distributed_train(data): ...

@app.step(gpu=["H100", "A100-80GB"], gpu_count=2)
async def flexible_train(data): ...
```

**Implementation Notes:**
- Add `gpu`, `gpu_count`, `gpu_memory` parameters to `@app.step()` decorator
- Extend worker types: `GPU_BLOCKING`, `GPU_NON_BLOCKING`
- Blazing Core integration for GPU node scheduling on GKE/Akash
- GPU resource tracking in WorkerThreadDAO
- NVIDIA runtime configuration in executor containers

**Supported GPU Types:**
| GPU | VRAM | Use Case |
|-----|------|----------|
| T4 | 16 GB | Inference, fine-tuning |
| L4 | 24 GB | Inference, training |
| A10 | 24 GB | Inference, training |
| A100-40GB | 40 GB | Training, large models |
| A100-80GB | 80 GB | Large model training |
| L40S | 48 GB | Balanced cost/performance |
| H100 | 80 GB | High-performance training |
| H200 | 141 GB | Largest models |

**Files to Create/Modify:**
- `src/blazing/gpu.py` - GPU configuration classes
- `src/blazing/blazing.py` - Add GPU params to step decorator
- `src/blazing_service/engine/runtime.py` - GPU worker types
- `src/blazing_service/worker/gpu_manager.py` - GPU resource management

---

### 2. Volumes (Persistent Storage)

**Status:** Not Implemented

**Modal API:**
```python
vol = modal.Volume.from_name("my-volume", create_if_missing=True)

@app.function(volumes={"/data": vol})
def process():
    with open("/data/file.txt", "w") as f:
        f.write("hello")
    vol.commit()  # Persist changes
```

**Proposed Blazing API (Connector-Based - Services Only):**

Blazing uses a **connector-based architecture** for Volumes, treating storage as a standardized connector just like databases, caches, and external APIs. This provides:
- Consistent pattern across all external resources
- Built-in tenant isolation via connector layer
- Works with existing `sandboxed=True` → service bridge architecture
- Swappable backends (local filesystem for dev, SeaweedFS for production)

**IMPORTANT: Volumes are ONLY accessible through Services, not directly in Steps.**

This is the same security model as databases - sandboxed user code cannot directly access storage. Instead, it calls service methods which run on trusted workers with real I/O access.

```python
# Define volume as a connector in your service
from blazing.local import VolumeConnector
from blazing import Volume

@app.service(connectors={'models': VolumeConnector(Volume.persisted("ml-models"))})
class ModelService(BaseService):
    def __init__(self, connectors):
        self.db = connectors['postgres']       # SQLAlchemyConnector
        self.cache = connectors['redis']       # RedisConnector
        self.models = connectors['models']     # VolumeConnector  <-- Same pattern!

    async def load_model(self, name: str) -> bytes:
        """Load model weights from volume."""
        return await self.models.get_file(f"/weights/{name}.pt")

    async def save_checkpoint(self, name: str, data: bytes) -> None:
        """Save training checkpoint."""
        await self.models.put_file(f"/checkpoints/{name}.pt", data)
        await self.models.commit()  # Flush to durable storage

    async def list_models(self) -> list[str]:
        """List available models."""
        files = await self.models.listdir("/weights")
        return [f.replace(".pt", "") for f in files if f.endswith(".pt")]
```

**Sandboxed Steps Access Volumes via Service Calls:**
```python
@app.step(sandboxed=True)
async def train_model(data: dict, services=None):
    """Sandboxed step that uses volume through service."""
    # Load model weights via service (runs on trusted worker)
    weights = await services['ModelService'].load_model("base-model")

    # ... do training in sandbox ...
    new_weights = train(weights, data)

    # Save checkpoint via service (runs on trusted worker)
    await services['ModelService'].save_checkpoint("checkpoint-1", new_weights)

    return {"status": "trained"}
```

**Why No `@app.step(volumes={...})` Decorator?**

Unlike Modal, Blazing does NOT support direct volume access in steps because:
1. **Security**: Sandboxed steps (Pyodide WASM) cannot perform real I/O
2. **Consistency**: All external resources (DB, cache, storage) use the same service pattern
3. **Testability**: Services with connectors are easier to mock in tests
4. **Multi-tenancy**: Connector layer handles tenant isolation automatically

**VolumeConnector Interface:**
```python
class VolumeConnector(BaseConnector):
    """S3/SeaweedFS volume connector with Modal-compatible semantics."""

    # File operations
    async def get_file(self, path: str) -> bytes: ...
    async def put_file(self, path: str, data: bytes) -> None: ...
    async def remove(self, path: str) -> None: ...
    async def listdir(self, path: str = "/") -> List[str]: ...
    async def exists(self, path: str) -> bool: ...

    # Directory operations
    async def put_directory(self, local_path: str, remote_path: str) -> None: ...
    async def get_directory(self, remote_path: str, local_path: str) -> None: ...

    # Consistency operations (matching Modal)
    async def commit(self) -> None: ...   # Flush write buffer to storage
    async def reload(self) -> None: ...   # Invalidate cache, fetch latest

    # Metadata
    async def stat(self, path: str) -> FileStat: ...
    async def get_size(self) -> int: ...  # Total volume size in bytes
```

**Why Connector Pattern (No Decorator Sugar)?**

| Approach | Pros | Cons |
|----------|------|------|
| **Connector-only (Blazing)** | Consistent with DB/cache connectors; works with sandbox→service bridge; testable; secure | Slightly more verbose than Modal |
| **Decorator-only (Modal)** | Less boilerplate | Breaks sandbox security model; two patterns for external resources |

**Blazing's Approach:**
1. **Core**: VolumeConnector implements the interface (swappable backends)
2. **Services**: Services declare volume connectors like any other connector
3. **Sandboxed Steps**: Access volumes ONLY through service method calls (trusted execution)

---

## Modal Volumes vs Blazing Volumes: Feature Parity Analysis

### Modal Volumes Key Specifications

| Specification | Modal v1 | Modal v2 | Blazing (SeaweedFS) |
|---------------|----------|----------|---------------------|
| **Bandwidth** | 2.5 GB/s target | 2.5 GB/s target | ✅ 2+ GB/s (network-limited) |
| **Max file size** | ~50 GB | 1 TiB | ✅ Unlimited (SeaweedFS handles TB+ files) |
| **Max files per volume** | ~500,000 inodes | Unlimited | ✅ Billions (optimized for this) |
| **Max files per directory** | ~500,000 | 32,768 | ✅ Unlimited (Filer handles this) |
| **Concurrent readers** | Hundreds | Hundreds | ✅ Unlimited (S3 API is stateless) |
| **Concurrent writers (same file)** | ⚠️ Last-write-wins | ⚠️ Last-write-wins | ✅ Same (S3 semantics) |
| **Concurrent writers (diff files)** | Limited | Hundreds | ✅ Unlimited (S3 API) |
| **Hard links** | No | Yes | ✅ Yes (Filer supports) |
| **Consistency model** | Eventually consistent | Eventually consistent | ✅ Strong (configurable) |

### Feature Comparison

#### ✅ Full Parity Features

| Feature | Modal | Blazing (SeaweedFS) |
|---------|-------|---------------------|
| Persistent storage across runs | ✅ | ✅ |
| Mount to containers at any path | ✅ | ✅ (FUSE or CSI driver) |
| Upload/download files from client | ✅ | ✅ (S3 API) |
| Directory listing | ✅ | ✅ |
| Create/delete files and directories | ✅ | ✅ |
| Read-only and read-write modes | ✅ | ✅ |
| Multi-tenant isolation | ✅ | ✅ (bucket/prefix per tenant) |
| Encryption at rest | ✅ | ✅ (SeaweedFS supports) |

#### ✅ Blazing Advantages

| Feature | Modal | Blazing (SeaweedFS) |
|---------|-------|---------------------|
| **Strong consistency option** | No (eventually consistent only) | ✅ Configurable per-write |
| **Unlimited file count** | v1: 500K limit, v2: unlimited | ✅ Optimized for billions |
| **Larger files** | v2: 1 TiB max | ✅ No practical limit |
| **S3 API compatibility** | No (proprietary API) | ✅ Works with any S3 tool |
| **Self-hosted option** | No (cloud only) | ✅ Run on-prem or any cloud |
| **Erasure coding** | Unknown | ✅ Built-in, configurable |
| **Cross-region replication** | Unknown | ✅ Native support |

#### ⚠️ Features Requiring Implementation

| Feature | Modal | Blazing Implementation |
|---------|-------|------------------------|
| **commit()** | Explicit flush to durable storage | Implement as S3 sync with confirmation |
| **reload()** | Refresh view of remote changes | Implement as cache invalidation |
| **Background auto-commit** | Every ~5 seconds | Implement via background task |
| **Snapshot deletion guarantee** | HIPAA compliance | Implement via hard delete API |
| **Volume snapshots** | Point-in-time restore | Implement via S3 versioning |

---

### Modal's Consistency Model (Must Match)

Modal uses a **last-write-wins** model with eventual consistency:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Modal Consistency Model                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Container A                    Container B                      │
│  ───────────                    ───────────                      │
│  write("/data/x", "A")          write("/data/x", "B")           │
│        │                              │                          │
│        ▼                              ▼                          │
│  Local Write Buffer              Local Write Buffer              │
│        │                              │                          │
│        └──────────┬───────────────────┘                          │
│                   ▼                                              │
│         Background Commit (~5s)                                  │
│                   │                                              │
│                   ▼                                              │
│            Modal Storage                                         │
│         (Last write wins: "B")                                   │
│                                                                  │
│  Container C (after reload())                                    │
│  ─────────────────────────────                                   │
│  read("/data/x") → "B"                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Blazing Implementation:**
```python
class BlazingVolume:
    """Matches Modal's consistency model using SeaweedFS."""

    def __init__(self, name: str):
        self.name = name
        self._write_buffer: dict[str, bytes] = {}
        self._commit_task: asyncio.Task | None = None
        self._background_commit_interval = 5  # seconds

    async def write(self, path: str, data: bytes) -> None:
        """Buffer write locally (matches Modal behavior)."""
        self._write_buffer[path] = data
        # Start background commit if not running
        if self._commit_task is None:
            self._commit_task = asyncio.create_task(self._background_commit())

    async def commit(self) -> None:
        """Explicitly flush all buffered writes to storage."""
        for path, data in self._write_buffer.items():
            await self._s3_client.put_object(
                Bucket=self._bucket,
                Key=f"{self._tenant_id}/{self.name}/data{path}",
                Body=data
            )
        self._write_buffer.clear()

    async def reload(self) -> None:
        """Invalidate local cache, fetch latest from storage.

        WARNING: Like Modal, this makes the volume appear empty
        during the reload operation.
        """
        self._local_cache.clear()
        await self._sync_from_remote()

    async def _background_commit(self) -> None:
        """Auto-commit every N seconds (matches Modal)."""
        while self._write_buffer:
            await asyncio.sleep(self._background_commit_interval)
            await self.commit()
        self._commit_task = None
```

---

### Reload Behavior (Critical Modal Detail)

Modal documentation states:
> "WARNING: During reload, the volume will appear empty until the operation completes."

**Blazing must match this behavior:**
```python
async def reload(self) -> None:
    """Reload volume from remote storage.

    IMPORTANT: During reload, all reads will return empty/not found
    until the sync completes. This matches Modal's behavior.

    Use Case: When Container A writes files and commits, Container B
    calls reload() to see those new files.
    """
    # 1. Clear local cache/view
    self._invalidate_local_cache()

    # 2. Re-fetch metadata from SeaweedFS
    await self._fetch_remote_metadata()

    # 3. Optionally pre-warm cache for recently accessed files
    if self._cache_warming_enabled:
        await self._warm_cache()
```

---

### Implementation Notes

**Backend: SeaweedFS with S3 API**

SeaweedFS is the recommended storage backend for Blazing Volumes:
- S3-compatible API (works with boto3, s3fs)
- Optimized for billions of small-to-medium files
- Built-in replication and erasure coding
- Simpler to operate than MinIO or Ceph
- Supports FUSE mounting for direct filesystem access

```
Architecture:
┌─────────────────────────────────────────────────────────────────┐
│                         Blazing Volume                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Client SDK                     Executor Container              │
│  ───────────                    ──────────────────              │
│  vol.put_file() ──────┐         /data (FUSE mount)              │
│  vol.get_file() ──────┼────────► s3fs or weed mount             │
│  vol.commit()   ──────┘                                         │
│                                                                 │
│  Write Buffer (5s auto-commit)                                  │
│        │                                                        │
│        ▼                                                        │
│  ════════════════════════════════════════════════════════════   │
│                                                                 │
│  SeaweedFS Cluster                                              │
│  ─────────────────                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                         │
│  │ Master  │  │ Volume  │  │ Volume  │  (replicated)           │
│  │ Server  │  │ Server  │  │ Server  │                         │
│  └─────────┘  └─────────┘  └─────────┘                         │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────┐                                                    │
│  │  Filer  │ ◄── S3 API (port 8333)                            │
│  └─────────┘                                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Volume Types:**
| Type | Backend | Use Case |
|------|---------|----------|
| `persisted` | SeaweedFS | Model weights, datasets, checkpoints |
| `ephemeral` | tmpfs/emptyDir | Scratch space, temp files |
| `cached` | SeaweedFS + local SSD | Frequently accessed files |

**S3 Bucket Layout:**
```
blazing-volumes/
├── {tenant_id}/
│   ├── {volume_name}/
│   │   ├── .meta.json          # Volume metadata
│   │   ├── data/               # User files
│   │   │   ├── models/
│   │   │   │   └── v1.pt
│   │   │   └── datasets/
│   │   │       └── train.parquet
│   │   └── .snapshots/         # Point-in-time snapshots
│   │       ├── 2025-01-01T00:00:00/
│   │       └── 2025-01-02T00:00:00/
```

**Mounting in Executors:**
```yaml
# Kubernetes Pod spec
spec:
  containers:
  - name: executor
    volumeMounts:
    - name: blazing-vol
      mountPath: /data
  volumes:
  - name: blazing-vol
    csi:
      driver: seaweedfs-csi
      volumeAttributes:
        collection: "blazing-volumes"
        path: "{tenant_id}/{volume_name}/data"
```

**Commit/Reload Semantics (Matching Modal):**
- `commit()`: Flush local writes to SeaweedFS (sync, blocking)
- `reload()`: Invalidate local cache, volume appears empty during reload
- Auto-commit on container exit (required)
- Background sync every ~5 seconds (matching Modal)
- **Last-write-wins** for concurrent writes to same file

**Size Limits and Quotas:**
- Per-tenant storage quota (e.g., 100GB default)
- Per-volume size limit (configurable)
- File count limits (SeaweedFS handles billions efficiently)
- Bandwidth throttling per tenant

**Performance Targets (Matching Modal):**
- Target bandwidth: 2.5 GB/s
- Latency: <10ms for metadata operations
- Concurrent containers: 100s per volume

**Files to Create:**
- `src/blazing/volume.py` - Volume class and operations
- `src/blazing_service/storage/volume_manager.py` - Volume lifecycle
- `src/blazing_service/storage/seaweedfs_client.py` - SeaweedFS S3 client
- `src/blazing_service/data_access/volume_dao.py` - Volume metadata
- `docker/seaweedfs/` - SeaweedFS deployment configs

**Docker Compose (Development):**
```yaml
services:
  seaweedfs-master:
    image: chrislusf/seaweedfs:latest
    command: master -ip=seaweedfs-master -port=9333
    ports:
      - "9333:9333"

  seaweedfs-volume:
    image: chrislusf/seaweedfs:latest
    command: volume -mserver=seaweedfs-master:9333 -port=8080
    depends_on:
      - seaweedfs-master

  seaweedfs-filer:
    image: chrislusf/seaweedfs:latest
    command: filer -master=seaweedfs-master:9333 -s3 -s3.port=8333
    ports:
      - "8333:8333"  # S3 API
      - "8888:8888"  # Filer API
    depends_on:
      - seaweedfs-volume
```

**Client Usage:**
```python
import boto3

# SeaweedFS S3 client
s3 = boto3.client(
    's3',
    endpoint_url='http://seaweedfs-filer:8333',
    aws_access_key_id='any',
    aws_secret_access_key='any'
)

# Upload
s3.upload_file('local/model.pt', 'blazing-volumes', 'tenant/vol/data/model.pt')

# Download
s3.download_file('blazing-volumes', 'tenant/vol/data/model.pt', 'local/model.pt')
```

---

### Conclusion: SeaweedFS Feature Parity

**✅ YES - SeaweedFS can match Modal's Volume features:**

| Modal Feature | SeaweedFS Equivalent | Notes |
|---------------|---------------------|-------|
| High bandwidth (2.5 GB/s) | ✅ Network-limited throughput | SeaweedFS is I/O optimized |
| Millions of files | ✅ Billions of files | SeaweedFS's core strength |
| commit() / reload() | ✅ Implement in SDK | S3 PUT + cache invalidation |
| Last-write-wins | ✅ S3 default behavior | Matches Modal exactly |
| Background commits | ✅ Implement in SDK | 5-second timer |
| Container mounting | ✅ FUSE/CSI driver | `weed mount` or s3fs |
| Multi-tenant isolation | ✅ Bucket/prefix per tenant | Standard S3 pattern |

**⚠️ Implementation Required (SDK layer, not infrastructure):**
1. Write buffer with background commit
2. Reload with cache invalidation
3. Volume lifecycle management
4. Quota enforcement

**✅ Blazing Advantages Over Modal:**
- Self-hosted option (on-prem, any cloud)
- S3 API compatibility (use any S3 tool)
- Strong consistency option (per-write configurable)
- No file size limits (TB+ files supported)
- Cross-region replication built-in

---

### 3. Secrets Management

**Status:** Not Implemented

**Modal API:**
```python
@app.function(secrets=[modal.Secret.from_name("db-credentials")])
def query():
    conn = os.environ["DATABASE_URL"]

# Create from dict
secret = modal.Secret.from_dict({"API_KEY": "xxx"})

# Create from .env file
secret = modal.Secret.from_dotenv()
```

**Proposed Blazing API:**
```python
# Reference existing secret
@app.step(secrets=[blazing.Secret.from_name("db-credentials")])
async def query():
    conn = os.environ["DATABASE_URL"]

# Create secret programmatically
secret = blazing.Secret.from_dict({
    "DATABASE_URL": "postgres://...",
    "API_KEY": "sk-xxx"
})
await secret.save("my-secret")

# Create from .env file
secret = blazing.Secret.from_dotenv(".env.production")

# Create from environment variables (filter by prefix)
secret = blazing.Secret.from_env(prefix="MYAPP_")
```

**CLI Operations:**
```bash
# Create secret
blazing secret create db-credentials \
    DATABASE_URL=postgres://... \
    API_KEY=sk-xxx

# List secrets
blazing secret list

# Delete secret
blazing secret delete db-credentials

# View secret (masked)
blazing secret show db-credentials
```

**Implementation Notes:**
- Encrypted storage in Blazing Registry (AES-256-GCM)
- Per-tenant secret isolation via app_id
- Environment variable injection in executor containers
- Secret rotation support
- Audit logging for secret access

**Files to Create:**
- `src/blazing/secret.py` - Secret class
- `src/blazing_service/security/secrets_manager.py` - Encryption/storage
- `src/blazing/cli/secrets.py` - CLI commands

---

### 4. Cron/Scheduled Jobs

**Status:** Not Implemented

**Modal API:**
```python
@app.function(schedule=modal.Cron("0 * * * *"))
def hourly_job(): ...

@app.function(schedule=modal.Period(minutes=30))
def periodic_job(): ...
```

**Proposed Blazing API:**
```python
# Cron expression
@app.workflow(schedule=blazing.Cron("0 * * * *"))
async def hourly_report():
    ...

# Interval-based
@app.workflow(schedule=blazing.Period(minutes=30))
async def sync_data():
    ...

# Multiple schedules
@app.workflow(schedule=[
    blazing.Cron("0 9 * * 1-5"),  # Weekdays at 9am
    blazing.Cron("0 12 * * 6,0"),  # Weekends at noon
])
async def notifications():
    ...
```

**Schedule Objects:**
```python
# Cron with timezone
schedule = blazing.Cron(
    "0 9 * * *",
    timezone="America/New_York"
)

# Period with jitter (prevent thundering herd)
schedule = blazing.Period(
    hours=1,
    jitter_minutes=5  # Random delay 0-5 minutes
)
```

**Implementation Notes:**
- Scheduler service in Coordinator
- Cron expression parsing (croniter library)
- ScheduleDAO for schedule definitions
- Trigger queue for due jobs
- Timezone handling
- Execution history tracking
- Retry on failure

**Files to Create:**
- `src/blazing/schedule.py` - Cron, Period classes
- `src/blazing_service/scheduler/scheduler.py` - Scheduler service
- `src/blazing_service/scheduler/cron_parser.py` - Cron parsing
- `src/blazing_service/data_access/schedule_dao.py` - Schedule metadata

---

### 5. Distributed Data Structures

**Status:** Partial (internal Redis queues only)

**Modal API:**
```python
# Distributed dict
cache = modal.Dict.from_name("inference-cache")
cache["key"] = value
value = cache["key"]

# Distributed queue
queue = modal.Queue.from_name("job-queue")
queue.put(item)
item = queue.get()
```

**Proposed Blazing API:**
```python
# Distributed Dict
cache = blazing.Dict.from_name("inference-cache")

# Async operations
await cache.put("key", value)
value = await cache.get("key")
await cache.delete("key")

# Batch operations
await cache.put_many({"k1": v1, "k2": v2})
values = await cache.get_many(["k1", "k2"])

# TTL support
await cache.put("key", value, ttl=3600)

# Iteration
async for key, value in cache.items():
    ...
```

```python
# Distributed Queue
queue = blazing.Queue.from_name("batch-jobs")

# Put/get
await queue.put({"task": "process", "id": 123})
item = await queue.get(timeout=30)

# Batch operations
await queue.put_many([item1, item2, item3])
items = await queue.get_many(n=10, timeout=30)

# Queue info
length = await queue.len()
```

**Implementation Notes:**
- Wrapper around Redis with multi-tenant isolation
- Dict: Redis HSET/HGET with app_id prefix
- Queue: Redis LPUSH/BRPOP with app_id prefix
- CRDT-safe operations for multi-master
- TTL and cleanup policies
- Size limits per tenant

**Files to Create:**
- `src/blazing/dict.py` - Distributed Dict class
- `src/blazing/queue.py` - Distributed Queue class

---

## Priority 2: Developer Experience

### 6. Cloud Bucket Mounts

**Status:** Not Implemented

**Modal API:**
```python
@app.function(
    mounts=[modal.CloudBucketMount("s3://my-bucket", "/data")]
)
def process():
    with open("/data/file.csv") as f:
        ...
```

**Proposed Blazing API:**
```python
# S3
s3_mount = blazing.CloudBucketMount(
    "s3://my-bucket/prefix",
    secret=blazing.Secret.from_name("aws-credentials")
)

# GCS
gcs_mount = blazing.CloudBucketMount(
    "gs://my-bucket",
    secret=blazing.Secret.from_name("gcp-credentials")
)

@app.step(mounts={"/data": s3_mount})
async def process():
    with open("/data/file.csv") as f:
        ...
```

**Implementation Notes:**
- S3 via s3fs/boto3
- GCS via gcsfs
- Azure Blob via adlfs
- Credential injection from Secrets
- Read-only and read-write modes
- Caching for performance

---

### 7. Dynamic Batching

**Status:** Not Implemented

**Modal API:**
```python
@app.function(gpu="A100")
@modal.batched(max_batch_size=32, wait_ms=100)
async def batch_inference(inputs: list[Tensor]):
    return model.forward(inputs)
```

**Proposed Blazing API:**
```python
@app.step(gpu="A100")
@blazing.batched(max_size=32, wait_ms=100)
async def batch_inference(inputs: list[Tensor]):
    # Called with batched inputs automatically
    return model.forward(inputs)

# With custom batching logic
@app.step(gpu="A100")
@blazing.batched(
    max_size=32,
    wait_ms=100,
    pad_to_max=True,  # Pad batch to max_size
    sort_by=lambda x: len(x),  # Sort for efficiency
)
async def nlp_inference(texts: list[str]):
    ...
```

**Implementation Notes:**
- Input accumulator in worker
- Time-based and size-based triggers
- Continuous batching for streaming inputs
- Result demultiplexing back to callers
- GPU memory-aware batch sizing

---

### 8. Sandbox Snapshots

**Status:** Not Implemented

**Modal API:**
```python
sandbox = modal.Sandbox.create(app=app)
# ... do work ...
snapshot = sandbox.snapshot()

# Later, restore from snapshot
sandbox = modal.Sandbox.from_snapshot(snapshot)
```

**Proposed Blazing API:**
```python
# Create sandbox with snapshotting enabled
sandbox = await blazing.Sandbox.create(
    enable_snapshots=True,
    max_snapshots=5
)

# Take snapshot
snapshot_id = await sandbox.snapshot("checkpoint-1")

# Restore from snapshot
sandbox = await blazing.Sandbox.from_snapshot(snapshot_id)

# List snapshots
snapshots = await blazing.Sandbox.list_snapshots()
```

**Implementation Notes:**
- Filesystem state capture for Pyodide sandbox
- Memory state serialization
- Snapshot storage in Volumes or object storage
- Snapshot expiration policies

---

### 9. Dashboard/Monitoring UI

**Status:** Not Implemented

**Features to Implement:**
- Real-time job status
- Worker pool visualization
- Queue depths and throughput
- Error logs and traces
- Resource utilization (CPU, memory, GPU)
- Cost tracking per tenant
- Historical metrics and graphs

**Implementation Notes:**
- Separate frontend service (React/Vue)
- WebSocket for real-time updates
- Prometheus metrics export
- Grafana dashboards as alternative

---

### 10. Multi-Language SDKs

**Status:** Python only

**Languages to Support:**
- JavaScript/TypeScript (highest priority)
- Go
- Rust (future)

**JavaScript SDK API:**
```typescript
import { Blazing } from '@blazing/sdk';

const app = new Blazing({
  apiUrl: 'https://api.blazing.io',
  apiToken: process.env.BLAZING_TOKEN
});

// Call a workflow
const result = await app.run('my-workflow', { x: 5, y: 10 });

// Submit and poll
const unit = await app.submit('my-workflow', { x: 5 });
const status = await unit.status();
const result = await unit.result();
```

---

## Priority 3: Enterprise Features

### 11. GPU Notebooks

**Status:** Not Implemented

**Features:**
- Interactive Jupyter notebooks
- GPU-backed compute
- Volume access
- Collaborative editing
- Notebook → Production workflow conversion

---

### 12. Custom Domains

**Status:** Not Documented

**Proposed API:**
```python
@app.endpoint(
    path="/api/predict",
    domain="api.mycompany.com"
)
async def predict(data): ...
```

---

### 13. OpenTelemetry Integration

**Status:** Not Implemented

**Proposed API:**
```python
app = Blazing(
    api_url="...",
    api_token="...",
    telemetry=blazing.OpenTelemetry(
        endpoint="https://otel.example.com",
        service_name="my-service"
    )
)
```

---

### 14. SSO/OIDC

**Status:** Not Implemented

**Features:**
- Okta integration
- Azure AD integration
- Google Workspace
- Custom OIDC provider

---

## Implementation Roadmap

### Phase 1: Core Infrastructure (Q1)
| Feature | Complexity | Dependencies |
|---------|------------|--------------|
| Secrets Management | Medium | Blazing Registry encryption |
| Volumes | High | Blazing Core storage |
| GPU Support | High | Blazing Core GPU scheduling |

### Phase 2: Developer Experience (Q2)
| Feature | Complexity | Dependencies |
|---------|------------|--------------|
| Cron/Scheduling | Medium | Coordinator scheduler |
| Distributed Dict/Queue | Low | Redis wrappers |
| Dashboard UI | High | Frontend service |

### Phase 3: Advanced Features (Q3)
| Feature | Complexity | Dependencies |
|---------|------------|--------------|
| Dynamic Batching | Medium | Worker modifications |
| Cloud Bucket Mounts | Medium | Cloud SDK integrations |
| Sandbox Snapshots | Medium | Pyodide modifications |

### Phase 4: Enterprise & SDKs (Q4)
| Feature | Complexity | Dependencies |
|---------|------------|--------------|
| JavaScript SDK | Medium | REST API stability |
| SSO/OIDC | Medium | Auth infrastructure |
| OpenTelemetry | Low | Metrics collection |

---

## Appendix: Blazing Unique Features

Features Blazing has that Modal doesn't:

| Feature | Description |
|---------|-------------|
| **4-Tier Worker Model** | BLOCKING, NON_BLOCKING, *_SANDBOXED for trust levels |
| **Service/Connector Pattern** | Explicit abstraction for external services |
| **CRDT Multi-Master Queues** | KeyDB/Redis multi-master ready |
| **Apache Arrow Flight** | 3-5x faster columnar data transfer |
| **Code Attestation** | HMAC-SHA256/Ed25519 cryptographic signing |
| **AST Security Validation** | Compile-time dangerous code detection |
| **Pyodide WASM Sandbox** | Browser-based Python isolation |
| **Buildah Support** | Alternative to Kaniko for builds |

---

*Last updated: 2025-12-25*
