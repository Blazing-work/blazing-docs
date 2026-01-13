# Final Coordinator/Executor Architecture for Blazing SaaS

**Date:** 2025-11-25
**Status:** Ready for Implementation
**Goal:** True environment isolation with executor-side data fetching for Blazing SaaS

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Guiding Principles](#guiding-principles)
3. [Security Architecture (Defense-in-Depth)](#security-architecture-defense-in-depth)
4. [SaaS Architecture Overview](#saas-architecture-overview)
5. [Process Architecture](#process-architecture)
6. [Data Flow Architecture](#data-flow-architecture)
   - [Data Address Pattern](#data-address-pattern-implemented-) ⭐ **IMPLEMENTED**
7. [Connector Architecture](#connector-architecture)
8. [Implementation Phases](#implementation-phases)
9. [Architectural Decisions (Final)](#architectural-decisions-final)
10. [Testing Strategy](#testing-strategy)
11. [Rollout Plan](#rollout-plan)

---

## Executive Summary

### The Problem
- Blazing coordinator cannot achieve true environment isolation with in-process execution
- sys.path manipulation fails when package versions differ between base and replicated venvs
- Test demonstrates: functions import from base environment instead of isolated venv

### The Solution

**Two-Process Architecture with Swappable Executor Backends:**

```
┌─────────────────────────────────────────────────────────────────┐
│ Worker Process (System Python - TRUSTED)                       │
│                                                                 │
│  • Orchestration (routes, DAG execution, status tracking)      │
│  • ALL user code sent to executor (no in-process execution)    │
│  • Connector management (auth, throttling, rate limits)        │
│  • Sends metadata only (~1KB) to executor via JSON/HTTP        │
│                                                                 │
│  DIRECT ACCESS:                                                │
│  ✓ Coordination Redis (queues, status, worker state)          │
│  ✓ Connector instances (with encrypted auth, throttling)      │
│                                                                 │
│  EXPOSES APIs for Executor:                                    │
│  ✓ POST /v1/connectors/{name}/fetch (proxies to connectors)   │
│  ✓ POST /v1/data/operations/... (sub-operation management)    │
│  ✓ GET  /v1/data/services/... (service metadata)            │
│                                                                 │
│  Responsibilities:                                             │
│  ✓ Poll Coordination Redis for operations                     │
│  ✓ Send ALL operations to executor (Pyron-like interface)     │
│  ✓ Track operation status                                     │
│  ✓ Proxy Connector requests from Executor                     │
│  ✗ NO user code execution (all undill runs in executor)       │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ JSON/HTTP (Pyron-like interface)
                          │ {operation_id, serialized_function,
                          │  args_address, kwargs_address}
                          │
                ┌─────────┴─────────┐
                │                   │
                │  Swappable        │
                │  Backend          │
                │                   │
         ┌──────▼──────┐    ┌──────▼──────┐
         │             │    │             │
    ┌────▼──────┐ ┌───▼─────────┐ ┌──────▼──────┐
    │ Pyodide   │ │   Docker    │ │   Docker    │
    │ (WASM)    │ │  (Native)   │ │  + gVisor   │
    │           │ │             │ │  (Max Sec)  │
    └───────────┘ └─────────────┘ └─────────────┘
         │              │              │
         │              │              │
         ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Executor Backend (Isolated Environment - UNTRUSTED)            │
│                                                                 │
│  • Receives: operation_id, serialized_function, addresses     │
│  • Resolves addresses via get_data() → actual data            │
│  • Executes in RestrictedPython sandbox                        │
│  • Returns result (or stores via set_data if large)           │
│                                                                 │
│  DATA RESOLUTION (via get_data):                              │
│  ✓ 'redis' → inline data from OperationDAO                    │
│  ✓ 'RedisIndirect|{pk}' → fetch from Data Redis               │
│  ✓ 'arrow|{grpc}|{pk}|{ipc}' → fetch from Arrow Flight        │
│  ✓ LRU cache with TTL (150x speedup on hits)                  │
│                                                                 │
│  API ACCESS (Connectors - proxied through Worker):            │
│  ✓ POST /v1/connectors/{name}/fetch → REST APIs, PostgreSQL   │
│  ✓ Worker enforces: auth, throttling, rate limits             │
│                                                                 │
│  API ACCESS (Operations - orchestration):                     │
│  ✓ POST /v1/data/operations/... → sub-operations              │
│                                                                 │
│  BLOCKED:                                                      │
│  ✗ NO direct access to Coordination Redis                     │
│  ✗ NO direct access to Connector credentials                  │
│  ✗ NO access to other customers' data                         │
└─────────────────────────────────────────────────────────────────┘
```

**Swappable Backend Architecture** (inspired by Pyron):
- **Pyodide (WASM):** Fast startup (~100ms), browser-compatible, edge deployment
- **Docker (Native):** Native Python speed, production server deployment
- **Docker + gVisor:** Maximum security, userspace kernel, production high-security
- **Same API:** Change backend parameter, everything else stays the same

### Key Benefits

1. ✅ **True environment isolation** - Subprocess execution with isolated venv
2. ✅ **Security by design** - Executor is UNTRUSTED, all sensitive access via API
3. ✅ **Optimal performance** - Connection pooling (30x), caching (150x), parallel fetching (1.5-3x)
4. ✅ **SaaS multi-tenancy** - Two Redis instances per customer (coordination + data)
5. ✅ **Clean separation** - Worker orchestrates, executor fetches/computes
6. ✅ **Centralized auth/throttling** - Connectors managed by trusted Worker

---

## Key Terminology

| Term | Definition | Access |
|------|------------|--------|
| **Datasource** | Customer's own data storage | Executor DIRECT access |
| | • Data Redis (`redis-data:6379`) | Read/Write |
| | • Arrow Flight servers | Read/Write |
| **Connector** | External APIs/databases with auth | Executor via API only |
| | • REST APIs (with rate limiting) | Via `/v1/connectors/{name}/fetch` |
| | • PostgreSQL (with connection pools) | Via `/v1/connectors/{name}/fetch` |
| | • Third-party services | Via `/v1/connectors/{name}/fetch` |
| **Service** | Business logic class that uses Connectors | Worker manages |
| | • Receives connector instances at init | |
| | • Provides methods for station functions | |
| **Coordination Redis** | Orchestration data (queues, status) | Worker ONLY |
| **Data Redis** | Customer application data | Executor DIRECT access |

---

## Guiding Principles

### Principle 1: Executor is UNTRUSTED

**What this means:**
- User-defined stations run inside executor (Docker/Pyodide)
- Executor is treated as potentially malicious code
- All access to sensitive resources goes through Worker API

**Executor Access Pattern:**
- **DIRECT:** Datasources (Data Redis, Arrow Flight) - customer's own data
- **VIA API:** Connectors (REST, PostgreSQL) - Worker proxies with auth/throttling
- **VIA API:** Operations - sub-operation creation/status
- **BLOCKED:** Coordination Redis, Connector credentials, other customers' data

**Implementation:**

```python
# Executor container (UNTRUSTED)
class ExecutorContainer:
    def __init__(self, data_redis_url: str, worker_api_url: str):
        # DIRECT ACCESS: Customer's own datasources
        self.data_redis = RedisClient(data_redis_url)  # Read/Write
        self.arrow_client = ArrowFlightClient()         # Read/Write

        # API ACCESS: Worker URL for Connector proxying
        self.worker_api_url = worker_api_url
        self.api_token = os.getenv('BLAZING_API_TOKEN')

        # NO connection to Coordination Redis
        # NO direct access to Connector credentials

    async def fetch_via_connector(self, connector_name: str, params: dict):
        """Fetch data via Worker's Connector API proxy."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.worker_api_url}/v1/connectors/{connector_name}/fetch",
                json=params,
                headers={'Authorization': f'Bearer {self.api_token}'}
            )
            return response.json()
```

### Principle 2: Externalize Synchronization Logic

**What this means:**

- All synchronization (operation creation, status updates, worker management) happens in worker
- Executor focuses solely on data fetching + computation
- No distributed coordination logic inside executor

**Implementation:**
```python
# ✅ WORKER (outside executor)
async def execute_operation(operation_pk):
    # Worker handles synchronization
    await update_operation_status(operation_pk, "IN_PROGRESS")

    # Send to executor via JSON/HTTP (Pyron-like interface)
    result = await executor_backend.execute_async(operation_pk, ...)

    # Worker handles result sync
    await update_operation_status(operation_pk, "COMPLETED")
    await store_result(operation_pk, result)

# ✅ EXECUTOR (no sync logic)
async def execute_operation(operation_data):
    # Just fetch data
    data = await fetch_datasources(operation_data['datasources'])

    # Execute computation
    result = await execute_function(operation_data['func'], data)

    # Return result (coordinator handles storage)
    return result
```

### Principle 3: Own Data or Read-Only Services

**What this means:**
- Executor accesses:
  - **Own data:** Results of its own computations
  - **Read/Write services:** Customer data Redis, Arrow Flight (general datasources)
  - **Read-only services:** PostgreSQL (via read-only Arrow Flight wrapper)
- No shared mutable state between executors

**Implementation:**
```python
# Customer provisioning
async def provision_customer(customer_id):
    # Create orchestration Redis (shared, managed by Blazing)
    orchestration_redis = await create_redis_instance(f"blazing-orchestration-{customer_id}")

    # Create data Redis (customer-owned, read/write for executors)
    data_redis = await create_redis_instance(f"blazing-data-{customer_id}")

    # Create Arrow Flight servers (general datasources, read/write)
    arrow_flight_server = await create_arrow_flight_server(f"blazing-flight-{customer_id}")

    # Create PostgreSQL (wrapped by read-only Arrow Flight for zero-copy)
    postgres_db = await create_postgres_instance(f"blazing-db-{customer_id}")
    postgres_arrow_flight = await create_arrow_flight_wrapper(postgres_db, read_only=True)

    return {
        'orchestration_redis_url': orchestration_redis.url,
        'data_redis_url': data_redis.url,
        'arrow_flight_endpoint': arrow_flight_server.endpoint
    }
```

---

## Security Architecture (Defense-in-Depth)

### Overview: Multi-Layer Security Stack

Blazing implements **defense-in-depth security** adapted from Pyron's proven architecture, providing multiple layers of protection against malicious code execution.

### Security Stack

```
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1: CLIENT-SIDE VALIDATION (Before Serialization)             │
│                                                                     │
│  ✅ RestrictedPython + AST Validation                              │
│  ✅ Blocks dangerous imports (os, subprocess, socket, etc.)        │
│  ✅ Blocks dangerous builtins (eval, exec, open, etc.)             │
│  ✅ Validates code BEFORE dill.dumps()                             │
│  ✅ Clear error messages at publish() time                         │
│                                                                     │
│  Performance: ~1-5ms overhead (once at publish time)               │
│  Source: Adapted from Pyron's security.py (399 lines)              │
└─────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 2: DOCKER CONTAINER ISOLATION (Runtime)                      │
│                                                                     │
│  ✅ Namespace isolation (PID, network, mount, UTS, IPC)            │
│  ✅ Resource limits (CPU, memory, PIDs)                            │
│  ✅ Custom bridge network                                          │
│                                                                     │
│  Performance: Minimal overhead (<1%)                                │
│  Source: Docker runtime                                            │
└─────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 3: SECCOMP SYSCALL FILTERING (Kernel-Level)                  │
│                                                                     │
│  ✅ Blocks dangerous syscalls (ptrace, reboot, mount, etc.)        │
│  ✅ Allows only safe syscalls (read, write, socket, etc.)          │
│  ✅ Kernel-level enforcement                                       │
│                                                                     │
│  Performance: <0.1% overhead (<1μs per syscall)                    │
│  Source: Pyron's seccomp-profile.json (304 lines)                  │
└─────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 4: CAPABILITY RESTRICTIONS                                   │
│                                                                     │
│  ✅ ALL capabilities dropped                                       │
│  ✅ Only NET_BIND_SERVICE added (for port binding)                 │
│  ✅ Prevents privilege escalation                                  │
│                                                                     │
│  Performance: No overhead                                           │
│  Source: Docker security options                                   │
└─────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 5: READ-ONLY FILESYSTEM                                      │
│                                                                     │
│  ✅ Container filesystem is read-only                              │
│  ✅ /tmp mounted as tmpfs with noexec,nosuid                       │
│  ✅ Prevents malware persistence                                   │
│                                                                     │
│  Performance: No overhead                                           │
│  Source: Docker read-only flag                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 6: CONTROLLED DATASOURCE ACCESS (Architectural)              │
│                                                                     │
│  ✅ Data Redis: Read/Write for customer cache                      │
│  ✅ Arrow Flight (general): Read/Write for datasources             │
│  ✅ PostgreSQL: Read-only via Arrow Flight wrapper                 │
│  ✅ Orchestration Redis: No access (coordinator only)              │
│                                                                     │
│  Performance: No overhead                                           │
│  Source: Blazing architecture (Principle 1)                        │
└─────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 7: RESOURCE LIMITS (DoS Prevention)                          │
│                                                                     │
│  ✅ CPU: 4.0 cores max                                             │
│  ✅ Memory: 4GB max                                                │
│  ✅ PIDs: 500 processes max                                        │
│  ✅ Network: Rate limiting (future)                                │
│                                                                     │
│  Performance: No overhead (prevents resource exhaustion)            │
│  Source: Docker resource constraints                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Client-Side Validation (Layer 1)

**Purpose:** Block dangerous code BEFORE it reaches infrastructure

**Implementation:** RestrictedPython + AST validation (adapted from Pyron)

**What it blocks:**
```python
# ❌ BLOCKED: Dangerous imports
import os
import subprocess
import socket
import pathlib
import urllib
import requests
import pickle

# ❌ BLOCKED: Dangerous builtins
eval('malicious code')
exec('malicious code')
open('/etc/passwd')
__import__('os')
globals()
locals()
getattr()
setattr()

# ❌ BLOCKED: Dunder access (except safe ones)
__builtins__
__class__.__bases__

# ✅ ALLOWED: Safe imports
import numpy as np
import pandas as pd
import math
import json
import datetime

# ✅ ALLOWED: Service access (Connectors)
data = await services.my_api.get_data()
```

**Usage:**
```python
from blazing import Blazing

# Security ON by default (strict mode)
app = Blazing(
    api_url="http://localhost:8000",
    api_token="customer-token"
)

@app.station
async def safe_function(data: list, services=None):
    """Data is passed as args, services for external access."""
    import numpy as np
    return float(np.mean(data))  # Data received as argument

await app.publish()  # ✅ Success

@app.station
async def malicious_function(services=None):
    import os  # ❌ Blocked
    os.system('rm -rf /')

await app.publish()
# ❌ Raises SecurityError:
# "Station 'malicious_function' failed security validation:
#  Import 'os' is blocked for security reasons"
```

**Security Levels:**
```python
# STRICT (default): Production-grade security
app = Blazing(..., security_level='strict')
# Blocks: os, subprocess, eval, exec, socket, file operations, etc.

# MODERATE: Development mode (allows some file access)
app = Blazing(..., security_level='moderate')
# Allows: pathlib (but still blocks subprocess, socket)

# PERMISSIVE: Testing only (NOT for production)
app = Blazing(..., security_level='permissive')
# Minimal restrictions, for debugging only

# CUSTOM: Fine-grained control
app = Blazing(
    ...,
    custom_allowed_imports=['numpy', 'pandas', 'scipy', 'sklearn']
)
```

**Performance:**
- Validation time: 1-5ms per function
- Happens once at `publish()` time (not per execution)
- Zero impact on executor performance

---

### Seccomp Profile (Layer 3)

**Purpose:** Kernel-level syscall filtering

**Implementation:** JSON profile copied from Pyron (304 lines)

**Blocked syscalls:**
```
ptrace          # Process tracing (debugging)
reboot          # System reboot
sethostname     # Hostname changes
setdomainname   # Domain changes
mount           # Filesystem mounting
umount          # Filesystem unmounting
umount2         # Filesystem unmounting
kexec_load      # Kernel loading
init_module     # Kernel module loading
delete_module   # Kernel module deletion
swapon          # Swap activation
swapoff         # Swap deactivation
pivot_root      # Root filesystem change
chroot          # Root directory change
acct            # Process accounting
settimeofday    # System time changes
```

**Allowed syscalls (safe operations):**
```
read, write, open, close    # File I/O
socket, bind, connect       # Network
mmap, munmap, brk           # Memory
clone, fork, execve         # Process creation
futex, rt_sigaction         # Synchronization
clock_gettime               # Time reading
```

**Docker Configuration:**
```yaml
services:
  coordinator:
    security_opt:
      - seccomp:docker/seccomp-profile.json
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    mem_limit: 4g
    cpus: 4.0
    pids_limit: 500
```

---

### Test Coverage

**Client-Side Validation Tests:** (28 tests, adapted from Pyron)
```python
# tests/test_client_security.py

class TestCodeValidator:
    ✅ test_validator_allows_safe_code
    ✅ test_validator_blocks_os_import
    ✅ test_validator_blocks_subprocess
    ✅ test_validator_blocks_eval
    ✅ test_validator_blocks_exec
    ✅ test_validator_blocks_import_builtin
    ✅ test_validator_blocks_socket
    ✅ test_validator_blocks_requests
    ✅ test_validator_blocks_file_operations
    ✅ test_validator_blocks_pickle
    ✅ test_validator_blocks_private_attributes
    ✅ test_validator_allows_custom_imports
    ✅ test_validator_blocks_unlisted_imports
    ✅ test_validator_allows_from_imports
    ✅ test_validator_blocks_from_os_import
    ✅ test_convenience_function

class TestBlazingClientSecurity:
    ✅ test_blazing_blocks_malicious_at_publish
    ✅ test_blazing_allows_safe_at_publish
    ✅ test_security_levels_work

class TestMultipleVectors:
    ✅ test_blocks_ctypes
    ✅ test_blocks_urllib
    ✅ test_blocks_pathlib
    ✅ test_blocks_shutil
    ✅ test_blocks_tempfile
    ✅ test_blocks_globals_access
    ✅ test_blocks_getattr
    ✅ test_blocks_dunder_names
    ✅ test_blocks_module_attr_calls
```

**Expected Results:** All 28 tests pass

---

### Security Audit Checklist

**Client-Side:**
- ✅ RestrictedPython validation enabled by default
- ✅ AST checks block dangerous imports/builtins
- ✅ Custom allowed imports configurable
- ✅ Clear error messages at publish time
- ✅ Service access patterns allowed
- ✅ Security levels (strict/moderate/permissive)

**Executor-Side:**
- ✅ Docker container isolation
- ✅ Seccomp syscall filtering
- ✅ ALL capabilities dropped
- ✅ Read-only filesystem
- ✅ tmpfs mounted with noexec/nosuid
- ✅ Resource limits (CPU/memory/PIDs)
- ✅ Non-root user (future)
- ✅ Custom bridge network

**Architectural:**
- ✅ Read-only data Redis (ACL enforced)
- ✅ Read-only Arrow Flight (PostgreSQL wrapper)
- ✅ No executor writes to orchestration Redis
- ✅ Multi-tenant isolation (app_id namespacing)

**Documentation:**
- ✅ Security implementation guide
- ✅ Security quickstart
- ✅ Security FAQ
- ✅ Attack vector examples

---

### Comparison with Pyron

| Security Layer | Pyron (WASM) | Pyron (Docker) | Blazing (Executor) |
|----------------|--------------|----------------|-------------------|
| **RestrictedPython** | ✅ | ✅ | ✅ (adapted) |
| **AST Validation** | ✅ | ✅ | ✅ (adapted) |
| **Seccomp** | N/A | ✅ | ✅ (copied) |
| **Read-only FS** | N/A | ✅ | ✅ (copied) |
| **Capability Drop** | N/A | ✅ | ✅ (copied) |
| **Resource Limits** | N/A | ✅ | ✅ (copied) |
| **WASM Sandbox** | ✅ | N/A | N/A |
| **gVisor (optional)** | N/A | ✅ | 🔜 (future) |

**Key Difference:** Blazing adds **client-side validation** before serialization, catching issues earlier than Pyron's executor-only validation.

---

### Performance Impact

**Client-Side Validation:**
- Overhead: 1-5ms per function
- Frequency: Once at `publish()` time
- Impact: Negligible (not on critical path)

**Seccomp Filtering:**
- Overhead: <0.1% CPU
- Latency: <1μs per syscall
- Impact: Negligible

**Docker Isolation:**
- Overhead: <1% CPU
- Memory: +50MB per container
- Impact: Acceptable for security benefit

**Total Impact:** <2% performance overhead for comprehensive security

---

### References

**Pyron Security Implementation:**
- [src/pyron/security.py](https://github.com/user/Pyron/blob/main/src/pyron/security.py) - 399 lines
- [seccomp-profile.json](https://github.com/user/Pyron/blob/main/seccomp-profile.json) - 304 lines
- [tests/test_security.py](https://github.com/user/Pyron/blob/main/tests/test_security.py) - 571 lines
- [SECURITY_IMPLEMENTATION.md](https://github.com/user/Pyron/blob/main/SECURITY_IMPLEMENTATION.md) - 787 lines

**Best Practices (2024):**
- [Python Pickle Security (DigitalOcean)](https://www.digitalocean.com/community/tutorials/python-pickle-example)
- [Insecure Deserialization (Semgrep)](https://semgrep.dev/docs/learn/vulnerabilities/insecure-deserialization/python)
- [Securing Pickle Data (LinkedIn)](https://www.linkedin.com/advice/0/what-some-best-practices-securing-validating)

---

## Swappable Backend Architecture

### Overview: One API, Multiple Execution Backends

Blazing supports **three executor backends** with identical coordinator API, inspired by Pyron's swappable backend design.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Worker (Unified API)                         │
│                                                                 │
│  backend = BlazingExecutorBackend(                             │
│      backend='pyodide'  # OR 'docker' OR 'gvisor'              │
│  )                                                              │
│  result = await backend.execute_async(                         │
│      operation_id, serialized_function,                        │
│      args_address, kwargs_address                              │
│  )                                                              │
└─────────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Pyodide    │  │    Docker    │  │   Docker     │
│   (WASM)     │  │   (Native)   │  │  + gVisor    │
│              │  │              │  │              │
│  Fast Start  │  │ Native Speed │  │  Max Security│
│  ~100ms      │  │ Production   │  │  Userspace   │
│  Browser OK  │  │ Server-only  │  │  Kernel      │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

### Backend Comparison

| Feature | Pyodide (WASM) | Docker (Native) | Docker + gVisor |
|---------|---------------|----------------|----------------|
| **Startup Time** | ~100ms | ~500ms | ~700ms |
| **Execution Speed** | 2-5x slower | Native | Native |
| **Memory** | ~50MB | ~200MB | ~250MB |
| **Browser Compatible** | ✅ Yes | ❌ No | ❌ No |
| **Edge Deployment** | ✅ Yes | ⚠️ Limited | ❌ No |
| **Security Isolation** | WASM sandbox | Docker container | Userspace kernel |
| **Syscall Filtering** | N/A (WASM) | Seccomp | gVisor syscall layer |
| **Best For** | Development, Edge, Browser | Production Server | High-Security Production |
| **Concurrent Ops** | Sequential | Parallel (100s) | Parallel (100s) |

---

### Backend 1: Pyodide (WASM)

**Architecture:**
```
Worker Process (Python)
    ↓ JSON/HTTP (Pyron-like interface)
Pyodide Executor Service (Node.js)
    ├─ FastAPI endpoints: POST /execute, GET /status/{task_id}
    ├─ Data resolution via get_data()
    │   ├─ Data Redis (RedisIndirect|pk)
    │   ├─ Arrow Flight (arrow|grpc|pk|ipc)
    │   └─ LRU cache with TTL
    └─ Pyodide/WASM
        └─ RestrictedPython sandbox
```

**Security Layers:**
1. **WASM Sandbox** - Memory isolation, no direct system access
2. **RestrictedPython** - Client-side validation before serialization
3. **Node.js Process Isolation** - Separate process from coordinator
4. **Limited Builtins** - No os, subprocess, file I/O

**Use Cases:**
- ✅ Development and testing
- ✅ Browser-based execution (Cloudflare Workers, etc.)
- ✅ Edge deployment (low latency requirements)
- ✅ Light computation (mean, sum, simple transforms)
- ❌ Heavy computation (matrix operations, ML) - use Docker instead

**Example:**
```python
from blazing_service.executor import BlazingExecutorBackend

# Create Pyodide backend (Pyron-like interface)
backend = BlazingExecutorBackend(
    backend='pyodide',
    container_url='http://localhost:8000'  # Pyodide executor service
)

# Execute operation (Pyron-like: POST /execute, poll GET /status/{task_id})
result = await backend.execute_async(
    operation_id=operation_id,
    serialized_function=serialized_function,
    args_address=args_address,
    kwargs_address=kwargs_address
)
```

---

### Backend 2: Docker (Native Python)

**Architecture:**
```
Worker (BlazingExecutorBackend)
    ↓ JSON/HTTP (Pyron-like interface)
Executor Container (FastAPI)
    ├─ POST /execute → Accept task, return task_id
    ├─ GET /status/{id} → Poll for completion
    ├─ get_data() → Resolve addresses to actual data
    │   ├─ 'redis' → inline from OperationDAO
    │   ├─ 'RedisIndirect|pk' → fetch from Data Redis
    │   └─ 'arrow|...' → fetch from Arrow Flight
    ├─ RestrictedPython sandbox
    └─ set_data() → Store result (binary tree decision)
```

**Security Layers:**
1. **Docker Container** - Namespace isolation (PID, network, mount, UTS, IPC)
2. **RestrictedPython** - Client-side validation before serialization
3. **Seccomp Profile** - Kernel-level syscall filtering (304-line profile)
4. **Capability Drop** - ALL capabilities dropped, only NET_BIND_SERVICE
5. **Read-only Filesystem** - Container filesystem is read-only
6. **Resource Limits** - CPU (4.0), memory (4GB), PIDs (500)

**Use Cases:**
- ✅ Production server deployment
- ✅ Heavy computation (matrix operations, ML inference)
- ✅ Native Python speed required
- ✅ Parallel execution (100s of concurrent operations)
- ❌ Browser deployment - use Pyodide instead

**Example:**
```python
# Create Docker executor
executor = await pool.get_or_create_executor(
    environment_spec={'python_version': '3.11', 'requirements': 'numpy==1.24.0\npandas==2.0.0'},
    backend='docker'
)

# Execute with native performance
result = await executor.execute(operation_id, func, datasources)
```

**Docker Configuration:**
```yaml
# docker-compose.yml
services:
  executor:
    image: blazing-executor:latest
    security_opt:
      - seccomp:docker/seccomp-profile.json
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    mem_limit: 4g
    cpus: 4.0
    pids_limit: 500
```

---

### Backend 3: Docker + gVisor (Maximum Security)

**Architecture:**
```
Worker (BlazingExecutorBackend)
    ↓ JSON/HTTP (Pyron-like interface)
Docker Container (gVisor runtime)
    ├─ gVisor (Userspace Kernel)
    │   ├─ Sentry (system call interceptor)
    │   ├─ Gofer (file system proxy)
    │   └─ Platform (host interface)
    │
    └─ Executor Service (inside gVisor)
        ├─ get_data() for address resolution
        ├─ RestrictedPython sandbox
        └─ set_data() for result storage
```

**Security Layers (7 layers):**
1. **gVisor Userspace Kernel** - System calls handled in userspace, not host kernel
2. **Docker Container** - Additional namespace isolation
3. **RestrictedPython** - Client-side validation before serialization
4. **Seccomp Profile** - Double protection (gVisor + Seccomp)
5. **Capability Drop** - ALL capabilities dropped
6. **Read-only Filesystem** - Container filesystem is read-only
7. **Resource Limits** - CPU/memory/PID limits

**Security Benefits:**
- **Syscall Interception:** gVisor's Sentry intercepts ALL syscalls before they reach host kernel
- **Reduced Attack Surface:** ~70% fewer syscalls exposed to host kernel
- **Container Escape Protection:** Even if container is compromised, attacker is in gVisor sandbox
- **Kernel Vulnerability Mitigation:** Host kernel exploits don't work (syscalls go to gVisor)

**Performance Trade-off:**
- Overhead: 10-30% CPU (syscall overhead)
- Memory: +50-100MB (gVisor runtime)
- Network: Minimal impact (<5%)
- **Worth it for:** High-security workloads, untrusted code, regulatory compliance

**Use Cases:**
- ✅ High-security production deployment
- ✅ Untrusted customer code
- ✅ Regulatory compliance (SOC2, HIPAA, PCI-DSS)
- ✅ Multi-tenant SaaS with strong isolation requirements
- ⚠️ Acceptable 10-30% performance overhead

**Example:**
```python
# Create gVisor-backed executor
executor = await pool.get_or_create_executor(
    environment_spec={'python_version': '3.11', 'requirements': 'numpy==1.24.0'},
    backend='gvisor'  # Automatically uses Docker + gVisor runtime
)

# Execute with maximum security
result = await executor.execute(operation_id, func, datasources)
```

**Docker Configuration:**
```yaml
# docker-compose.yml (with gVisor)
services:
  executor-gvisor:
    image: blazing-executor:latest
    runtime: runsc  # gVisor runtime
    security_opt:
      - seccomp:docker/seccomp-profile.json  # Still apply Seccomp
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    mem_limit: 4g
    cpus: 4.0
    pids_limit: 500
```

**gVisor Installation (Production Server):**
```bash
# Install gVisor runtime
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list
sudo apt-get update && sudo apt-get install -y runsc

# Configure Docker to use gVisor
sudo runsc install
sudo systemctl restart docker

# Verify installation
docker run --runtime=runsc hello-world
```

---

### Backend Selection Strategy

**Development:**
```python
# Fast iteration, quick startup
backend = 'pyodide'
```

**Production (Standard Security):**
```python
# Native performance, good security
backend = 'docker'
```

**Production (High Security):**
```python
# Maximum isolation, acceptable overhead
backend = 'gvisor'
```

**Automatic Selection (Future):**
```python
# Auto-select based on environment_spec and security requirements
executor = await pool.get_or_create_executor(
    environment_spec={...},
    backend='auto',  # Chooses best backend
    security_level='high'  # Prefers gVisor if available
)
```

---

### Unified API Across Backends

**Key Design Principle:** Same coordinator code works with any backend

```python
# Coordinator code (backend-agnostic)
async def execute_operation(operation_pk: str):
    operation_DAO = await OperationDAO.get(operation_pk)
    station_DAO = await StationDAO.get(operation_DAO.station_pk)

    # Get executor (backend determined by config or operation)
    executor = await executor_pool.get_or_create_executor(
        environment_spec=json.loads(station_DAO.environment_spec),
        backend=determine_backend(station_DAO)  # pyodide | docker | gvisor
    )

    # Execute (same API for all backends)
    result = await executor.execute(
        operation_id=operation_pk,
        func=dill.loads(station_DAO.serialized_function),
        datasources=json.loads(station_DAO.datasources)
    )

    # Update result (same for all backends)
    await OperationDAO.update(operation_pk, {
        'status': 'COMPLETED',
        'result': result.result
    })
```

**Executor Interface (Implemented by All Backends):**
```python
class ExecutorBackend(ABC):
    """Abstract base class for executor backends."""

    @abstractmethod
    async def initialize(self, environment_spec: dict) -> None:
        """Initialize executor with isolated environment."""
        pass

    @abstractmethod
    async def execute(
        self,
        operation_id: str,
        func: Callable,
        datasources: dict
    ) -> ExecutionResult:
        """Execute function with datasources."""
        pass

    @abstractmethod
    async def fetch_datasources(self, datasources: dict) -> dict:
        """Fetch all datasources (inside executor)."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up executor resources."""
        pass
```

**Implementations:**
- `PyodideExecutor(ExecutorBackend)` - WASM backend
- `DockerExecutor(ExecutorBackend)` - Native Docker backend
- `GVisorExecutor(ExecutorBackend)` - Docker + gVisor backend (inherits from DockerExecutor)

---

### Performance Benchmarks (Backend Comparison)

**Scenario 1: Fetch 10MB + Simple Mean**

| Backend | Fetch | Transfer | Compute | Total |
|---------|-------|----------|---------|-------|
| Pyodide | 50ms | 10ms (VFS) | 5ms (WASM) | **65ms** |
| Docker | 50ms | <1ms (none) | 2ms (native) | **53ms** ✅ |
| gVisor | 50ms | <1ms (none) | 3ms (native+overhead) | **54ms** ✅ |

**Winner:** Docker and gVisor (similar performance)

---

**Scenario 2: Fetch 10MB + Heavy Compute (Matrix Operations)**

| Backend | Fetch | Transfer | Compute | Total |
|---------|-------|----------|---------|-------|
| Pyodide | 50ms | 10ms | 150ms (WASM) | **210ms** |
| Docker | 50ms | <1ms | 30ms (native) | **81ms** ✅ |
| gVisor | 50ms | <1ms | 40ms (native+15% overhead) | **91ms** ✅ |

**Winner:** Docker (native speed), gVisor acceptable

---

**Scenario 3: Cached Data + Light Compute**

| Backend | Fetch | Transfer | Compute | Total |
|---------|-------|----------|---------|-------|
| Pyodide | <1ms (cache) | 10ms | 5ms | **16ms** |
| Docker | <1ms (cache) | <1ms | 2ms | **4ms** ✅ |
| gVisor | <1ms (cache) | <1ms | 3ms | **5ms** ✅ |

**Winner:** Docker (fastest), gVisor close

---

**Recommendation:**
- **Development:** Pyodide (fast startup, easy debugging)
- **Production Standard:** Docker (best performance)
- **Production High-Security:** gVisor (maximum isolation, acceptable overhead)

---

## SaaS Architecture Overview

### Two-Redis Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Customer Instance                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Orchestration Redis (Managed by Blazing)                 │  │
│  │                                                           │  │
│  │  • Operation queues (CRDT multi-master)                  │  │
│  │  • Worker state (coordinator, workers)                       │  │
│  │  • Station/Route definitions                             │  │
│  │  • Unit status tracking                                  │  │
│  │  • Timing statistics                                     │  │
│  │                                                           │  │
│  │  Access: Coordinator (read/write), API (read/write)      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Data Redis (Customer-Owned)                              │  │
│  │                                                           │  │
│  │  • Customer application data                             │  │
│  │  • Events, sensors, metrics                              │  │
│  │  • Time-series data                                      │  │
│  │  • Cache for computation results                         │  │
│  │                                                           │  │
│  │  Access: Executor (read/write), Customer apps (read/write)│  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Arrow Flight (General Datasources)                       │  │
│  │                                                           │  │
│  │  • Arrow Flight servers for various datasources          │  │
│  │  • High-performance data transport                       │  │
│  │                                                           │  │
│  │  Access: Executor (read/write)                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ PostgreSQL (Wrapped by Read-Only Arrow Flight)           │  │
│  │                                                           │  │
│  │  • Relational data (users, transactions)                 │  │
│  │  • Arrow Flight wrapper enforces read-only access        │  │
│  │  • Zero-copy data access via Arrow protocol              │  │
│  │                                                           │  │
│  │  Access: Executor (read-only via Arrow Flight wrapper)   │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### REST API Layer

```
┌─────────────────────────────────────────────────────────────────┐
│                      REST API (FastAPI)                         │
│                                                                 │
│  POST /v1/registry/sync                                         │
│    • Client publishes stations/routes                          │
│    • Stores in orchestration Redis                             │
│                                                                 │
│  POST /v1/operations                                            │
│    • Create operation from station wrapper                     │
│    • Enqueue to orchestration Redis                            │
│    • Returns operation_id                                      │
│                                                                 │
│  GET /v1/operations/{operation_id}                              │
│    • Get operation status/result                               │
│    • Reads from orchestration Redis                            │
│                                                                 │
│  GET /v1/operations/{operation_id}/timing                       │
│    • Get timing statistics                                     │
│    • Used by coordinator maintenance loop                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Process Architecture

### Complete System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Coordinator Container                                │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Centralized Maintenance Loop (Coordinator-Level)                      │ │
│  │                                                                   │ │
│  │  • Fetches timing stats from orchestration Redis                 │ │
│  │  • Analyzes coordinator + executor utilization                   │ │
│  │  • Makes rebalancing decisions                                   │ │
│  │  • Updates worker pool sizes                                     │ │
│  │  • Prevents overwhelming connections to datasources              │ │
│  │                                                                   │ │
│  │  Stats Sources:                                                  │ │
│  │    - Coordinator stats queue (orchestration Redis)               │ │
│  │    - Executor stats queue (orchestration Redis)                  │ │
│  │                                                                   │ │
│  │  Decisions:                                                      │ │
│  │    - Scale coordinators up/down                                 │ │
│  │    - Scale executors up/down                                    │ │
│  │    - Adjust connection pool limits                              │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Worker Process 1 (System Python)                                 │ │
│  │                                                                   │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │ WorkerAsync (C async workers)                              │  │ │
│  │  │  • Poll orchestration Redis for operations                 │  │ │
│  │  │  • Send ALL operations to executor (Pyron-like interface)  │  │ │
│  │  │  • Track operation status                                  │  │ │
│  │  │  • NO data fetching, NO user code execution                │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │                                                                   │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │ WorkerSync (P sync workers)                                │  │ │
│  │  │  • Reserved for future sync operations                     │  │ │
│  │  │  • Currently minimal usage                                 │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │                                                                   │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │ Stats Collection                                           │  │ │
│  │  │  • Tracks: processing_time, wait_time, queue_depth        │  │ │
│  │  │  • Pushes to orchestration Redis stats queue              │  │ │
│  │  │  • Consumed by coordinator maintenance loop                   │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │                                                                   │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │ BlazingExecutorBackend (Pyron-like interface)              │  │ │
│  │  │  • HTTP client to executor container                      │  │ │
│  │  │  • POST /execute → returns task_id immediately            │  │ │
│  │  │  • GET /status/{task_id} → poll for completion            │  │ │
│  │  │  • Exponential backoff polling (100ms → 2s max)           │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                          │                                              │
│                          │ JSON/HTTP (Pyron-like)                       │
│                          │ {operation_id, serialized_function,          │
│                          │  args_address, kwargs_address}               │
│                          ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Executor Container (FastAPI service, RestrictedPython sandbox)   │ │
│  │                                                                   │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │ Data Resolution Layer (uses get_data())                    │  │ │
│  │  │                                                            │  │ │
│  │  │  Resolves data addresses to actual data:                  │  │ │
│  │  │  • 'redis' → inline data from OperationDAO                │  │ │
│  │  │  • 'RedisIndirect|{pk}' → fetch from Data Redis           │  │ │
│  │  │  • 'arrow|{grpc}|{pk}|{ipc}' → fetch from Arrow Flight    │  │ │
│  │  │                                                            │  │ │
│  │  │  • LRU cache with TTL (150x speedup)                      │  │ │
│  │  │  • Parallel fetching (asyncio.gather)                     │  │ │
│  │  │                                                            │  │ │
│  │  │  Access Pattern:                                          │  │ │
│  │  │    ✓ Data Redis (read/write)                             │  │ │
│  │  │    ✓ Arrow Flight general (read/write)                   │  │ │
│  │  │    ✓ Arrow Flight PostgreSQL (read-only)                 │  │ │
│  │  │    ✗ NO orchestration Redis access                       │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │                                                                   │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │ RestrictedPython Sandbox                                   │  │ │
│  │  │  • AST validation (no file I/O, no os.system, etc.)       │  │ │
│  │  │  • Deserializes function, resolves data via get_data()    │  │ │
│  │  │  • Executes in restricted environment                     │  │ │
│  │  │  • Returns result (or stores via set_data if large)       │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │                                                                   │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │ Stats Collection                                           │  │ │
│  │  │  • Tracks: data_fetch_time, compute_time, cache_hit_rate  │  │ │
│  │  │  • Pushes to orchestration Redis stats queue              │  │ │
│  │  │  • Consumed by coordinator maintenance loop                   │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Worker Process 2... → JSON/HTTP → Executor Container             │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Worker Process N... → JSON/HTTP → Executor Container             │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Properties

**1. Pyron-like JSON/HTTP Interface**

- Workers communicate with executor via HTTP (like Pyron's `docker_backend.py`)
- POST /execute returns task_id immediately
- GET /status/{task_id} polls for completion with exponential backoff
- No shared memory or complex IPC - simple, debuggable JSON payloads

**2. Data Address Resolution (via get_data())**

- Worker sends DATA ADDRESSES, not actual data
- Executor uses existing `get_data()` to resolve addresses:
  - `redis` → inline data from OperationDAO
  - `RedisIndirect|{pk}` → fetch from Data Redis
  - `arrow|{grpc}|{pk}|{ipc}` → fetch from Arrow Flight

**3. Zero Data Transfer in IPC**

- Worker → Executor: ~1KB metadata only (operation_id, addresses, serialized_function)
- Executor fetches data internally from data Redis / Arrow Flight
- Aligns with Principle 3: Own data or read/write/read-only services

**4. Controlled Datasource Access**

- Executors connect to data Redis (read/write for caching)
- Arrow Flight general datasources (read/write)
- Arrow Flight wraps PostgreSQL (read-only enforced)
- No access to orchestration infrastructure
- Aligns with Principle 1: User-controlled scripts with controlled datasource access

---

## Data Flow Architecture

### Complete Operation Lifecycle

**IMPORTANT: Blazing Philosophy**
- Stations receive data through **args/kwargs**, NOT magic variables
- Routes **orchestrate** which stations get called with what data
- Services are **injected** for external data access (Connectors)
- NO `datasources` declaration on stations - that's NOT how Blazing works

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. Client Publishes Stations and Routes                                │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Client Code:                                                            │
│                                                                         │
│   from blazing import Blazing                                           │
│                                                                         │
│   app = Blazing(                                                        │
│       api_url="http://localhost:8000",                                  │
│       api_token="customer-xyz-token"                                    │
│   )                                                                     │
│                                                                         │
│   # Station: receives data as args, uses services for external access │
│   @app.station                                                          │
│   async def analyze_events(events: list, services=None):               │
│       """Station receives data through args - NOT magic variables."""   │
│       import pandas as pd                                               │
│       df = pd.DataFrame(events)                                         │
│       return float(df['value'].mean())                                  │
│                                                                         │
│   @app.station                                                          │
│   async def fetch_sensors(sensor_ids: list, services=None):            │
│       """Use services to access external APIs via Connectors."""       │
│       # services provides access to Connectors (REST APIs, DBs)        │
│       sensor_data = await services.sensor_api.get_readings(sensor_ids) │
│       return sensor_data                                                │
│                                                                         │
│   # Route: orchestrates data flow between stations                     │
│   @app.route                                                            │
│   async def process_pipeline(event_ids: list, services=None):          │
│       """Routes orchestrate - they call stations with data."""          │
│       # Fetch data via service (Connector access)                     │
│       events = await services.event_api.get_events(event_ids)          │
│       sensors = await fetch_sensors([e['sensor_id'] for e in events],   │
│                                      services=services)               │
│       # Pass data to station as args                                   │
│       result = await analyze_events(events, services=services)        │
│       return result                                                     │
│                                                                         │
│   await app.publish()  # Sends to API                                  │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. API Stores Station in Orchestration Redis                           │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ POST /v1/registry/sync                                                  │
│                                                                         │
│ Payload:                                                                │
│   {                                                                     │
│     "stations": [{                                                      │
│       "name": "analyze_events",                                         │
│       "serialized_function": "base64...",                               │
│       "station_type": "NON-BLOCKING",                                   │
│       "priority": 0.0                                                   │
│     }, {                                                                │
│       "name": "fetch_sensors",                                          │
│       "serialized_function": "base64...",                               │
│       "station_type": "NON-BLOCKING",                                   │
│       "priority": 0.0                                                   │
│     }],                                                                 │
│     "routes": [{                                                        │
│       "name": "process_pipeline",                                       │
│       "serialized_function": "base64...",                               │
│       "priority": -1.0  # Routes have priority=-1                       │
│     }]                                                                  │
│   }                                                                     │
│                                                                         │
│ Result:                                                                 │
│   StationDAO/WorkflowDAO created in orchestration Redis                    │
│   Key: blazing:{app_id}:workflow_definition:Station:{pk}                  │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. Client Creates Route Task via API                                   │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Client Code:                                                            │
│                                                                         │
│   # Data is passed as args to the route                                │
│   unit = await app.run(                                  │
│       "process_pipeline",                                               │
│       event_ids=["evt_001", "evt_002", "evt_003"]  # Args passed here  │
│   )                                                                     │
│   result = await unit.result()                                         │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ POST /v1/jobs                                                           │
│                                                                         │
│ Payload:                                                                │
│   {                                                                     │
│     "route_name": "process_pipeline",                                   │
│     "args": [],                                                         │
│     "kwargs": {"event_ids": ["evt_001", "evt_002", "evt_003"]}         │
│   }                                                                     │
│                                                                         │
│ Result:                                                                 │
│   UnitDAO + OperationDAO created in orchestration Redis                │
│   Enqueued to: blazing:{app_id}:Station:{station_pk}:Queue:{node_id}   │
│   Returns: job_id (unit_pk)                                            │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. Worker Polls Orchestration Redis                                    │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Worker Process (runtime.py:get_next_operation)                         │
│                                                                         │
│   operation_pk = await dequeue_non_blocking_operation(station_pk)       │
│   operation_DAO = await OperationDAO.get(operation_pk)                  │
│   station_DAO = await StationDAO.get(operation_DAO.station_pk)          │
│                                                                         │
│   # ALL user code goes to executor (no routing decision)               │
│   # Worker sends ADDRESSES, executor uses get_data() to resolve        │
│   await send_to_executor(operation_DAO, station_DAO)                   │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. Worker Sends to Executor (JSON/HTTP - Pyron-like)                   │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Worker: Send via BlazingExecutorBackend (Pyron-like interface)         │
│                                                                         │
│   # Send ADDRESSES, not data! Executor will use get_data() to resolve  │
│   result = await executor_backend.execute_async(                       │
│       operation_id=operation_DAO.pk,                                   │
│       serialized_function=station_DAO.serialized_function,             │
│       args_address=operation_DAO.args_address,      # Address!         │
│       kwargs_address=operation_DAO.kwargs_address,  # Address!         │
│   )                                                                     │
│                                                                         │
│   # HTTP POST to executor container                                    │
│   # POST http://executor:8000/execute                                  │
│   # Body: {"task_id": "uuid", "operation_id": "...", ...}              │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. Executor Receives Request and Resolves Addresses                    │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Executor Container: Use get_data() to resolve addresses                │
│                                                                         │
│   # 1. Get operation DAO                                               │
│   operation_dao = await OperationDAO.get(request.operation_id)          │
│                                                                         │
│   # 2. Use EXISTING get_data() to resolve addresses → actual data      │
│   #    Handles: 'redis', 'RedisIndirect|pk', 'arrow|grpc|pk|ipc'       │
│   args = await OperationDAO.get_data(operation_dao, 'args')             │
│   kwargs = await OperationDAO.get_data(operation_dao, 'kwargs')         │
│                                                                         │
│   # 3. Deserialize function                                            │
│   func = Util.deserialize_function(request.serialized_function)         │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. Executor Injects Services for Connector Access                     │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Executor: Prepare Services with Connector API Client                  │
│                                                                         │
│   # Services use Connector API proxy (credentials stay in Coordinator)│
│   connector_client = ConnectorClient(                                   │
│       coordinator_api_url=COORDINATOR_API_URL,                          │
│       api_token=API_TOKEN                                               │
│   )                                                                     │
│                                                                         │
│   # Build services with connector client                              │
│   services = await build_services(connector_client)                   │
│                                                                         │
│   # Inject services into kwargs                                       │
│   kwargs['services'] = services                                       │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 8. Executor Executes Function in Isolated venv                         │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Executor: Execute via Worker Pool                                      │
│                                                                         │
│   # Execute with args/kwargs (Blazing pattern - data as args!)         │
│   result = await func(*args, **kwargs)                                  │
│                                                                         │
│   # Inside func (station):                                              │
│   #   async def analyze_events(events: list, services=None):          │
│   #       import pandas as pd                                          │
│   #       df = pd.DataFrame(events)  # events received as arg!         │
│   #       return float(df['value'].mean())                             │
│   #                                                                     │
│   # If station needs external data, it uses services:                 │
│   #   async def fetch_more(event_ids: list, services=None):           │
│   #       data = await services.api.get_events(event_ids)             │
│   #       return data                                                   │
│                                                                         │
│   # Result: 42.5                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 9. Executor Stores Result and Returns Status                           │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Executor: Store result via set_data(), update task status              │
│                                                                         │
│   # Store result using binary tree decision (inline vs address)        │
│   await OperationDAO.set_result(                                       │
│       operation_id, result,                                            │
│       grpc_address=GRPC_ADDRESS,                                       │
│       ipc_address=IPC_ADDRESS                                          │
│   )                                                                     │
│                                                                         │
│   # Update in-memory task status (for polling)                         │
│   tasks[task_id] = {                                                    │
│       'status': 'completed',                                            │
│       'result': result,  # Small results inline, large via address     │
│       'elapsed_time': 0.080  # 80ms total                              │
│   }                                                                     │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 10. Worker Polls for Completion                                        │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Worker: Poll executor until task completes                             │
│                                                                         │
│   # GET http://executor:8000/status/{task_id}                          │
│   # Returns: {"status": "completed", "result": 42.5, ...}              │
│                                                                         │
│   while elapsed < timeout:                                              │
│       status = await client.get(f'/status/{task_id}')                  │
│       if status['status'] == 'completed':                              │
│           return ExecutionResult(success=True, result=status['result'])│
│       await asyncio.sleep(poll_interval)                               │
│       poll_interval = min(poll_interval * 1.5, 2.0)  # Backoff         │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 11. Worker Updates Operation Status in Redis                           │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Worker: Update operation status after executor completes               │
│                                                                         │
│   # Result already stored by executor via set_data()                   │
│   # Worker just updates status                                          │
│   await Util.update_fields_in_transaction(OperationDAO, operation_id, {│
│       'current_status': 'DONE',                                        │
│       'processing_time': result.elapsed_time                           │
│   })                                                                    │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 12. Coordinator Maintenance Loop Consumes Stats                            │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Coordinator: Analyze Stats and Rebalance                                   │
│                                                                         │
│   # Fetch stats from orchestration Redis                               │
│   coordinator_stats = await redis.lrange(                               │
│       f"blazing:{app_id}:CoordinatorStatisticsQueue:*", 0, -1           │
│   )                                                                     │
│   executor_stats = await redis.lrange(                                  │
│       f"blazing:{app_id}:ExecutorStatisticsQueue:*", 0, -1              │
│   )                                                                     │
│                                                                         │
│   # Analyze                                                             │
│   avg_data_fetch_time = mean([s['data_fetch_time'] for s in executor_stats])│
│   cache_hit_rate = sum([s['cache_hit'] for s in executor_stats]) / len(...)│
│   coordinator_queue_depth = ...                                         │
│                                                                         │
│   # Make rebalancing decisions                                          │
│   if avg_data_fetch_time > 0.100:  # >100ms avg fetch                  │
│       # Increase executor connection pool size                         │
│       await update_executor_config({'redis_pool_size': 20})             │
│                                                                         │
│   if coordinator_queue_depth > 1000:                                    │
│       # Increase coordinator async workers                             │
│       await scale_coordinator_workers(current + 50)                     │
│                                                                         │
│   # Prevent overwhelming datasource connections                        │
│   total_redis_connections = executor_count * executor_pool_size         │
│   if total_redis_connections > 100:  # Hard limit                      │
│       await scale_down_executors()                                      │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 13. Client Retrieves Result via API                                    │
└─────────────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Client Code:                                                            │
│                                                                         │
│   result = await unit.result()  # Polls API until completed            │
│   print(f"Result: {result}")    # 42.5                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Data Address Pattern (IMPLEMENTED ✅)

**Location:** [src/blazing_service/data_access/data_access.py:1881-2082](src/blazing_service/data_access/data_access.py#L1881-L2082)

The Data Address Pattern enables efficient data transfer between Coordinator and Executor by using **address references** instead of transferring large data inline. This is the core mechanism for optimizing data flow in Blazing.

#### Address Types

| Address Format | Storage Location | Use Case |
|----------------|------------------|----------|
| `redis` | OperationDAO fields (args/kwargs) | Small data (<1MB), inline in operation |
| `RedisIndirect\|{pk}` | StorageDAO in Data Redis | Medium data (1MB-50MB), separate storage |
| `arrow\|{grpc}\|{op_pk}\|{ipc}` | Arrow Flight server | Large data (>50MB), PyArrow DataFrames/arrays |

#### How It Works

**1. Coordinator Sets Data (storing args/kwargs/result):**

```python
# data_access.py:set_data() - line 1881
async def set_data(cls, operation_pk, data, grpc_address, ipc_address, data_type):
    """Store operation data using optimal address pattern based on type/size."""

    # PyArrow-compatible data → Arrow Flight (zero-copy, fastest for large data)
    if isinstance(data, (pd.DataFrame, np.ndarray)):
        arrow_table = pa.Table.from_pandas(data) if isinstance(data, pd.DataFrame) else pa.table({'data': data})
        ticket = await _write_to_arrow_flight(arrow_table, grpc_address, ipc_address)

        await Util.update_field_in_transaction(
            OperationDAO, operation_pk,
            f'{data_type}_address',
            f"arrow|{grpc_address}|{operation_pk}|{ipc_address}"  # ← Arrow address
        )

    # Other data → StorageDAO (Data Redis)
    else:
        serialized_data = dill.dumps(data)
        storage_dao = StorageDAO(
            value=serialized_data,
            operation_pk=operation_pk,
            data_type=data_type
        )
        await storage_dao.save()

        await Util.update_field_in_transaction(
            OperationDAO, operation_pk,
            f'{data_type}_address',
            f"RedisIndirect|{storage_dao.pk}"  # ← RedisIndirect address
        )
```

**2. Executor Gets Data (resolving addresses from args/kwargs):**

```python
# data_access.py:get_data() - line 1988
async def get_data(cls, operation_dao, data_type):
    """Resolve data address to actual data."""

    address = getattr(operation_dao, f'{data_type}_address')

    # Address type 1: Direct storage in OperationDAO (small data)
    if address == "redis":
        serialized_data = getattr(operation_dao, data_type)
        return dill.loads(serialized_data)

    # Address type 2: StorageDAO reference (medium data)
    elif address.startswith("RedisIndirect|"):
        pk = address.split("RedisIndirect|")[1]
        storage_dao = await StorageDAO.get(pk)
        return dill.loads(storage_dao.value)

    # Address type 3: Arrow Flight reference (large data)
    elif address.startswith("arrow|"):
        # Parse: arrow|{grpc_address}|{operation_pk}|{ipc_address}
        parts = address.split("|")
        grpc_address = parts[1]
        operation_pk = parts[2]
        ipc_address = parts[3]

        return await Util._get_result_from_arrow_flight(
            address, data_format, expected_dimensions
        )
```

#### Binary Tree Decision for Results

When the Executor computes a result, it uses a **binary tree decision** to choose the optimal transfer protocol:

```
                    ┌─────────────────────┐
                    │   Result Data Type  │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
       ┌──────────┐     ┌──────────┐     ┌──────────┐
       │ DataFrame│     │  ndarray │     │  Other   │
       │ or PyArrow│     │ (large) │     │  (dict,  │
       │  Table   │     │          │     │  list)   │
       └────┬─────┘     └────┬─────┘     └────┬─────┘
            │                │                │
            ▼                ▼                ▼
    ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
    │ arrow|...     │ │ arrow|...     │ │  Size Check   │
    │ (Arrow Flight)│ │ (Arrow Flight)│ │               │
    └───────────────┘ └───────────────┘ └───────┬───────┘
                                                │
                                   ┌────────────┼────────────┐
                                   ▼            ▼            ▼
                              ┌────────┐   ┌────────┐   ┌────────┐
                              │  <1MB  │   │ 1-50MB │   │  >50MB │
                              └───┬────┘   └───┬────┘   └───┬────┘
                                  │            │            │
                                  ▼            ▼            ▼
                           ┌──────────┐ ┌─────────────┐ ┌──────────┐
                           │  redis   │ │RedisIndirect│ │ arrow|...│
                           │ (inline) │ │  |{pk}      │ │          │
                           └──────────┘ └─────────────┘ └──────────┘
```

#### Complete Data Flow Example

```
1. Client calls: app.run("pipeline", data=[...100MB DataFrame...])

2. API receives kwargs with large DataFrame
   └─> set_data() detects DataFrame → writes to Arrow Flight
   └─> Stores address: "arrow|localhost:8815|01ABC123|localhost:8816"

3. Worker sends JSON/HTTP to Executor (Pyron-like):
   └─> POST /execute {
         operation_id: "01ABC123",
         serialized_function: <base64 encoded>,
         args_address: "redis",
         kwargs_address: "arrow|localhost:8815|01ABC123|localhost:8816"  ← Reference!
       }
   └─> Returns task_id immediately

4. Executor receives operation and resolves data:
   └─> Calls get_data(kwargs_address) → fetches from Arrow Flight (zero-copy!)
   └─> Deserializes function, executes in RestrictedPython sandbox
   └─> Executes function with resolved data

5. Executor computes result (50MB array):
   └─> Binary tree: ndarray + >1MB → Arrow Flight
   └─> set_data() writes to Arrow Flight
   └─> Stores result address: "arrow|localhost:8815|01ABC123-result|localhost:8816"

6. Worker polls GET /status/{task_id}, receives result:
   └─> Updates OperationDAO.result_address = "arrow|..."
   └─> Client's unit.result() resolves address when fetched
```

#### Performance Benefits

| Scenario | Without Address Pattern | With Address Pattern |
|----------|------------------------|---------------------|
| 100MB DataFrame transfer | ~500ms (serialize + transfer) | ~5ms (address only) |
| Result fetch from cache | N/A (always transfer) | ~1ms (LRU cache hit) |
| Multiple operations same data | N × 500ms | 500ms + (N-1) × 5ms |

#### Implementation Status

- ✅ **set_data()** - [data_access.py:1881](src/blazing_service/data_access/data_access.py#L1881)
- ✅ **get_data()** - [data_access.py:1988](src/blazing_service/data_access/data_access.py#L1988)
- ✅ **_get_args_kwargs()** - [data_access.py:2055](src/blazing_service/data_access/data_access.py#L2055)
- ✅ **Arrow Flight integration** - [data_access.py:1918](src/blazing_service/data_access/data_access.py#L1918)
- ✅ **StorageDAO for RedisIndirect** - [data_access.py:1946](src/blazing_service/data_access/data_access.py#L1946)

---

## Connector Architecture

### Current Architecture (Coordinator-Side Connectors)

The existing Blazing architecture initializes connectors **per-worker-thread** inside the coordinator:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Current Architecture (Coordinator Process)                                  │
│                                                                         │
│  WorkerThread._async_init():                                           │
│    connectors = await Connectors.fetch_all_connectors()  ← Per-thread  │
│    self.services = await Services.fetch_all_services(connectors)    │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Worker Thread 1                                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐  │ │
│  │  │ Connectors (per-thread instances)                           │  │ │
│  │  │  • RESTConnector "TimeSeriesAPI" → httpx.AsyncClient        │  │ │
│  │  │  • SQLAlchemyConnector "PostgresDB" → async_engine          │  │ │
│  │  │  • Connection pools: 10-100 connections each                │  │ │
│  │  └─────────────────────────────────────────────────────────────┘  │ │
│  │  ┌─────────────────────────────────────────────────────────────┐  │ │
│  │  │ Services (receive connectors at init)                      │  │ │
│  │  │  • TimeSeriesService(connectors)                           │  │ │
│  │  │  • Uses self.api_connector.get_data(url)                    │  │ │
│  │  └─────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Worker Thread 2 (separate connector instances)                    │ │
│  │  ┌─────────────────────────────────────────────────────────────┐  │ │
│  │  │ Connectors (new instances, new connection pools)            │  │ │
│  │  │  • RESTConnector "TimeSeriesAPI" → httpx.AsyncClient        │  │ │
│  │  │  • SQLAlchemyConnector "PostgresDB" → async_engine          │  │ │
│  │  └─────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

**Current Connector Classes:**

| Class | Data Source | Connection Pooling | Location |
|-------|-------------|-------------------|----------|
| `RESTConnector` | HTTP/REST APIs | `httpx.AsyncClient` (10-2000 connections) | `runtime.py:3368-3505` |
| `SQLAlchemyConnector` | PostgreSQL | `create_async_engine` (100+20 overflow) | `runtime.py:3507-3603` |

**Key Features:**

- **Encrypted auth:** Credentials stored encrypted in Redis (`ConnectorDAO.auth`)
- **SSH tunneling:** Optional SSH tunnel for secure database access
- **Throttling:** Per-connector rate limiting (fixed interval or rolling window)
- **Dynamic loading:** Connector classes loaded at runtime via reflection

---

### New Architecture: Connector API Proxy

In the worker/executor architecture, **connectors stay in the Worker** (trusted) and the **executor calls them via API** (untrusted):

```
┌─────────────────────────────────────────────────────────────────────────┐
│ New Architecture: Connector API Proxy                                   │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Worker Process (TRUSTED - hosts Connectors)                       │ │
│  │                                                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐  │ │
│  │  │ Connector Instances (with auth, throttling, connection pools)│  │ │
│  │  │                                                             │  │ │
│  │  │  • RESTConnector "TimeSeriesAPI" → httpx.AsyncClient        │  │ │
│  │  │  • SQLAlchemyConnector "PostgresDB" → async_engine          │  │ │
│  │  │  • Credentials stored encrypted in Coordination Redis       │  │ │
│  │  │  • Rate limiting enforced per-connector                     │  │ │
│  │  └─────────────────────────────────────────────────────────────┘  │ │
│  │                                                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐  │ │
│  │  │ Connector API Endpoints (proxies requests to Connectors)    │  │ │
│  │  │                                                             │  │ │
│  │  │  POST /v1/connectors/{name}/fetch                           │  │ │
│  │  │    → Validates auth token                                   │  │ │
│  │  │    → Applies rate limiting/throttling                       │  │ │
│  │  │    → Calls connector.get_data()                             │  │ │
│  │  │    → Returns data to executor                               │  │ │
│  │  └─────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              │ HTTP API                                 │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Executor Container (UNTRUSTED - calls Connector API)             │ │
│  │                                                                   │ │
│  │  DIRECT ACCESS (Datasources - customer's own data):             │ │
│  │  ┌─────────────────────────────────────────────────────────────┐  │ │
│  │  │  • Data Redis (redis-data:6379) - Read/Write                │  │ │
│  │  │  • Arrow Flight - Read/Write                                │  │ │
│  │  └─────────────────────────────────────────────────────────────┘  │ │
│  │                                                                   │ │
│  │  API ACCESS (Connectors - via Worker proxy):                    │ │
│  │  ┌─────────────────────────────────────────────────────────────┐  │ │
│  │  │  async def fetch_from_connector(name, params):              │  │ │
│  │  │      response = await httpx.post(                           │  │ │
│  │  │          f"{WORKER_API}/v1/connectors/{name}/fetch",        │  │ │
│  │  │          json=params,                                       │  │ │
│  │  │          headers={'Authorization': f'Bearer {token}'}       │  │ │
│  │  │      )                                                      │  │ │
│  │  │      return response.json()                                 │  │ │
│  │  └─────────────────────────────────────────────────────────────┘  │ │
│  │                                                                   │ │
│  │  BLOCKED:                                                        │ │
│  │  ✗ NO direct Connector access (no credentials)                  │ │
│  │  ✗ NO Coordination Redis access                                 │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why API Proxy instead of Executor-Side Connectors:**

| Concern | Executor-Side (WRONG) | API Proxy (CORRECT) |
|---------|----------------------|---------------------|
| **Auth credentials** | Exposed to untrusted code ❌ | Stay in Worker ✅ |
| **Rate limiting** | Per-executor (hard to enforce) ❌ | Centralized (easy) ✅ |
| **Throttling** | Each executor manages own ❌ | Single point of control ✅ |
| **Connection pools** | Duplicated per executor ❌ | Shared in Worker ✅ |
| **Security** | Untrusted code has DB access ❌ | API-only access ✅ |

---

### Connector API Endpoints

The Worker/API server exposes these API endpoints for Executor to access Connectors:

```python
# worker/api/connector_api.py (in Worker/API server)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])

class ConnectorFetchRequest(BaseModel):
    """Request to fetch data via a Connector."""
    method: str = "get"  # get, post, query, etc.
    params: dict = {}    # Parameters for the connector method

class ConnectorFetchResponse(BaseModel):
    """Response from Connector fetch."""
    data: Any
    format: str = "json"  # json, arrow, pickle
    cached: bool = False


@router.post("/{connector_name}/fetch")
async def fetch_via_connector(
    connector_name: str,
    request: ConnectorFetchRequest,
    app_id: str = Depends(get_app_id),
    token: str = Depends(verify_token)
):
    """
    Proxy a data fetch request to a Connector.

    - Coordinator holds the Connector instance (with auth, connection pool)
    - Coordinator enforces rate limiting/throttling
    - Executor only gets the data back, never the credentials
    """
    # Get connector from Coordinator's registry
    connector = await get_connector(connector_name, app_id)
    if not connector:
        raise HTTPException(404, f"Connector '{connector_name}' not found")

    # Apply throttling (centralized rate limiting)
    await ConnectorDAO.throttle(connector.pk)

    # Execute the fetch via connector
    if request.method == "get":
        data = await connector.get_data(**request.params)
    elif request.method == "query":
        data = await connector.query(**request.params)
    else:
        raise HTTPException(400, f"Unknown method: {request.method}")

    return ConnectorFetchResponse(data=data, format="json")


@router.get("/{connector_name}/info")
async def get_connector_info(
    connector_name: str,
    app_id: str = Depends(get_app_id)
):
    """Get connector metadata (without exposing credentials)."""
    connector_dao = await ConnectorDAO.find(
        ConnectorDAO.name == connector_name
    ).first()

    return {
        "name": connector_dao.name,
        "type": connector_dao.target_class_name,
        "throttling": connector_dao.throttling_config,
        # NOTE: auth is NOT exposed
    }
```

---

### Executor-Side Connector Client

The Executor uses a simple HTTP client to call the Coordinator's Connector API:

```python
# executor/connector_client.py (in Executor process)

class ConnectorClient:
    """Client for accessing Connectors via Coordinator API."""

    def __init__(self, coordinator_api_url: str, api_token: str):
        self.api_url = coordinator_api_url
        self.headers = {'Authorization': f'Bearer {api_token}'}

    async def fetch(self, connector_name: str, method: str = "get", **params):
        """Fetch data via Connector API proxy."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.api_url}/v1/connectors/{connector_name}/fetch",
                json={"method": method, "params": params},
                headers=self.headers
            )
            if response.status_code != 200:
                raise RuntimeError(f"Connector fetch failed: {response.text}")
            return response.json()["data"]


# Usage in Executor (user's station function)
async def my_station_function(services=None):
    # Fetch from PostgreSQL via Connector API (NOT direct DB access)
    data = await connector_client.fetch(
        "PostgresDB",
        method="query",
        sql="SELECT * FROM events WHERE timestamp > :ts",
        params={"ts": "2024-01-01"}
    )
    return process(data)
```

---

### Executor-Side Datasource Classes

The Executor has **direct access** to Datasources (customer's own data). These are different from Connectors (external APIs with auth):

```python
# executor/datasources/redis_datasource.py

class RedisDataSource:
    """Direct access to customer's Data Redis (NOT the Coordination Redis)."""

    def __init__(self):
        self.pool: Optional[redis.asyncio.ConnectionPool] = None

    @classmethod
    async def create(cls, config: dict) -> 'RedisDataSource':
        instance = cls()

        # Create connection pool (shared across all async workers)
        instance.pool = redis.asyncio.ConnectionPool(
            host=config['host'],
            port=config.get('port', 6379),
            db=config.get('db', 0),
            max_connections=config.get('pool_size', 100),
            decode_responses=True
        )
        instance.client = redis.asyncio.Redis(connection_pool=instance.pool)

        return instance

    async def get(self, key: str) -> Optional[str]:
        """Read from data Redis."""
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: int = None) -> None:
        """Write to data Redis (for caching results)."""
        await self.client.set(key, value, ex=ex)

    async def hgetall(self, key: str) -> dict:
        """Read hash from data Redis."""
        return await self.client.hgetall(key)

    async def close(self):
        if self.client:
            await self.client.close()
        if self.pool:
            await self.pool.disconnect()


# executor/datasources/arrow_flight_datasource.py

class ArrowFlightDataSource:
    """Direct access to Arrow Flight servers (customer's datasources)."""

    def __init__(self):
        self.client: Optional[pyarrow.flight.FlightClient] = None
        self.read_only: bool = False

    @classmethod
    async def create(cls, config: dict) -> 'ArrowFlightDataSource':
        instance = cls()
        instance.read_only = config.get('read_only', False)

        # Create Flight client (connection pooling handled by Arrow)
        location = pyarrow.flight.Location.for_grpc_tcp(
            config['host'],
            config.get('port', 8815)
        )
        instance.client = pyarrow.flight.FlightClient(location)

        return instance

    async def do_get(self, ticket: bytes) -> pa.Table:
        """Fetch data via Arrow Flight (zero-copy)."""
        reader = self.client.do_get(pyarrow.flight.Ticket(ticket))
        return reader.read_all()

    async def do_put(self, descriptor: str, table: pa.Table) -> None:
        """Write data via Arrow Flight (if not read-only)."""
        if self.read_only:
            raise PermissionError("This Arrow Flight datasource is read-only")

        flight_desc = pyarrow.flight.FlightDescriptor.for_path(descriptor)
        writer, _ = self.client.do_put(flight_desc, table.schema)
        writer.write_table(table)
        writer.close()

    async def close(self):
        if self.client:
            self.client.close()


# executor/datasources/postgres_arrow_datasource.py

class PostgresArrowDataSource(ArrowFlightDataSource):
    """Read-only Arrow Flight wrapper for PostgreSQL (customer's database)."""

    @classmethod
    async def create(cls, config: dict) -> 'PostgresArrowDataSource':
        # Force read-only for PostgreSQL wrapper
        config['read_only'] = True
        return await super().create(config)

    async def query(self, sql: str, params: dict = None) -> pa.Table:
        """Execute read-only SQL query, return as Arrow Table."""
        # Ticket encodes the SQL query
        ticket_data = json.dumps({'sql': sql, 'params': params or {}})
        return await self.do_get(ticket_data.encode())
```

---

### Access Summary: Datasources vs Connectors

| Type | Location | Access Mode | Example |
|------|----------|-------------|---------|
| **Datasource** | Executor (DIRECT) | Read/Write | Data Redis, Arrow Flight |
| **Connector** | Coordinator (API PROXY) | Via `/v1/connectors/` | REST APIs, PostgreSQL |

**Key Distinction:**

- **Datasources** = Customer's own data storage → Executor accesses DIRECTLY
- **Connectors** = External APIs/databases with auth → Executor calls via Coordinator API

---

### Connector Access Patterns by Type

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Datasource Access Matrix                                                │
│                                                                         │
│  ┌─────────────────────┬────────┬────────┬────────────────────────────┐ │
│  │ Connector           │ Read   │ Write  │ Notes                      │ │
│  ├─────────────────────┼────────┼────────┼────────────────────────────┤ │
│  │ RedisConnector      │ ✅     │ ✅     │ Customer data cache        │ │
│  │ (Data Redis)        │        │        │ Results caching            │ │
│  ├─────────────────────┼────────┼────────┼────────────────────────────┤ │
│  │ ArrowFlightConnector│ ✅     │ ✅     │ General datasources        │ │
│  │ (General)           │        │        │ High-performance transport │ │
│  ├─────────────────────┼────────┼────────┼────────────────────────────┤ │
│  │ PostgresArrowConn.  │ ✅     │ ❌     │ SQL queries only           │ │
│  │ (PostgreSQL)        │        │        │ Read-only enforced         │ │
│  ├─────────────────────┼────────┼────────┼────────────────────────────┤ │
│  │ RESTConnector       │ ✅     │ ✅     │ External APIs              │ │
│  │                     │        │        │ Throttling applied         │ │
│  ├─────────────────────┼────────┼────────┼────────────────────────────┤ │
│  │ Orchestration Redis │ ❌     │ ❌     │ NO executor access         │ │
│  │                     │        │        │ Coordinator only           │ │
│  └─────────────────────┴────────┴────────┴────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Connection Pool Sizing

**Problem:** With shared connectors, pool sizing becomes critical.

**Current:** Each worker thread has its own pool → N threads × M connections = N×M total

**New:** Single pool per executor process → M connections shared across C async workers

```python
# executor/connectors/pool_config.py

class PoolConfig:
    """Connection pool sizing based on worker count."""

    @staticmethod
    def calculate_pool_size(
        async_workers: int,
        datasource_type: str,
        base_size: int = 10
    ) -> int:
        """
        Calculate optimal pool size for shared connector.

        Rule of thumb:
        - pool_size = async_workers × connections_per_worker
        - But cap at reasonable maximum to prevent resource exhaustion
        """
        multipliers = {
            'redis': 2.0,      # Redis is fast, fewer connections needed
            'postgres': 1.5,   # Postgres handles fewer concurrent connections
            'rest': 3.0,       # REST APIs may have latency, need more
            'arrow': 1.0,      # Arrow handles multiplexing well
        }

        multiplier = multipliers.get(datasource_type, 2.0)
        calculated = int(async_workers * multiplier)

        # Reasonable bounds
        min_size = base_size
        max_size = {
            'redis': 500,
            'postgres': 100,
            'rest': 2000,
            'arrow': 50,
        }.get(datasource_type, 100)

        return max(min_size, min(calculated, max_size))
```

**Example:** With 50 async workers:

- Redis: `min(50 × 2.0, 500) = 100` connections
- PostgreSQL: `min(50 × 1.5, 100) = 75` connections
- REST: `min(50 × 3.0, 2000) = 150` connections

---

### Executor Initialization with Connectors

```python
# executor/main.py

class ExecutorProcess:
    """Main executor process with shared connector registry."""

    def __init__(self, config: ExecutorConfig):
        self.config = config
        self.registry: Optional[ConnectorRegistry] = None
        self.workers: List[ExecutorWorkerAsync] = []

    async def start(self):
        """Initialize executor with shared connectors."""

        # 1. Initialize shared connector registry (once per process)
        self.registry = await ConnectorRegistry.get_instance()

        # 2. Create async workers (all share the same registry)
        for i in range(self.config.async_workers):
            worker = ExecutorWorkerAsync(
                worker_id=i,
                registry=self.registry,  # Shared reference
            )
            self.workers.append(worker)

        # 3. Start all workers
        await asyncio.gather(*[w.start() for w in self.workers])

    async def shutdown(self):
        """Graceful shutdown."""
        # Stop workers first
        await asyncio.gather(*[w.stop() for w in self.workers])

        # Then close connectors
        await self.registry.close_all()


class ExecutorWorkerAsync:
    """Async worker that executes operations using Blazing pattern."""

    def __init__(self, worker_id: int, connector_client: ConnectorClient):
        self.worker_id = worker_id
        self.connector_client = connector_client  # For Connector API proxy access

    async def execute_operation(self, operation: Operation) -> Any:
        """Execute operation using Blazing pattern (data via args, services for external)."""

        # Build services with Connector API client
        # Services use the Connector API proxy (credentials stay in Coordinator)
        services = await build_services(self.connector_client)

        # Blazing Pattern: Data comes from args/kwargs, NOT separate datasources!
        # Inject services into kwargs
        kwargs = operation.kwargs.copy()
        kwargs['services'] = services

        # Execute function with args (data) and kwargs (services)
        result = await operation.func(*operation.args, **kwargs)

        return result
```

---

### Services in New Architecture

**Question:** How do services work in the new architecture?

**Answer:** Services work the same way - they are **injected into station/route functions via the `services` parameter**. The difference is WHERE the Connectors live:

- **Current:** Connectors live in coordinator worker threads
- **New:** Connectors live in Coordinator, executor calls via API proxy

```python
# Current Pattern (coordinator-side, connectors in worker thread)
# Service class wraps Connectors
class TimeSeriesService(BaseService):
    def __init__(self, connector_instances):
        self.api_connector = connector_instances.get('TimeSeriesAPI')

    async def fetch_timeseries(self, symbol, points):
        return await self.api_connector.get_data(f"/api/timeseries/{symbol}?points={points}")


# Station uses services (THIS STAYS THE SAME)
@app.station
async def analyze_timeseries(symbol: str, points: int, services=None):
    """Station receives data through args, uses services for external access."""
    # Services provides access to Connectors
    data = await services.timeseries.fetch_timeseries(symbol, points)
    return process_timeseries(data)


# New Architecture: Service internally uses Connector API proxy
# (Internal implementation changes, but station code stays EXACTLY the same)
class TimeSeriesService(BaseService):
    def __init__(self, connector_client: ConnectorClient):
        # Instead of direct connector, uses API client
        self.connector_client = connector_client

    async def fetch_timeseries(self, symbol, points):
        # Calls Coordinator's Connector API proxy instead of direct connector
        return await self.connector_client.fetch(
            connector_name='TimeSeriesAPI',
            method='get',
            url=f'/api/timeseries/{symbol}?points={points}'
        )
```

**Key Point:** Station code DOES NOT CHANGE. The `services` parameter works exactly the same way. Only the internal implementation of Services changes to use the Connector API proxy.

**Benefits:**

- Station code remains unchanged (same `services=None` pattern)
- Routes continue to orchestrate data flow between stations
- Data still passed through args/kwargs (Blazing philosophy preserved)
- Connector credentials stay in Coordinator (security)
- Throttling centralized in Coordinator (consistency)

---

### Throttling in New Architecture

**Current:** Per-connector throttling in coordinator (per-thread)

**New:** Global throttling coordinated via orchestration Redis:

```python
# executor/connectors/throttling.py

class GlobalThrottler:
    """Throttling coordinated across all executor processes."""

    def __init__(self, orchestration_redis: redis.asyncio.Redis):
        self.redis = orchestration_redis

    async def acquire(self, connector_name: str, config: ThrottlingConfig) -> bool:
        """
        Acquire throttle slot (distributed across all executors).

        Uses Redis MULTI/EXEC for atomic check-and-increment.
        """
        key = f"throttle:{connector_name}"

        if config.mode == 'rolling':
            # Rolling window: track timestamps in sorted set
            now = time.time()
            window_start = now - config.window

            async with self.redis.pipeline(transaction=True) as pipe:
                # Remove expired entries
                await pipe.zremrangebyscore(key, 0, window_start)
                # Count current entries
                await pipe.zcard(key)
                # Add current request
                await pipe.zadd(key, {str(now): now})
                # Set expiry
                await pipe.expire(key, int(config.window) + 1)

                results = await pipe.execute()
                current_count = results[1]

            if current_count >= config.limit:
                # Over limit, wait
                await asyncio.sleep(config.window / config.limit)
                return await self.acquire(connector_name, config)

            return True

        elif config.mode == 'fixed':
            # Fixed interval: simple rate limiting
            last_call_key = f"{key}:last"
            last_call = await self.redis.get(last_call_key)

            if last_call:
                elapsed = time.time() - float(last_call)
                min_interval = config.window / config.limit
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

            await self.redis.set(last_call_key, str(time.time()), ex=int(config.window))
            return True
```

---

### Migration Path

**Phase 1:** Keep existing coordinator-side connectors working (current state)
**Phase 2:** Add Connector API proxy endpoints to Coordinator
**Phase 3:** Add executor-side datasource registry (Data Redis, Arrow Flight)
**Phase 4:** Add executor-side connector client (calls Coordinator API proxy)
**Phase 5:** Migrate station functions to use new datasource/connector patterns
**Phase 6:** Remove legacy coordinator-side connector code

```python
# Compatibility layer during migration

class HybridDataAccessLayer:
    """Support both legacy coordinator and new executor data access patterns."""

    def __init__(self, mode: str = 'new'):
        self.mode = mode  # 'legacy', 'new', or 'hybrid'

    async def fetch_data(self, datasource_spec: dict) -> Any:
        ds_type = datasource_spec.get('type')

        if ds_type in ('redis', 'arrow_flight'):
            # Datasources: Executor accesses directly
            return await self._fetch_datasource(datasource_spec)
        elif ds_type == 'connector':
            # Connectors: Executor calls via Coordinator API proxy
            return await self._fetch_via_connector_api(datasource_spec)
        else:
            raise ValueError(f"Unknown datasource type: {ds_type}")

    async def _fetch_datasource(self, spec: dict) -> Any:
        """Direct access to customer's datasources (Data Redis, Arrow Flight)."""
        # ... implementation using RedisDataSource, ArrowFlightDataSource

    async def _fetch_via_connector_api(self, spec: dict) -> Any:
        """Fetch via Coordinator's Connector API proxy."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{COORDINATOR_API}/v1/connectors/{spec['connector_name']}/fetch",
                json={"method": spec['method'], "params": spec['params']},
                headers={"Authorization": f"Bearer {API_TOKEN}"}
            )
            return response.json()["data"]
```

---

## Datasource API Specification

### Design Philosophy

**API-First Approach:** Define the contract between coordinator and executor before implementation. The executor becomes a consumer of well-defined APIs rather than directly accessing Redis/connectors.

**Separation of Concerns:**

| Layer | Responsibility | Access |
|-------|---------------|--------|
| **Coordinator** | Orchestration, routing, status | Orchestration Redis (R/W) |
| **Datasource API** | Data fetching, result storage | Data Redis, Connectors, Arrow Flight |
| **Executor** | Computation only | Datasource API only |

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ API-First Architecture                                                  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Coordinator (Coordinator)                                           │   │
│  │                                                                 │   │
│  │  • Polls orchestration Redis for operations                    │   │
│  │  • Dispatches to executor with operation_id only               │   │
│  │  • Updates operation status                                    │   │
│  │                                                                 │   │
│  │  Access: Orchestration Redis (R/W)                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              │ operation_id                             │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Executor Process                                                │   │
│  │                                                                 │   │
│  │  1. GET  /v1/data/operations/{id}/args      → Fetch args       │   │
│  │  2. GET  /v1/data/operations/{id}/kwargs    → Fetch kwargs     │   │
│  │  3. GET  /v1/data/operations/{id}/function  → Fetch function   │   │
│  │  4. GET  /v1/data/datasources/{name}        → Fetch datasource │   │
│  │  5. Execute function(args, kwargs, datasources)                │   │
│  │  6. POST /v1/data/operations/{id}/result    → Store result     │   │
│  │                                                                 │   │
│  │  Access: Datasource API only (no direct Redis)                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Datasource API (FastAPI Service)                                │   │
│  │                                                                 │   │
│  │  • Abstracts all data access behind REST endpoints             │   │
│  │  • Manages connector pools (shared across requests)            │   │
│  │  • Handles serialization/deserialization                       │   │
│  │  • Enforces access controls (read-only PostgreSQL)             │   │
│  │                                                                 │   │
│  │  Access: Data Redis (R/W), Connectors, Arrow Flight            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### API Endpoints

#### 1. Operation Data Endpoints

**GET /v1/data/operations/{operation_id}/args**

Fetch operation arguments.

```yaml
Path Parameters:
  operation_id: string (ULID)

Response 200:
  Content-Type: application/json OR application/x-arrow-ipc
  Body:
    data: any              # Deserialized args
    format: string         # "json" | "arrow" | "pickle"
    dimensions: string     # "scalar" | "1D" | "2D" | etc.

Response 404:
  Body: { "error": "Operation not found" }

Response 410:
  Body: { "error": "Args already consumed" }  # If read_status == "consumed"
```

**GET /v1/data/operations/{operation_id}/kwargs**

Fetch operation keyword arguments.

```yaml
Path Parameters:
  operation_id: string (ULID)

Response 200:
  Content-Type: application/json
  Body:
    data: object           # Deserialized kwargs dict
    format: string
    dimensions: string

Response 404/410: Same as args
```

**GET /v1/data/operations/{operation_id}/function**

Fetch serialized function for execution.

```yaml
Path Parameters:
  operation_id: string (ULID)

Response 200:
  Content-Type: application/json
  Body:
    serialized_function: string    # Base64-encoded dill pickle
    function_signature: string     # Human-readable signature
    station_name: string
    station_type: string           # "BLOCKING" | "NON-BLOCKING"

Response 404:
  Body: { "error": "Operation or station not found" }
```

**POST /v1/data/operations/{operation_id}/result**

Store operation result.

```yaml
Path Parameters:
  operation_id: string (ULID)

Request:
  Content-Type: application/json OR application/x-arrow-ipc
  Body:
    data: any              # Result to store
    format: string         # "json" | "arrow" | "pickle"

Response 204: No Content (success)

Response 404:
  Body: { "error": "Operation not found" }

Response 409:
  Body: { "error": "Result already stored" }
```

**GET /v1/data/operations/{operation_id}/result**

Fetch operation result (for downstream operations).

```yaml
Path Parameters:
  operation_id: string (ULID)

Response 200:
  Content-Type: application/json OR application/x-arrow-ipc
  Body:
    data: any
    format: string
    dimensions: string

Response 404:
  Body: { "error": "Operation not found" }

Response 425:
  Body: { "error": "Result not yet available" }
```

---

#### 2. Datasource Endpoints

**GET /v1/data/datasources/{datasource_name}**

Fetch data from a declared datasource.

```yaml
Path Parameters:
  datasource_name: string

Query Parameters:
  operation_id: string     # For context/caching
  params: JSON string      # Datasource-specific parameters

Response 200:
  Content-Type: application/json OR application/x-arrow-ipc
  Body:
    data: any              # Fetched data
    format: string
    source: string         # "redis" | "arrow_flight" | "rest" | "postgres"
    cached: boolean        # Whether result was from cache

Response 404:
  Body: { "error": "Datasource not found" }

Response 502:
  Body: { "error": "Upstream datasource error", "details": "..." }
```

**POST /v1/data/datasources/{datasource_name}**

Write data to a datasource (if permitted).

```yaml
Path Parameters:
  datasource_name: string

Request:
  Content-Type: application/json OR application/x-arrow-ipc
  Body:
    data: any
    key: string            # For Redis: the key to write
    params: object         # Datasource-specific parameters

Response 204: No Content (success)

Response 403:
  Body: { "error": "Datasource is read-only" }  # e.g., PostgreSQL

Response 404:
  Body: { "error": "Datasource not found" }
```

---

#### 3. Connector Endpoints

**GET /v1/data/connectors/{connector_name}/fetch**

Execute a fetch operation via connector.

```yaml
Path Parameters:
  connector_name: string

Query Parameters:
  url: string              # For REST connectors
  query: string            # For SQL connectors (base64-encoded)
  ticket: string           # For Arrow Flight (base64-encoded)

Response 200:
  Content-Type: application/json OR application/x-arrow-ipc
  Body:
    data: any
    format: string
    throttled: boolean     # Whether request was delayed by throttling
    latency_ms: number     # Request latency

Response 404:
  Body: { "error": "Connector not found" }

Response 429:
  Body: { "error": "Rate limited", "retry_after": 1.5 }

Response 502:
  Body: { "error": "Upstream error", "details": "..." }
```

**POST /v1/data/connectors/{connector_name}/execute**

Execute a write/mutation operation via connector (if permitted).

```yaml
Path Parameters:
  connector_name: string

Request:
  Content-Type: application/json
  Body:
    operation: string      # "insert" | "update" | "delete" | "put"
    params: object         # Connector-specific parameters

Response 200:
  Content-Type: application/json
  Body:
    affected: number       # Rows/items affected
    result: any            # Operation-specific result

Response 403:
  Body: { "error": "Connector is read-only" }

Response 404:
  Body: { "error": "Connector not found" }
```

---

#### 4. Cache Endpoints

**GET /v1/data/cache/{key}**

Read from executor-accessible cache (Data Redis).

```yaml
Path Parameters:
  key: string (URL-encoded)

Response 200:
  Content-Type: application/json
  Body:
    value: any
    ttl: number            # Remaining TTL in seconds, or -1 if no expiry

Response 404:
  Body: { "error": "Key not found" }
```

**PUT /v1/data/cache/{key}**

Write to executor-accessible cache.

```yaml
Path Parameters:
  key: string (URL-encoded)

Request:
  Content-Type: application/json
  Body:
    value: any
    ttl: number            # Optional TTL in seconds

Response 204: No Content (success)
```

**DELETE /v1/data/cache/{key}**

Delete from cache.

```yaml
Path Parameters:
  key: string (URL-encoded)

Response 204: No Content (success, even if key didn't exist)
```

---

#### 5. Batch Endpoints (Performance Optimization)

**POST /v1/data/operations/{operation_id}/context**

Fetch all operation context in one request (args + kwargs + function + datasources).

```yaml
Path Parameters:
  operation_id: string (ULID)

Request:
  Content-Type: application/json
  Body:
    include_args: boolean      # Default: true
    include_kwargs: boolean    # Default: true
    include_function: boolean  # Default: true
    datasources: [string]      # List of datasource names to prefetch

Response 200:
  Content-Type: application/json
  Body:
    args:
      data: any
      format: string
    kwargs:
      data: object
      format: string
    function:
      serialized_function: string
      function_signature: string
      station_name: string
    datasources:
      {datasource_name}:
        data: any
        format: string
        source: string

Response 404:
  Body: { "error": "Operation not found" }
```

**POST /v1/data/batch/fetch**

Batch fetch multiple datasources in parallel.

```yaml
Request:
  Content-Type: application/json
  Body:
    requests:
      - datasource: string
        params: object
      - connector: string
        url: string
      - cache_key: string

Response 200:
  Content-Type: application/json
  Body:
    results:
      - success: boolean
        data: any
        error: string (if failed)
      - ...
    total_latency_ms: number
```

---

### OpenAPI Specification

```yaml
openapi: 3.0.3
info:
  title: Blazing Datasource API
  description: |
    API for executor processes to access datasources, operation data,
    and caching without direct Redis/connector access.
  version: 1.0.0

servers:
  - url: http://localhost:8001
    description: Local development
  - url: https://data.blazing.io
    description: Production

security:
  - BearerAuth: []

paths:
  /v1/data/operations/{operation_id}/args:
    get:
      summary: Fetch operation arguments
      tags: [Operations]
      parameters:
        - name: operation_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Arguments retrieved
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DataResponse'
            application/x-arrow-ipc:
              schema:
                type: string
                format: binary

  /v1/data/operations/{operation_id}/kwargs:
    get:
      summary: Fetch operation keyword arguments
      tags: [Operations]
      parameters:
        - name: operation_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Kwargs retrieved
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DataResponse'

  /v1/data/operations/{operation_id}/function:
    get:
      summary: Fetch serialized function
      tags: [Operations]
      parameters:
        - name: operation_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Function retrieved
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FunctionResponse'

  /v1/data/operations/{operation_id}/result:
    get:
      summary: Fetch operation result
      tags: [Operations]
      parameters:
        - name: operation_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Result retrieved
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DataResponse'
    post:
      summary: Store operation result
      tags: [Operations]
      parameters:
        - name: operation_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DataRequest'
      responses:
        '204':
          description: Result stored

  /v1/data/operations/{operation_id}/context:
    post:
      summary: Batch fetch operation context
      tags: [Operations, Batch]
      parameters:
        - name: operation_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ContextRequest'
      responses:
        '200':
          description: Context retrieved
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ContextResponse'

  /v1/data/datasources/{datasource_name}:
    get:
      summary: Fetch from datasource
      tags: [Datasources]
      parameters:
        - name: datasource_name
          in: path
          required: true
          schema:
            type: string
        - name: operation_id
          in: query
          schema:
            type: string
        - name: params
          in: query
          schema:
            type: string
      responses:
        '200':
          description: Data retrieved
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DatasourceResponse'
    post:
      summary: Write to datasource
      tags: [Datasources]
      parameters:
        - name: datasource_name
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DatasourceWriteRequest'
      responses:
        '204':
          description: Data written
        '403':
          description: Datasource is read-only

  /v1/data/connectors/{connector_name}/fetch:
    get:
      summary: Fetch via connector
      tags: [Connectors]
      parameters:
        - name: connector_name
          in: path
          required: true
          schema:
            type: string
        - name: url
          in: query
          schema:
            type: string
        - name: query
          in: query
          schema:
            type: string
        - name: ticket
          in: query
          schema:
            type: string
      responses:
        '200':
          description: Data fetched
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ConnectorResponse'
        '429':
          description: Rate limited

  /v1/data/cache/{key}:
    get:
      summary: Read from cache
      tags: [Cache]
      parameters:
        - name: key
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Value retrieved
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CacheResponse'
        '404':
          description: Key not found
    put:
      summary: Write to cache
      tags: [Cache]
      parameters:
        - name: key
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CacheWriteRequest'
      responses:
        '204':
          description: Value stored
    delete:
      summary: Delete from cache
      tags: [Cache]
      parameters:
        - name: key
          in: path
          required: true
          schema:
            type: string
      responses:
        '204':
          description: Key deleted

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

  schemas:
    DataResponse:
      type: object
      properties:
        data:
          description: The actual data (any JSON type)
        format:
          type: string
          enum: [json, arrow, pickle]
        dimensions:
          type: string
          example: "2D"

    DataRequest:
      type: object
      required: [data]
      properties:
        data:
          description: Data to store
        format:
          type: string
          enum: [json, arrow, pickle]
          default: json

    FunctionResponse:
      type: object
      properties:
        serialized_function:
          type: string
          description: Base64-encoded dill pickle
        function_signature:
          type: string
          example: "(x: int, y: int) -> int"
        station_name:
          type: string
        station_type:
          type: string
          enum: [BLOCKING, NON-BLOCKING]

    ContextRequest:
      type: object
      properties:
        include_args:
          type: boolean
          default: true
        include_kwargs:
          type: boolean
          default: true
        include_function:
          type: boolean
          default: true
        datasources:
          type: array
          items:
            type: string

    ContextResponse:
      type: object
      properties:
        args:
          $ref: '#/components/schemas/DataResponse'
        kwargs:
          $ref: '#/components/schemas/DataResponse'
        function:
          $ref: '#/components/schemas/FunctionResponse'
        datasources:
          type: object
          additionalProperties:
            $ref: '#/components/schemas/DatasourceResponse'

    DatasourceResponse:
      type: object
      properties:
        data:
          description: Fetched data
        format:
          type: string
        source:
          type: string
          enum: [redis, arrow_flight, rest, postgres]
        cached:
          type: boolean

    DatasourceWriteRequest:
      type: object
      required: [data]
      properties:
        data:
          description: Data to write
        key:
          type: string
          description: For Redis - the key to write
        params:
          type: object
          description: Datasource-specific parameters

    ConnectorResponse:
      type: object
      properties:
        data:
          description: Fetched data
        format:
          type: string
        throttled:
          type: boolean
        latency_ms:
          type: number

    CacheResponse:
      type: object
      properties:
        value:
          description: Cached value
        ttl:
          type: integer
          description: Remaining TTL in seconds (-1 if no expiry)

    CacheWriteRequest:
      type: object
      required: [value]
      properties:
        value:
          description: Value to cache
        ttl:
          type: integer
          description: TTL in seconds
```

---

### Implementation Strategy

**Phase 1: Implement Datasource API alongside existing architecture**

```python
# src/blazing_service/datasource_api.py

from fastapi import FastAPI, HTTPException, Depends
from blazing_service.data_access import OperationDAO, StationDAO, ConnectorDAO
from blazing_service.engine.runtime import Connectors

datasource_app = FastAPI(title="Blazing Datasource API", version="1.0.0")

# Shared connector registry (initialized once)
_connector_registry: Dict[str, Any] = {}

@datasource_app.on_event("startup")
async def initialize_connectors():
    """Initialize shared connector pool on API startup."""
    global _connector_registry
    _connector_registry = await Connectors.fetch_all_connectors()


@datasource_app.get("/v1/data/operations/{operation_id}/args")
async def get_operation_args(operation_id: str):
    """Fetch operation arguments."""
    try:
        operation = await OperationDAO.get(operation_id)
        if operation.args_read_status == "consumed":
            raise HTTPException(410, "Args already consumed")

        args = await OperationDAO._get_args(operation_id)
        return {
            "data": args,
            "format": operation.args_data_format or "json",
            "dimensions": operation.args_dimensions or "unknown"
        }
    except Exception as e:
        raise HTTPException(404, f"Operation not found: {e}")


@datasource_app.get("/v1/data/operations/{operation_id}/function")
async def get_operation_function(operation_id: str):
    """Fetch serialized function for execution."""
    try:
        operation = await OperationDAO.get(operation_id)
        station = await StationDAO.get(operation.station_pk)

        return {
            "serialized_function": station.serialized_function,
            "function_signature": station.function_signature,
            "station_name": station.name,
            "station_type": station.station_type
        }
    except Exception as e:
        raise HTTPException(404, f"Operation or station not found: {e}")


@datasource_app.post("/v1/data/operations/{operation_id}/result")
async def store_operation_result(operation_id: str, request: DataRequest):
    """Store operation result."""
    try:
        await OperationDAO.set_result(
            operation_id,
            request.data,
            grpc_address=None,  # Determined by API
            ipc_address=None
        )
        return Response(status_code=204)
    except Exception as e:
        raise HTTPException(500, f"Failed to store result: {e}")


@datasource_app.get("/v1/data/connectors/{connector_name}/fetch")
async def connector_fetch(
    connector_name: str,
    url: Optional[str] = None,
    query: Optional[str] = None
):
    """Fetch data via connector."""
    if connector_name not in _connector_registry:
        raise HTTPException(404, f"Connector '{connector_name}' not found")

    connector = _connector_registry[connector_name]
    start_time = time.time()

    try:
        if hasattr(connector, 'get_data') and url:
            # REST connector
            data = await connector.get_data(url)
        elif hasattr(connector, 'execute_query') and query:
            # SQL connector
            data = await connector.execute_query(base64.b64decode(query).decode())
        else:
            raise HTTPException(400, "Invalid parameters for connector type")

        return {
            "data": data,
            "format": "json",
            "throttled": False,
            "latency_ms": (time.time() - start_time) * 1000
        }
    except Exception as e:
        raise HTTPException(502, f"Upstream error: {e}")
```

**Phase 2: Executor uses API instead of direct access**

```python
# executor/client.py

class DatasourceClient:
    """Client for Datasource API used by executor."""

    def __init__(self, api_url: str, api_token: str):
        self.api_url = api_url
        self.headers = {"Authorization": f"Bearer {api_token}"}
        self.session = httpx.AsyncClient(timeout=30)

    async def get_operation_context(
        self,
        operation_id: str,
        datasources: List[str] = None
    ) -> OperationContext:
        """Batch fetch all operation context in one request."""
        response = await self.session.post(
            f"{self.api_url}/v1/data/operations/{operation_id}/context",
            headers=self.headers,
            json={
                "include_args": True,
                "include_kwargs": True,
                "include_function": True,
                "datasources": datasources or []
            }
        )
        response.raise_for_status()
        return OperationContext(**response.json())

    async def store_result(self, operation_id: str, result: Any) -> None:
        """Store operation result."""
        response = await self.session.post(
            f"{self.api_url}/v1/data/operations/{operation_id}/result",
            headers=self.headers,
            json={"data": result, "format": "json"}
        )
        response.raise_for_status()

    async def fetch_datasource(
        self,
        datasource_name: str,
        params: dict = None
    ) -> Any:
        """Fetch from a datasource."""
        response = await self.session.get(
            f"{self.api_url}/v1/data/datasources/{datasource_name}",
            headers=self.headers,
            params={"params": json.dumps(params or {})}
        )
        response.raise_for_status()
        return response.json()["data"]
```

---

### Security Considerations

1. **JWT Validation:** All endpoints require valid JWT with `app_id` claim
2. **Operation Isolation:** Executor can only access operations for its `app_id`
3. **Connector Access Control:** Connectors scoped to customer's app_id
4. **Read-Only Enforcement:** PostgreSQL datasources always read-only
5. **Rate Limiting:** Per-customer rate limits on API endpoints

---

### Performance Optimizations

1. **Batch Context Endpoint:** Single request fetches args + kwargs + function + datasources
2. **Connection Pooling:** API maintains shared connector pools
3. **Response Caching:** LRU cache for frequently accessed datasources
4. **Arrow IPC:** Binary format for large data transfers (zero-copy)
5. **Streaming:** Large results streamed rather than buffered

---

## Implementation Phases

### Phase 0: Foundation & SaaS Infrastructure (Week 1)

**Goal:** Set up SaaS multi-tenancy, two-Redis architecture, datasource infrastructure

**Tasks:**

1. **Two-Redis Architecture Setup**
   ```yaml
   # docker-compose.yml
   services:
     orchestration-redis:
       image: redis:7-alpine
       # Managed by Blazing, shared state

     data-redis:
       image: redis:7-alpine
       command: redis-server --appendonly yes --acl-file /etc/redis/acl.conf
       volumes:
         - ./redis-acl.conf:/etc/redis/acl.conf:ro
       # Customer-owned data, read-only for executors

   # redis-acl.conf (enforces read-only for executors)
   user executor_user on >executor_password ~* -@all +@read
   ```

2. **Update DAOs for Datasources**
   ```python
   # src/blazing_service/data_access/data_access.py

   class StationDAO(HashModel):
       # Existing fields
       pk: str
       name: str
       serialized_function: str
       environment_spec: Optional[str] = None

       # NEW: Datasource specifications
       datasources: Optional[str] = None  # JSON-serialized

   class OperationDAO(HashModel):
       # Existing fields
       pk: str
       station_pk: str
       unit_pk: str
       status: str

       # NEW: Datasource specs for this operation
       datasources: Optional[str] = None  # JSON-serialized
   ```

3. **Update Client API**
   ```python
   # src/blazing/blazing.py

   class Blazing:
       def station(self, datasources: Optional[Dict[str, str]] = None):
           """
           Define a station with optional datasources.

           Args:
               datasources: Dict mapping names to URLs
                   {
                       'events': 'redis://data-redis:6379/events',
                       'sensors': 'arrow_flight://arrow:8815/sensors'
                   }
           """
           def decorator(func):
               # Parse datasources
               datasources_spec = self._parse_datasources(datasources or {})

               # Store in station registration
               self._stations.append({
                   'name': func.__name__,
                   'serialized_function': base64.b64encode(dill.dumps(func)),
                   'environment_spec': json.dumps(self._environment_spec),
                   'datasources': json.dumps(datasources_spec)  # NEW
               })
               return func
           return decorator

       def _parse_datasources(self, datasources: Dict[str, str]) -> Dict:
           """Parse datasource URLs into structured specs."""
           specs = {}
           for name, url in datasources.items():
               if url.startswith('redis://'):
                   specs[name] = self._parse_redis_url(url)
               elif url.startswith('arrow_flight://'):
                   specs[name] = self._parse_arrow_flight_url(url)
               elif url.startswith('postgresql://'):
                   specs[name] = self._parse_postgres_url(url)
           return specs
   ```

4. **Baseline Testing**
   ```python
   # tests/test_phase0_baseline.py

   async def test_two_redis_architecture():
       """Test orchestration Redis separate from data Redis."""
       pass

   async def test_data_reference_resolution():
       """Test executor resolves redisindirect| and arrow| references."""
       pass

   async def test_blazing_args_kwargs_pattern():
       """Test data flows through args/kwargs, services for Connectors."""
       pass
   ```

**Deliverables:**
- ✅ Two-Redis architecture deployed
- ✅ Data reference resolution working (redisindirect|, arrow|)
- ✅ Blazing pattern enforced (args/kwargs, services)
- ✅ Backward compatible

---

### Phase 1: Executor Data Fetching Layer (Week 2)

**Goal:** Implement data fetching clients inside executor with pooling and caching

**Tasks:**

1. **Create Executor Data Fetching Module**
   ```
   src/blazing_service/executor/
   ├── __init__.py
   ├── executor_process.py       # Main executor
   ├── data_fetching/
   │   ├── __init__.py
   │   ├── redis_client.py        # Async Redis with pooling
   │   ├── arrow_flight_client.py # Async Arrow Flight
   │   ├── postgres_client.py     # Async PostgreSQL (future)
   │   ├── connection_pool.py     # Generic connection pooling
   │   └── lru_cache.py           # LRU cache with TTL
   ```

2. **Implement Async Redis Client with Pooling**
   ```python
   # src/blazing_service/executor/data_fetching/redis_client.py

   import aredis
   from typing import Optional

   class ExecutorRedisClient:
       """Async Redis client with connection pooling (30x speedup)."""

       def __init__(self, data_redis_url: str, pool_size: int = 10):
           self.pool = aredis.ConnectionPool.from_url(
               data_redis_url,
               max_connections=pool_size,
               decode_responses=False  # Get bytes for zero-copy
           )
           self.client = aredis.StrictRedis(connection_pool=self.pool)

       async def get(self, key: str) -> Optional[bytes]:
           """Fetch data from Redis (read-only)."""
           return await self.client.get(key)

       async def hgetall(self, key: str) -> dict:
           """Fetch hash from Redis (read-only)."""
           return await self.client.hgetall(key)
   ```

3. **Implement Async Arrow Flight Client**
   ```python
   # src/blazing_service/executor/data_fetching/arrow_flight_client.py

   import pyarrow.flight as flight
   from typing import Dict

   class ExecutorArrowFlightClient:
       """Async Arrow Flight client using PyArrow as_async()."""

       def __init__(self):
           self.clients: Dict[str, flight.FlightClient] = {}

       async def fetch_table(self, endpoint: str, port: int, path: str):
           """Fetch Arrow table from Flight server."""
           # Create or reuse client
           location = flight.Location.for_grpc_tcp(endpoint, port)

           if location not in self.clients:
               self.clients[location] = flight.FlightClient(location)

           # Use async API (PyArrow as_async)
           client = self.clients[location]
           async_client = client.as_async()

           # Fetch table
           ticket = flight.Ticket(path.encode())
           stream = await async_client.do_get(ticket)
           table = await stream.read_all()

           return table
   ```

4. **Implement LRU Cache with TTL**
   ```python
   # src/blazing_service/executor/data_fetching/lru_cache.py

   from collections import OrderedDict
   import time

   class LRUCache:
       """LRU cache with TTL (150x speedup on hits)."""

       def __init__(self, max_size: int = 1000, ttl: int = 300):
           self.max_size = max_size
           self.ttl = ttl  # 5 minutes
           self.cache = OrderedDict()

       def get(self, key: str):
           """Get cached value if not expired."""
           if key not in self.cache:
               return None

           value, timestamp = self.cache[key]

           # Check TTL
           if time.time() - timestamp > self.ttl:
               del self.cache[key]
               return None

           # Move to end (LRU)
           self.cache.move_to_end(key)
           return value

       def set(self, key: str, value):
           """Set cached value."""
           # Evict oldest if full
           if len(self.cache) >= self.max_size:
               self.cache.popitem(last=False)

           self.cache[key] = (value, time.time())
   ```

5. **Integrate into ExecutorProcess**
   ```python
   # src/blazing_service/executor/executor_process.py

   class ExecutorProcess:
       def __init__(self, data_redis_url: str):
           # Data fetching clients (for resolving references)
           self.redis_client = ExecutorRedisClient(data_redis_url, pool_size=10)
           self.arrow_client = ExecutorArrowFlightClient()

           # LRU cache (1GB max, 5 min TTL)
           self.cache = LRUCache(max_size=1000, ttl=300)

       async def resolve_all_references(self, args: list, kwargs: dict) -> tuple:
           """Resolve all data references in args/kwargs in parallel.

           Blazing Pattern: Data comes via args/kwargs, NOT magic variables.
           References (redisindirect|, arrow|) are resolved to actual data.
           """
           # Resolve args in parallel
           resolved_args = await asyncio.gather(*[
               self.resolve_data_reference(arg) for arg in args
           ])

           # Resolve kwargs in parallel (except services)
           resolved_kwargs = {}
           tasks = []
           keys = []
           for key, value in kwargs.items():
               if key != 'services':
                   keys.append(key)
                   tasks.append(self.resolve_data_reference(value))

           if tasks:
               resolved_values = await asyncio.gather(*tasks)
               resolved_kwargs = dict(zip(keys, resolved_values))

           # Copy services as-is (built separately)
           if 'services' in kwargs:
               resolved_kwargs['services'] = kwargs['services']

           return list(resolved_args), resolved_kwargs

       async def resolve_data_reference(self, value):
           """Resolve single data reference with caching."""
           if not isinstance(value, str):
               return value

           # Check cache first
           cached = self.cache.get(value)
           if cached:
               return cached

           # Resolve based on prefix
           if value.startswith('redisindirect|'):
               pk = value[len('redisindirect|'):]
               data = await self.redis_client.get(pk)
           elif value.startswith('arrow|'):
               ref = value[len('arrow|'):]
               endpoint, rest = ref.split(':', 1)
               port_str, path = rest.split('/', 1)
               data = await self.arrow_client.fetch_table(endpoint, int(port_str), path)
           else:
               return value  # Small data passed inline

           # Cache and return
           self.cache.set(value, data)
           return data
   ```

6. **Unit Tests**
   ```python
   # tests/test_executor_data_fetching.py

   async def test_redis_client_connection_pooling():
       """Test Redis client reuses connections (30x speedup)."""
       pass

   async def test_arrow_flight_client_async():
       """Test Arrow Flight client uses async API."""
       pass

   async def test_lru_cache_hit():
       """Test cache returns data without refetching (150x speedup)."""
       pass

   async def test_parallel_reference_resolution():
       """Test multiple data references resolved concurrently."""
       pass
   ```

**Deliverables:**
- ✅ Async Redis client with connection pooling
- ✅ Async Arrow Flight client (PyArrow as_async)
- ✅ LRU cache with TTL
- ✅ Parallel reference resolution (redisindirect|, arrow|)
- ✅ Unit tests (>90% coverage)

---

### Phase 2: Pyron-like Executor Backend (Week 3)

**Goal:** Implement JSON/HTTP interface for coordinator → executor communication (inspired by Pyron)

**Key Insight:** Use simple JSON/HTTP instead of shared memory IPC. This is:

- Debuggable (can inspect requests/responses)
- Works across Docker containers
- Proven pattern (same as Pyron)
- No multiprocessing complexity

**Tasks:**

1. **Implement BlazingExecutorBackend** (Pyron-like interface for workers)

   ```python
   # src/blazing_service/executor/executor_backend.py

   class BlazingExecutorBackend:
       """Pyron-like interface for sending operations to executor container."""

       def __init__(self, executor_url: str = 'http://executor:8000', timeout: int = 300):
           self.executor_url = executor_url
           self.timeout = timeout
           self.client = httpx.AsyncClient(base_url=executor_url, timeout=timeout)

       async def execute_async(
           self,
           operation_id: str,
           serialized_function: str,
           args_address: str,
           kwargs_address: str
       ) -> ExecutionResult:
           """Send operation to executor, poll for completion.

           Args:
               operation_id: Operation ULID
               serialized_function: Base64-encoded dill pickle
               args_address: Address for args ('redis', 'RedisIndirect|pk', 'arrow|...')
               kwargs_address: Address for kwargs

           Returns:
               ExecutionResult with success/result/error
           """
           # Submit task
           task_id = str(uuid.uuid4())
           response = await self.client.post('/execute', json={
               'task_id': task_id,
               'operation_id': operation_id,
               'serialized_function': serialized_function,
               'args_address': args_address,
               'kwargs_address': kwargs_address,
           })

           if not response.json().get('accepted'):
               return ExecutionResult(success=False, error='Task rejected')

           # Poll for completion (with exponential backoff)
           poll_interval = 0.1
           elapsed = 0
           while elapsed < self.timeout:
               await asyncio.sleep(poll_interval)
               elapsed += poll_interval

               status = await self.client.get(f'/status/{task_id}')
               status_data = status.json()

               if status_data['status'] == 'completed':
                   return ExecutionResult(
                       success=True,
                       result=status_data.get('result'),
                       elapsed_time=status_data.get('elapsed_time')
                   )
               elif status_data['status'] == 'failed':
                   return ExecutionResult(success=False, error=status_data.get('error'))

               poll_interval = min(poll_interval * 1.5, 2.0)

           return ExecutionResult(success=False, error='Timeout')
   ```

2. **Worker Integration**

   ```python
   # In WorkerAsync (runtime.py)

   async def execute_operation(self, operation_pk: str):
       operation_dao = await OperationDAO.get(operation_pk)
       station_dao = await StationDAO.get(operation_dao.station_pk)

       # Send to executor via Pyron-like interface
       result = await self.executor_backend.execute_async(
           operation_id=operation_pk,
           serialized_function=station_dao.serialized_function,
           args_address=operation_dao.args_address,
           kwargs_address=operation_dao.kwargs_address,
       )

       # Store result
       if result.success:
           await OperationDAO.set_result(operation_pk, result.result, ...)
   ```

**Deliverables:**

- ✅ BlazingExecutorBackend (Pyron-like interface)
- ✅ Worker integration
- ✅ Unit tests

---

### Phase 3: Executor Container Service (Week 4)

**Goal:** FastAPI service running inside executor container that uses `get_data()` to resolve addresses

**Key Insight:** The executor uses the EXISTING `get_data()` from `data_access.py` to resolve addresses.
No need to reimplement - just call the existing code!

**Tasks:**

1. **Implement Executor Container Service**

   ```python
   # src/blazing_service/executor/executor_service.py

   from fastapi import FastAPI
   from blazing_service.data_access.data_access import OperationDAO
   from blazing_service.util.util import Util
   from blazing_service.restricted_executor import RestrictedExecutor

   app = FastAPI(title="Blazing Executor")
   tasks: Dict[str, dict] = {}  # In-memory task storage

   @app.post("/execute")
   async def execute(request: ExecuteRequest):
       """Accept execution request, return immediately with task_id."""
       task_id = request.task_id
       tasks[task_id] = {'status': 'running', 'started_at': datetime.now()}

       # Run in background
       asyncio.create_task(run_operation(task_id, request))
       return {'accepted': True, 'task_id': task_id}

   @app.get("/status/{task_id}")
   async def get_status(task_id: str):
       """Poll for task completion."""
       task = tasks.get(task_id)
       if not task:
           raise HTTPException(404, "Task not found")
       return task

   @app.get("/health")
   async def health():
       return {'status': 'healthy'}

   async def run_operation(task_id: str, request: ExecuteRequest):
       """Execute operation using get_data() to resolve addresses."""
       try:
           start_time = time.time()

           # 1. Get operation DAO (has address fields)
           operation_dao = await OperationDAO.get(request.operation_id)

           # 2. Use EXISTING get_data() to resolve addresses → actual data
           args = await OperationDAO.get_data(operation_dao, 'args')
           kwargs = await OperationDAO.get_data(operation_dao, 'kwargs')

           # 3. Deserialize function
           func = Util.deserialize_function(request.serialized_function)

           # 4. Execute in RestrictedPython sandbox
           restricted = RestrictedExecutor()
           wrapped_func = restricted.create_restricted_wrapper(func)
           result = await wrapped_func(*args, **kwargs)

           # 5. Store result (uses set_data with binary tree decision)
           await OperationDAO.set_result(
               request.operation_id, result,
               grpc_address=os.getenv('GRPC_ADDRESS'),
               ipc_address=os.getenv('IPC_ADDRESS')
           )

           elapsed = time.time() - start_time
           tasks[task_id] = {
               'status': 'completed',
               'result': result,
               'elapsed_time': elapsed
           }

       except Exception as e:
           tasks[task_id] = {'status': 'failed', 'error': str(e)}
   ```

2. **Dockerfile.executor**

   ```dockerfile
   # docker/Dockerfile.executor
   FROM python:3.13-slim

   WORKDIR /app
   COPY src/blazing_service /app/blazing_service
   COPY pyproject.toml /app/

   RUN pip install --no-cache-dir uvicorn fastapi httpx redis dill

   # Executor only needs: data_access, util, restricted_executor
   ENV REDIS_URL=redis://redis:6379
   ENV DATA_REDIS_URL=redis://data-redis:6380

   EXPOSE 8000
   CMD ["uvicorn", "blazing_service.executor.executor_service:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

3. **Integration Tests**

   ```python
   # tests/test_executor_service.py

   async def test_executor_resolves_redis_indirect():
       """Test executor uses get_data() to resolve RedisIndirect| addresses."""
       pass

   async def test_executor_resolves_arrow():
       """Test executor uses get_data() to resolve arrow| addresses."""
       pass

   async def test_executor_runs_in_restricted_sandbox():
       """Test dangerous code is blocked by RestrictedExecutor."""
       pass
   ```

**Deliverables:**

- ✅ Executor container service (FastAPI)
- ✅ Uses existing get_data() for address resolution
- ✅ RestrictedPython sandbox integration
- ✅ Dockerfile.executor
- ✅ Integration tests

---

### Phase 4: Coordinator Integration (Week 5)

**Goal:** Coordinator sends ALL operations to isolated executor (Pyodide/Docker)

**Key Principle:** User code (undill) ALWAYS runs in isolated executor - no conditional routing.

**Tasks:**

1. **Modify runtime.py to Send to Executor**

   ```python
   # src/blazing_service/engine/runtime.py

   async def execute_operation(operation_pk: str):
       # ALL user code runs in isolated executor
       # Coordinator never executes deserialized user functions directly

       # 1. Get operation context
       operation_dao = await OperationDAO.get(operation_pk)
       station_dao = await StationDAO.get(operation_dao.station_pk)

       # 2. Send to executor (always - no routing decision needed)
       executor = await get_or_create_executor(station_dao.environment_spec)
       result = await executor.execute({
           'operation_id': operation_pk,
           'serialized_function': station_dao.serialized_function,
           'args_address': operation_dao.args_address,
           'kwargs_address': operation_dao.kwargs_address,
       })

       # 3. Store result
       await OperationDAO.set_result(operation_pk, result)
   ```

2. **Executor Handles ALL Execution**
   - Deserializes function (undill)
   - Resolves data references (RedisIndirect|, arrow|)
   - Executes in RestrictedPython sandbox
   - Returns result to coordinator

**Deliverables:**

- ✅ Coordinator sends ALL operations to executor
- ✅ No user code execution in coordinator
- ✅ Modified runtime.py

---

### Phase 5: Stats Collection and Coordinator Maintenance (Week 6)

**Goal:** Implement independent stats collection and centralized maintenance loop

**Tasks:**

1. **Stats Collection in Executor**
   ```python
   # src/blazing_service/executor/executor_process.py

   async def execute_operation(self, operation_data):
       start_time = time.time()

       # Resolve data references from args/kwargs (Blazing pattern)
       resolve_start = time.time()
       resolved_args, resolved_kwargs = await self.resolve_all_references(
           operation_data['args'], operation_data['kwargs']
       )
       data_resolve_time = time.time() - resolve_start

       # Execute function with resolved args/kwargs
       compute_start = time.time()
       func = operation_data['func']
       result = await func(*resolved_args, **resolved_kwargs)
       compute_time = time.time() - compute_start

       # Collect stats
       stats = {
           'operation_id': operation_data['operation_id'],
           'data_resolve_time': data_resolve_time,
           'compute_time': compute_time,
           'cache_hits': self.cache_hits,  # Track reference resolution cache hits
       }

       # Note: Executor does NOT write directly to orchestration Redis
       # Stats are returned to coordinator, which writes to Redis
       return {'result': result, 'stats': stats}
   ```

2. **Coordinator Maintenance Loop**
   ```python
   # src/blazing_service/engine/runtime.py (coordinator-level)

   async def maintenance_loop():
       """Centralized maintenance loop (Principle 2: Externalized sync)."""
       while True:
           await asyncio.sleep(30)

           # Fetch stats from orchestration Redis
           coordinator_stats = await fetch_coordinator_stats()
           executor_stats = await fetch_executor_stats()

           # Analyze
           avg_fetch_time = mean([s['data_fetch_time'] for s in executor_stats])
           cache_hit_rate = mean([s['cache_hit'] for s in executor_stats])
           coordinator_queue_depth = await get_queue_depth()

           # Rebalance decisions
           if avg_fetch_time > 0.100:
               await increase_executor_pool_size()

           if coordinator_queue_depth > 1000:
               await scale_coordinator_workers()

           # Prevent overwhelming datasources
           total_connections = executor_count * executor_pool_size
           if total_connections > 100:
               await scale_down_executors()
   ```

**Deliverables:**
- ✅ Stats collection in executor
- ✅ Stats pushed to orchestration Redis
- ✅ Coordinator maintenance loop consumes stats
- ✅ Rebalancing working

---

### Phase 6: End-to-End Testing (Week 7)

**Goal:** Comprehensive testing of full system

**Tasks:**

1. **Environment Isolation Tests**
   ```python
   # tests/test_e2e_environment_isolation.py

   async def test_environment_isolation_six_versions():
       """THE KEY TEST: Different six versions work correctly."""
       # Base coordinator: six==1.17.0
       # Executor: six==1.16.0
       # Should pass now! ✅
       pass
   ```

2. **Performance Tests**
   ```python
   # tests/test_e2e_performance.py

   async def test_executor_side_reference_resolution_performance():
       """Test executor-side reference resolution is faster than inline transfer."""
       # Compare: 80ms (resolve references) vs 130ms (inline large data)
       # Improvement: 38% faster
       pass

   async def test_parallel_reference_resolution():
       """Test parallel reference resolution is faster than sequential."""
       # Compare: 50ms (parallel) vs 100ms (sequential)
       # Improvement: 50% faster
       pass

   async def test_cache_hit_speedup():
       """Test LRU cache provides 150x speedup."""
       # First: 80ms, Subsequent: 30ms
       # Improvement: 63% faster
       pass
   ```

**Deliverables:**
- ✅ Environment isolation tests passing
- ✅ Performance benchmarks
- ✅ All existing tests passing

---

## Architectural Decisions (Final)

### Decision 1: Executor-Side Data Reference Resolution

**Chosen:** Executor resolves data references from args/kwargs (Blazing pattern)

**Rationale:**
- Blazing philosophy: Data flows through args/kwargs, NOT magic variables
- Routes orchestrate which stations get called with what data
- Services are injected for external Connector access
- Eliminates data transfer overhead when references are used
- Enables connection pooling (30x speedup)
- Enables LRU caching (150x speedup)

**Implementation:**
- Coordinator sends operation with args/kwargs (data OR references)
- Executor resolves references: `redisindirect|pk` → Data Redis, `arrow|endpoint:port/path` → Arrow Flight
- Small data (<1MB) passed inline in args/kwargs
- Executor maintains async clients with connection pools and LRU cache

---

### Decision 1.1: Data Transfer Decision Tree (Coordinator-Side)

**Chosen:** Coordinator decides how to transfer data to Executor based on size

**Key Insight:** The Coordinator (worker) has full access to **Coordinating Redis**. The Executor does NOT have access to Coordinating Redis (security boundary), but DOES have direct access to **Data Redis** and **Arrow Flight**.

**Reference Prefixes:**
- `redis|pk` = **Coordinating Redis** (Coordinator has direct access, Executor does NOT)
- `redisindirect|pk` = **Data Redis** (Executor has direct access)
- `arrow|endpoint:port/path` = **Arrow Flight** (Executor has direct access)

**Data Transfer Decision Tree (Coordinator-Side):**
```
┌─────────────────────────────────────────────────────────────────┐
│              Coordinator Prepares Operation                     │
│         Has args/kwargs to send to Executor                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              For each value in args/kwargs:                     │
│                    Check data size                              │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────────┐       ┌─────────────────────┐
    │ Small data (<1MB)   │       │ Large data (>1MB)   │
    └────────┬────────────┘       └────────┬────────────┘
             │                             │
             ▼                             ▼
    ┌─────────────────────┐       ┌─────────────────────┐
    │ Store in            │       │ Store in            │
    │ Coordinating Redis  │       │ Data Redis OR       │
    │ using redis|pk      │       │ Arrow Flight        │
    │                     │       │                     │
    │ Transfer inline     │       │ Pass reference:     │
    │ via HTTP/JSON       │       │ redisindirect|pk    │
    │ to Executor         │       │ or arrow|...        │
    └─────────────────────┘       └─────────────────────┘
             │                             │
             ▼                             ▼
    ┌─────────────────────┐       ┌─────────────────────┐
    │ Executor receives   │       │ Executor receives   │
    │ data directly in    │       │ reference, fetches  │
    │ HTTP/JSON payload   │       │ from Data Redis or  │
    │                     │       │ Arrow Flight        │
    │ (no Redis access    │       │ (direct access to   │
    │ needed)             │       │ Data Redis/Arrow)   │
    └─────────────────────┘       └─────────────────────┘
```

**Coordinator-Side Implementation:**
```python
# Coordinator decides transfer method based on size
async def prepare_operation_payload(self, args, kwargs):
    """Prepare args/kwargs for transfer to Executor."""
    prepared_args = []
    for arg in args:
        prepared_args.append(await self.prepare_value(arg))

    prepared_kwargs = {}
    for key, value in kwargs.items():
        prepared_kwargs[key] = await self.prepare_value(value)

    return prepared_args, prepared_kwargs

async def prepare_value(self, value):
    """Decide transfer method based on data size."""
    serialized = dill.dumps(value)
    size = len(serialized)

    if size < 1_000_000:  # <1MB: store in Coordinating Redis, pass inline
        # Coordinator stores in Coordinating Redis (has direct access)
        pk = generate_ulid()
        await self.coordinating_redis.set(f"redis|{pk}", serialized)
        # Pass data inline via HTTP/JSON to Executor
        return value

    else:  # >1MB: store in Data Redis, pass reference
        pk = generate_ulid()
        await self.data_redis.set(pk, serialized)
        # Executor will fetch directly from Data Redis
        return f"redisindirect|{pk}"
```

**Executor-Side Implementation:**
```python
# Executor resolves references (only for large data from Data Redis/Arrow)
async def resolve_data_reference(self, value):
    if not isinstance(value, str):
        return value  # Non-string, use directly (small data inline)

    if value.startswith('redisindirect|'):
        # Large data: fetch from Data Redis (Executor has direct access)
        pk = value[len('redisindirect|'):]
        return await self.data_redis_client.get(pk)

    elif value.startswith('arrow|'):
        # Large data: fetch from Arrow Flight (Executor has direct access)
        ref = value[len('arrow|'):]
        endpoint, rest = ref.split(':', 1)
        port_str, path = rest.split('/', 1)
        return await self.arrow_client.fetch_table(endpoint, int(port_str), path)

    else:
        return value  # Small data passed inline via HTTP/JSON
```

**Result Handling (Executor → Coordinator):**
- Small results (<1MB): Return directly via HTTP/JSON
- Large results (>1MB): Store in Data Redis, return `redisindirect|{result_pk}`
- Coordinator resolves result references before returning to client

---

### Decision 2: Centralized Coordinator-Level Maintenance

**Chosen:** Single maintenance loop at coordinator level

**Rationale:**
- Prevents overwhelming datasource connections
- Centralized global view of system state
- Aligns with Principle 2 (externalized synchronization)

**Implementation:**
- Coordinator pushes stats to orchestration Redis
- Executor pushes stats to orchestration Redis (via coordinator)
- Coordinator consumes stats and makes rebalancing decisions

---

### Decision 3: Two-Redis Architecture

**Chosen:** Orchestration Redis (Blazing-managed) + Data Redis (customer-owned)

**Rationale:**
- Clean separation of concerns
- Executors access customer data with controlled permissions
- Aligns with Principle 1 (user scripts with controlled datasource access)

**Implementation:**
- Orchestration Redis: Operation queues, worker state, station definitions
- Data Redis: Customer application data (read/write for executors)

---

### Decision 4: Controlled Datasource Access

**Chosen:** Executors connect to datasources with tiered access levels

**Rationale:**
- Security: Executors can't corrupt orchestration state
- Flexibility: Executors can write to data Redis for caching, write to Arrow Flight for general datasources
- Safety: PostgreSQL remains read-only via Arrow Flight wrapper
- Aligns with Principle 1 (controlled datasource access)

**Implementation:**
- Data Redis: Read/write access for caching computation results
- Arrow Flight (general): Read/write access for datasources
- Arrow Flight (PostgreSQL wrapper): Read-only access enforced at wrapper level
- Orchestration Redis: No access from executors

---

### Decision 5: REST API for Operation Creation

**Chosen:** Clients use REST API to create operations (not direct Redis access)

**Rationale:**
- SaaS multi-tenancy (JWT authentication, app_id isolation)
- Clean API abstraction
- Easier to monitor and rate-limit

**Implementation:**
- POST /v1/operations creates OperationDAO and enqueues
- Client polls GET /v1/operations/{id} for status/result
- API writes to orchestration Redis

---

## Testing Strategy

### Test Levels

**Level 1: Unit Tests (>90% coverage)**

- Executor data fetching clients
- Connection pooling
- LRU cache
- BlazingExecutorBackend HTTP client
- get_data() address resolution

**Level 2: Integration Tests**

- Worker → Executor JSON/HTTP communication
- Executor fetches data and executes
- Stats collection and pushing

**Level 3: End-to-End Tests**
- Full system with Docker infrastructure
- Environment isolation verification
- Performance benchmarks
- Existing feature compatibility

**Level 4: SaaS Tests**
- Multi-tenant isolation
- Two-Redis architecture
- Read-only access enforcement
- REST API authentication

---

## Rollout Plan

### Phase A: Feature Flag (Week 8)
- Deploy with `COORDINATOR_EXECUTOR_ENABLED=false`
- Test in staging with feature flag ON
- Monitor metrics

### Phase B: Opt-In Beta (Week 9)
- Enable for specific customers with custom dependencies
- Monitor performance and errors
- Gather feedback

### Phase C: Gradual Rollout (Week 10-11)
- 10% → 25% → 50% → 75% → 100%
- Rollback criteria: P95 latency >15%, error rate >1%

### Phase D: Full Production (Week 12)
- Default enabled for all traffic
- Remove feature flag code
- Celebrate! 🎉

---

## Success Metrics

### Functional Metrics
| Metric | Current | Target | Critical |
|--------|---------|--------|----------|
| Environment isolation | ❌ Fails | ✅ 100% pass | YES |
| Test coverage | 85% | >90% | NO |
| Existing tests passing | 100% | 100% | YES |

### Performance Metrics
| Metric | Current (Shared Memory) | Target (Executor Fetches) | Improvement |
|--------|------------------------|--------------------------|-------------|
| 100MB Arrow table | 130ms | 80ms | 38% faster |
| Multiple datasources | 200ms | 90ms | 55% faster |
| Cached data | 130ms | 30ms | 63% faster |

### SaaS Metrics
| Metric | Target | Alert If |
|--------|--------|----------|
| Multi-tenant isolation | 100% | Any leak |
| Read-only enforcement | 100% | Any write |
| API latency P95 | <220ms | >250ms |

---

## Conclusion

This architecture successfully combines:

1. ✅ **True environment isolation** (subprocess execution)
2. ✅ **Executor-side data fetching** (Pyron pattern, zero transfer)
3. ✅ **SaaS multi-tenancy** (two-Redis, JWT auth)
4. ✅ **Guiding principles** (read-only access, externalized sync)
5. ✅ **Optimal performance** (pooling, caching, parallel fetching)
6. ✅ **Clean architecture** (coordinator orchestrates, executor computes)

**Next Steps:**
1. Review and approve this plan
2. Begin Phase 0: Foundation & SaaS infrastructure
3. Gradual implementation over 7 weeks
4. Rollout over 4 weeks
5. Full production deployment

---

**Document Version:** 2.0 (Final)
**Last Updated:** 2025-11-24
**Authors:** Claude Code
**Status:** Ready for Implementation
