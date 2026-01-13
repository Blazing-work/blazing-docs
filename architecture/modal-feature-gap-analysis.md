# Modal Feature Gap Analysis

Comparison of Modal.com features vs Blazing's current capabilities.

## Feature Comparison Matrix

| Feature Category | Modal | Blazing | Gap? |
|-----------------|-------|---------|------|
| **Core Execution** | | | |
| Serverless functions | `@app.function()` | `@app.step()` | No |
| Class-based execution | `@app.cls()` | `@app.service()` | No |
| Async/sync support | Both | Both | No |
| Auto-scaling | Yes | Yes (worker pool) | No |
| Cold start optimization | Sub-second | TBD | **Maybe** |
| **Containers & Images** | | | |
| Custom images | `modal.Image` | `blazing.Image` | No |
| Fluent builder API | `.pip_install()`, `.apt_install()` | Same API | No |
| Dockerfile support | `.from_dockerfile()` | `.from_dockerfile()` | No |
| Build caching | Layer caching | Content hash caching | No |
| **GPU Support** | | | |
| GPU types (T4, A100, H100, etc.) | Full range | Not implemented | **YES** |
| Multi-GPU | Up to 8 GPUs | Not implemented | **YES** |
| GPU fallbacks | Priority list | Not implemented | **YES** |
| GPU memory options | 40GB/80GB variants | Not implemented | **YES** |
| **Persistent Storage** | | | |
| Volumes | `modal.Volume` | Not implemented | **YES** |
| Volume mounting | `volumes={"/data": vol}` | Not implemented | **YES** |
| Cloud bucket mounts | S3, GCS support | Not implemented | **YES** |
| **Secrets Management** | | | |
| Secrets store | `modal.Secret` | Not implemented | **YES** |
| Secret injection | `secrets=[secret]` | Not implemented | **YES** |
| Provider templates | AWS, GCP, HuggingFace | Not implemented | **YES** |
| `.env` file support | `Secret.from_dotenv()` | Not implemented | **YES** |
| **Scheduling** | | | |
| Cron jobs | `@app.function(schedule=...)` | Not implemented | **YES** |
| Periodic execution | `modal.Cron`, `modal.Period` | Not implemented | **YES** |
| **Web Endpoints** | | | |
| HTTP endpoints | `@app.web_endpoint()` | `@app.endpoint()` | No |
| Response modes | sync, streaming | ASYNC, SYNC, STREAM, WEBHOOK | No |
| WebSocket support | Via ASGI | `enable_websocket=True` | No |
| Custom domains | Yes | Not documented | **Maybe** |
| **Concurrency** | | | |
| Container concurrency | `@modal.concurrent()` | Worker pool (per-process) | Partial |
| Target inputs | `target_inputs` param | PILOT_LIGHT_ASYNC_SLOTS | Partial |
| Dynamic batching | Beta feature | Not implemented | **YES** |
| **Sandboxes** | | | |
| Arbitrary code execution | `modal.Sandbox` | `@app.step(sandboxed=True)` | No |
| Sandbox snapshots | Filesystem snapshots | Not implemented | **YES** |
| Named sandboxes | `Sandbox.from_name()` | Not applicable | N/A |
| **Data Structures** | | | |
| Distributed Dict | `modal.Dict` | Not implemented | **YES** |
| Distributed Queue | `modal.Queue` | Redis queues (internal) | Partial |
| **Notebooks** | | | |
| GPU notebooks | Modal Notebooks | Not implemented | **YES** |
| **Monitoring** | | | |
| Built-in dashboard | Yes | Not implemented | **YES** |
| OpenTelemetry | Integration | Not documented | **Maybe** |
| Datadog | Integration | Not documented | **Maybe** |
| **SDKs** | | | |
| Python | Primary | Primary | No |
| JavaScript/TypeScript | Yes | Not implemented | **YES** |
| Go | Yes | Not implemented | **YES** |
| **Enterprise** | | | |
| SSO (Okta) | Yes | Not documented | **Maybe** |
| OIDC | Yes | Not documented | **Maybe** |
| Teams/Organizations | Yes | Multi-tenant via JWT | Partial |

---

## Critical Gaps (Priority 1)

### 1. GPU Support
**Modal**: Full GPU support with T4, L4, A10, A100 (40/80GB), L40S, H100, H200, B200. Multi-GPU up to 8 per container. Automatic GPU upgrades. GPU fallback lists.

**Blazing**: No GPU support. Workers run on CPU only.

**Implementation Estimate**: High complexity
- Blazing Core integration for GPU node scheduling
- Worker type extensions (GPU_BLOCKING, GPU_NON_BLOCKING)
- GPU resource requests in step decorator
- GPU memory management

```python
# Proposed API
@app.step(gpu="A100", gpu_count=2)
async def train_model(data):
    ...
```

---

### 2. Volumes (Persistent Storage)
**Modal**: High-performance distributed filesystem. Mount to containers. Explicit commit/reload for changes. 1TB+ per file (v2).

**Blazing**: No persistent volume support. Only Redis-based data transfer.

**Implementation Estimate**: Medium complexity
- BlazingVolume class with Blazing Core storage backend
- Volume mounting in executor containers
- Read/write/commit semantics
- Integration with BlazingBuild for image layers

```python
# Proposed API
vol = blazing.Volume.persisted("model-weights")

@app.step(volumes={"/models": vol})
async def inference(input_data):
    model = load_model("/models/latest.pt")
    return model.predict(input_data)
```

---

### 3. Secrets Management
**Modal**: Secure credential storage. Dashboard + CLI + SDK creation. Environment variable injection. Provider templates.

**Blazing**: No dedicated secrets management. Credentials passed via constructor or env vars.

**Implementation Estimate**: Medium complexity
- BlazingSecret class
- Secrets storage in Blazing Registry (encrypted)
- Environment variable injection in executors
- CLI for secret management

```python
# Proposed API
@app.step(secrets=[blazing.Secret.from_name("db-credentials")])
async def query_database():
    conn = os.environ["DATABASE_URL"]
    ...
```

---

### 4. Cron/Scheduled Jobs
**Modal**: Built-in scheduling with `modal.Cron` and `modal.Period`. Cron expressions and interval-based.

**Blazing**: No scheduling support. Jobs must be triggered externally.

**Implementation Estimate**: Medium complexity
- Scheduler service in Coordinator
- Cron expression parsing
- Job trigger queue
- Schedule management API

```python
# Proposed API
@app.workflow(schedule=blazing.Cron("0 * * * *"))  # Every hour
async def hourly_report():
    ...

@app.workflow(schedule=blazing.Period(minutes=30))
async def periodic_sync():
    ...
```

---

### 5. Distributed Data Structures (Dict/Queue)
**Modal**: `modal.Dict` for in-memory key-value storage. `modal.Queue` for job queues.

**Blazing**: Internal Redis queues only. No user-facing distributed data structures.

**Implementation Estimate**: Low-Medium complexity
- Wrapper around Redis with multi-tenant isolation
- Dict: HSET/HGET operations
- Queue: LPUSH/RPOP operations
- Expiration and cleanup policies

```python
# Proposed API
cache = blazing.Dict.from_name("inference-cache")
job_queue = blazing.Queue.from_name("batch-jobs")

@app.step()
async def process():
    cached = await cache.get("key")
    if not cached:
        result = compute()
        await cache.put("key", result)

    # Queue example
    await job_queue.put({"task": "process", "id": 123})
```

---

## Medium Priority Gaps (Priority 2)

### 6. Cloud Bucket Mounts
**Modal**: Direct S3/GCS mounting as local filesystem.

**Blazing**: No cloud storage integration.

```python
# Proposed API
@app.step(mounts=[blazing.CloudBucketMount("s3://my-bucket", "/data")])
async def process_data():
    with open("/data/input.csv") as f:
        ...
```

---

### 7. Dynamic Batching
**Modal**: Automatically batch inputs for GPU efficiency (vLLM-style continuous batching).

**Blazing**: No batching support. Each operation is processed individually.

```python
# Proposed API
@app.step(gpu="A100", batch_max_size=32, batch_linger_ms=100)
async def batch_inference(inputs: list[Tensor]):
    # Called with batched inputs
    return model.forward(inputs)
```

---

### 8. Sandbox Snapshots
**Modal**: Preserve sandbox filesystem state for later restoration.

**Blazing**: Pyodide sandbox is stateless between executions.

---

### 9. Dashboard/Monitoring UI
**Modal**: Built-in web dashboard for monitoring, logs, metrics.

**Blazing**: No UI. Monitoring via logs only.

---

### 10. Multi-Language SDKs
**Modal**: Python, JavaScript/TypeScript, Go SDKs.

**Blazing**: Python only.

---

## Lower Priority Gaps (Priority 3)

### 11. GPU Notebooks
Interactive notebook environment with GPU access.

### 12. Custom Domains
User-defined domains for web endpoints.

### 13. OpenTelemetry/Datadog Integration
Built-in observability integrations.

### 14. SSO/OIDC
Enterprise authentication beyond JWT.

---

## Features Blazing Has That Modal Doesn't

| Feature | Blazing | Modal |
|---------|---------|-------|
| **4-tier Worker Model** | BLOCKING, NON_BLOCKING, BLOCKING_SANDBOXED, NON_BLOCKING_SANDBOXED | Single execution model |
| **Service/Connector Pattern** | `@app.service()` with explicit connectors | No equivalent abstraction |
| **Multi-tenant by Design** | JWT-based tenant isolation, app_id namespacing | Team/org separation only |
| **CRDT Multi-Master Queues** | KeyDB/Redis multi-master ready | Not documented |
| **Apache Arrow Flight** | Native columnar data transfer | Not documented |
| **Code Attestation** | HMAC-SHA256/Ed25519 signing | Not documented |
| **AST Security Validation** | Compile-time code scanning | Runtime sandbox only |
| **Pyodide WASM Sandbox** | Browser-based Python sandbox | Container-based sandbox |
| **Local Development Emulators** | LocalRegistry, LocalBuildService, LocalStack | Local dev via `modal serve` |
| **Buildah Support** | Planned for production builds | Docker/Kaniko only |

---

## Recommended Implementation Roadmap

### Phase 1: Core Infrastructure (Q1)
1. **Secrets Management** - Foundation for secure credential handling
2. **Volumes** - Required for ML model storage and data pipelines
3. **GPU Support** - Critical for AI/ML workloads

### Phase 2: Developer Experience (Q2)
4. **Cron/Scheduling** - Enables recurring workflows
5. **Distributed Dict/Queue** - User-facing data structures
6. **Dashboard UI** - Monitoring and management

### Phase 3: Advanced Features (Q3)
7. **Dynamic Batching** - GPU efficiency optimization
8. **Cloud Bucket Mounts** - S3/GCS integration
9. **Sandbox Snapshots** - Stateful sandbox support

### Phase 4: Enterprise & SDKs (Q4)
10. **JavaScript SDK** - Frontend integration
11. **SSO/OIDC** - Enterprise auth
12. **OpenTelemetry** - Observability

---

## Sources

- [Modal.com](https://modal.com/)
- [Modal GPU Guide](https://modal.com/docs/guide/gpu)
- [Modal Volumes Guide](https://modal.com/docs/guide/volumes)
- [Modal Secrets Guide](https://modal.com/docs/guide/secrets)
- [Modal Sandboxes Guide](https://modal.com/docs/guide/sandbox)
- [Modal Concurrent Inputs](https://modal.com/docs/guide/concurrent-inputs)
- [Serverless GPU with Modal](https://www.edlitera.com/blog/posts/serverless-gpu-ai-modal)
- [Modal Product Updates Aug 2025](https://modal.com/blog/modal-product-update-aug-2025)
