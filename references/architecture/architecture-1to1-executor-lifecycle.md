# Architecture: 1:1 Coordinator-Executor Lifecycle Management

## Executive Summary

This document describes the architecture for true 1:1 mapping between coordinator and executor at **every level**, where the coordinator (coordinator) fully manages the lifecycle of its paired executor components. The executor is a "dumb sandboxed muscle" that only follows instructions.

**Key Insight**: Resource initialization happens at the appropriate level, mirroring how the original coordinator worked:
- **Environment replication** → Coordinator level (once, before any processes)
- **Connectors & Services** → Process level (once per process, shared to workers)
- **Function cache** → Process level (shared within process)

All initialization happens in the executor sandbox for security, but is orchestrated by the coordinator.

---

## Design Principles

### 1. Coordinator = Brain
- Makes ALL decisions (what, when, how, scaling)
- Manages executor process lifecycle (create, execute, destroy)
- Polls queues and orchestrates flow
- Has Redis access for state management

### 2. Executor = Dumb Muscle
- Makes NO decisions
- Follows instructions from coordinator
- Executes code in isolated sandbox
- Has NO Redis access (security isolation)
- Maintains process-level caches for performance

### 3. True 1:1 at Every Level

- Each coordinator `Coordinator` owns exactly one `ExecutorEnvironment`
- Each coordinator `WorkerProcess` owns exactly one `ExecutorProcess`
- Each coordinator `WorkerThread` owns exactly one `ExecutorThread`
- Each coordinator `WorkerAsync` owns exactly one `ExecutorAsync`
- Resources initialized at appropriate level, shared down
- Mirrors original architecture where:
  - Environment setup was done once at startup
  - Services/connectors were process-scoped
  - Threads/workers shared parent resources
- Predictable resource utilization and debugging

---

## Original Architecture (Before Executor Split)

```
WorkerProcess (WP:0001)
    │
    ├── _async_init()
    │       ├── Connectors.fetch_all_connectors()  ──► SHARED
    │       └── Services.load_all()               ──► SHARED
    │
    ├── WorkerThread (WT:00)
    │       ├── WorkerAsync (WA:00) ──► Uses shared services/connectors
    │       ├── WorkerAsync (WA:01) ──► Uses shared services/connectors
    │       └── WorkerAsync (WA:02) ──► Uses shared services/connectors
    │
    └── WorkerThread (WT:01) [with free-threading]
            └── WorkerAsync (WA:00) ──► Uses shared services/connectors

Resources initialized ONCE at process level, shared DOWN to all workers.
This is how Python works - processes isolate, threads/async share.
```

---

## Target Architecture (1:1 at Every Level)

```
COORDINATOR                                    EXECUTOR (Sandbox)
═══════════                                    ══════════════════

┌─────────────────────────────────────┐       ┌─────────────────────────────────────┐
│            COORDINATOR                  │       │       ExecutorEnvironment           │
│                                     │       │                                     │
│ _async_init():                      │  1:1  │ Initialized ONCE by Coordinator:        │
│   • Create executor environment ────┼──────►│   • Environment replication         │
│   • Replicate dependencies          │       │   • Package installation            │
│   • Validate environment            │       │   • Bytecode validation             │
│                                     │       │                                     │
│ [BEFORE ANY PROCESSES CREATED]      │       │ [SHARED TO ALL PROCESSES BELOW]     │
└──────────────────┬──────────────────┘       └──────────────────┬──────────────────┘
                   │                                             │
                   │ creates processes                           │ inherits env
                   ▼                                             ▼

┌─────────────────────────────────────┐       ┌─────────────────────────────────────┐
│ WorkerProcess (WP:0001)             │       │ ExecutorProcess-0001                │
│                                     │       │                                     │
│ _async_init():                      │  1:1  │ Initialized by coordinator:         │
│   • Create executor process ────────┼──────►│   • Connectors (once)               │
│   • Initialize connectors           │       │   • Services (once)                │
│   • Initialize services            │       │   • Function cache (process-level)  │
│                                     │       │                                     │
│ executor_backend (HTTP client+pool) │       │ [SHARED TO ALL THREADS BELOW]       │
│                                     │       │                                     │
│ ┌─────────────────────────────────┐ │       │ ┌─────────────────────────────────┐ │
│ │ WorkerThread (WT:00)            │ │  1:1  │ │ ExecutorThread-00               │ │
│ │                                 │ │──────►│ │                                 │ │
│ │  WA:00 ─────────────────────────┼─┼──────►│ │  ExecutorAsync-0 (shared cache) │ │
│ │  WA:01 ─────────────────────────┼─┼──────►│ │  ExecutorAsync-1 (shared cache) │ │
│ │  WA:02 ─────────────────────────┼─┼──────►│ │  ExecutorAsync-2 (shared cache) │ │
│ │                                 │ │       │ │                                 │ │
│ └─────────────────────────────────┘ │       │ └─────────────────────────────────┘ │
│                                     │       │                                     │
│ ┌─────────────────────────────────┐ │       │ ┌─────────────────────────────────┐ │
│ │ WorkerThread (WT:01) [future]   │ │  1:1  │ │ ExecutorThread-01               │ │
│ │                                 │ │──────►│ │                                 │ │
│ │  WA:00 ─────────────────────────┼─┼──────►│ │  ExecutorAsync-3 (shared cache) │ │
│ │  WA:01 ─────────────────────────┼─┼──────►│ │  ExecutorAsync-4 (shared cache) │ │
│ │                                 │ │       │ │                                 │ │
│ └─────────────────────────────────┘ │       │ └─────────────────────────────────┘ │
└─────────────────────────────────────┘       └─────────────────────────────────────┘

┌─────────────────────────────────────┐       ┌─────────────────────────────────────┐
│ WorkerProcess (WP:0002)             │       │ ExecutorProcess-0002                │
│                                     │  1:1  │                                     │
│ executor_backend (HTTP client+pool) │──────►│ Separate caches (process isolated) │
│                                     │       │                                     │
│  WT:00 ─────────────────────────────┼──────►│  ExecutorThread-00                 │
│    WA:00 ───────────────────────────┼──────►│    ExecutorAsync-0 (shared cache)  │
│    WA:01 ───────────────────────────┼──────►│    ExecutorAsync-1 (shared cache)  │
│    WA:02 ───────────────────────────┼──────►│    ExecutorAsync-2 (shared cache)  │
│                                     │       │                                     │
└─────────────────────────────────────┘       └─────────────────────────────────────┘
```

---

## Full Hierarchy (4 Layers with 1:1 Mapping)

```
COORDINATOR SIDE                                      EXECUTOR SIDE (Sandbox)
════════════════                                      ══════════════════════

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                      COORDINATOR                                           │
│                              (Top-level orchestrator)                                  │
│                                                                                        │
│   _async_init():                                                                       │
│     1. Create ExecutorEnvironment ─────────────────────────────────────────────────────┼──┐
│     2. Replicate environment (packages, dependencies)                                  │  │
│     3. Validate bytecode attestations                                                  │  │
│     4. THEN create WorkerProcesses                                                     │  │
│                                                                                        │  │
│   Config: num_processes, num_threads_per_process, pilot_light settings                │  │
└────────────────────────────────────────┬──────────────────────────────────────────────┘  │
                                         │                                                 │
                                         │                              1:1                │
                                         │                               ▼                 │
                                         │               ┌─────────────────────────────────┴───┐
                                         │               │      ExecutorEnvironment            │
                                         │               │                                     │
                                         │               │  COORDINATOR-LEVEL (shared to all):    │
                                         │               │  • Python environment (venv/uv)     │
                                         │               │  • Installed packages               │
                                         │               │  • Validated bytecode               │
                                         │               │  • Security policies                │
                                         │               │                                     │
                                         │               │  [CREATED ONCE, SHARED TO ALL      │
                                         │               │   EXECUTOR PROCESSES BELOW]        │
                                         │               └──────────────────┬──────────────────┘
                                         │                                  │
         ┌───────────────────────────────┼───────────────────────────────┐  │
         │                               │                               │  │
         ▼                               ▼                               ▼  │ inherits env
┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
│ ProcessController   │       │ ProcessController   │       │ ProcessController   │
│ (spawns OS process) │       │ (spawns OS process) │       │ (spawns OS process) │
└──────────┬──────────┘       └──────────┬──────────┘       └──────────┬──────────┘
           │                             │                             │
           ▼                             ▼                             ▼
┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
│ WorkerProcess       │       │ WorkerProcess       │       │ WorkerProcess       │
│ (WP:0000)           │       │ (WP:0001)           │       │ (WP:0002)           │
│                     │       │                     │       │                     │
│ _async_init():      │       │                     │       │                     │
│  • Create Executor  │       │                     │       │                     │
│    Process ─────────┼──┐    │                     │       │                     │
│  • Init connectors  │  │    │                     │       │                     │
│  • Init services   │  │    │                     │       │                     │
│                     │  │    │                     │       │                     │
│ executor_backend    │  │    │ executor_backend    │       │ executor_backend    │
│ (HTTP client+pool)  │  │    │ (HTTP client+pool)  │       │ (HTTP client+pool)  │
│                     │  │    │                     │       │                     │
│ ┌─────────────────┐ │  │    │ ┌─────────────────┐ │       │ ┌─────────────────┐ │
│ │ WorkerThread ───┼─┼──┼────┼─┼─────────────────┼─┼──┐    │ │ WorkerThread    │ │
│ │ (WT:00)         │ │  │    │ │ (WT:00)         │ │  │    │ │ (WT:00)         │ │
│ │                 │ │  │    │ │                 │ │  │    │ │                 │ │
│ │  ┌───────────┐  │ │  │    │ │  ┌───────────┐  │ │  │    │ │  ┌───────────┐  │ │
│ │  │ WA:00     │  │ │  │    │ │  │ WA:00     │  │ │  │    │ │  │ WA:00     │  │ │
│ │  │ WA:01     │  │ │  │    │ │  │ WA:01     │  │ │  │    │ │  │ WA:01     │  │ │
│ │  │ WA:02     │  │ │  │    │ │  │ WA:02     │  │ │  │    │ │  │ WA:02     │  │ │
│ │  └───────────┘  │ │  │    │ │  └───────────┘  │ │  │    │ │  └───────────┘  │ │
│ └─────────────────┘ │  │    │ └─────────────────┘ │  │    │ └─────────────────┘ │
└─────────────────────┘  │    └─────────────────────┘  │    └─────────────────────┘
                         │                             │
                    1:1  │                        1:1  │
                         ▼                             ▼
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│ ExecutorProcess-0               │       │ ExecutorProcess-1 / 2 / ...     │
│ (uses shared environment)       │       │ (uses shared environment)       │
│                                 │       │                                 │
│ PROCESS-LEVEL CACHE:            │       │ PROCESS-LEVEL CACHE:            │
│ • Connectors (initialized once) │       │ • Connectors                    │
│ • Services (initialized once)  │       │ • Services                     │
│ • Function cache                │       │ • Function cache                │
│                                 │       │                                 │
│ ┌─────────────────────────────┐ │       │                                 │
│ │ ExecutorThread-00 (WT:00)   │ │       │ (same structure)                │
│ │                             │ │       │                                 │
│ │  ExecutorAsync-0 (WA:00)    │ │       │                                 │
│ │  ExecutorAsync-1 (WA:01)    │ │       │                                 │
│ │  ExecutorAsync-2 (WA:02)    │ │       │                                 │
│ │                             │ │       │                                 │
│ │ [all share process cache]   │ │       │                                 │
│ └─────────────────────────────┘ │       │                                 │
└─────────────────────────────────┘       └─────────────────────────────────┘
```

---

## Resource Initialization Flow

### Coordinator Side (Full 3-Level Pattern)

```python
class Coordinator:
    async def _async_init(self):
        # 1. Create executor environment (1:1 with Coordinator)
        self.executor_backend = get_executor_backend()
        await self.executor_backend.create_environment()

        # 2. Replicate environment (packages, dependencies)
        await self.executor_backend.replicate_environment(
            packages=self.required_packages,
            requirements=self.requirements_txt,
        )

        # 3. Validate ALL serialized code BEFORE creating processes
        #    This happens in the sandbox - keeps untrusted code out of coordinator
        validation_result = await self.executor_backend.validate_code(
            serialized_functions=self.all_functions,
            serialized_services=self.all_services,
            attestations=self.attestations,
        )
        if not validation_result.valid:
            raise SecurityValidationError(validation_result.violations)

        # 4. NOW create WorkerProcesses (environment is ready)
        for i in range(self.num_processes):
            process = await ProcessController.create(
                executor_backend=self.executor_backend,  # Shared
                ...
            )


class WorkerProcess:
    async def _async_init(self):
        # 1. Create our dedicated executor process (1:1, inherits environment)
        await self.executor_backend.create_process(self.process_id)

        # 2. Initialize connectors in executor (once per process)
        #    Uses validated code from environment
        await self.executor_backend.initialize_connectors(self.process_id)

        # 3. Initialize services in executor (once per process)
        await self.executor_backend.initialize_services(self.process_id)

        # 4. Create worker threads (they inherit executor_backend)
        for i in range(self.num_threads):
            thread = await ThreadController.create(
                executor_backend=self.executor_backend,  # Shared
                process_id=self.process_id,
                ...
            )
```

### Executor Side (3-Level Hierarchy)

```python
# Global environment (one per Coordinator)
_environment: Optional[ExecutorEnvironment] = None


class ExecutorEnvironment:
    """Coordinator-level. Created ONCE, shared to all processes."""

    def __init__(self):
        self.status = "initializing"
        self.validated_functions: Dict[str, bytes] = {}
        self.validated_services: Dict[str, bytes] = {}
        self.security_policy: Dict[str, Any] = {}
        self.processes: Dict[str, ExecutorProcess] = {}

    async def replicate(self, packages: List[str], requirements: str):
        """Install packages in isolated environment (sandboxed)."""
        # pip/uv install in sandbox
        await install_packages(packages, requirements)

    async def validate(self, functions: List[bytes], services: List[bytes],
                       attestations: Dict[str, str]) -> ValidationResult:
        """ALL security validation happens here in the sandbox."""
        violations = []
        for func_bytes in functions:
            # 1. Undill (deserialize)
            func = dill.loads(func_bytes)

            # 2. AST analysis
            ast_violations = analyze_ast(func)
            violations.extend(ast_violations)

            # 3. Bytecode inspection
            bytecode_violations = inspect_bytecode(func)
            violations.extend(bytecode_violations)

            # 4. Import validation
            import_violations = validate_imports(func, self.security_policy)
            violations.extend(import_violations)

            # 5. Attestation verification
            if not verify_attestation(func_bytes, attestations):
                violations.append("Invalid attestation signature")

            if not violations:
                self.validated_functions[hash(func_bytes)] = func_bytes

        return ValidationResult(valid=len(violations) == 0, violations=violations)


class ExecutorProcess:
    """WorkerProcess-level. Holds process-level caches."""

    def __init__(self, process_id: str, environment: ExecutorEnvironment):
        self.process_id = process_id
        self.environment = environment  # Link to parent

        # Process-level caches (shared by all workers in this process)
        self.connectors = None
        self.services = {}
        self.function_cache = {}
        self.wrapped_function_cache = {}

        # Worker pool (all share above caches)
        self.workers: Dict[str, ExecutorWorker] = {}

    async def initialize_connectors(self):
        """Called once by coordinator during process init."""
        # Uses validated code from environment
        self.connectors = await Connectors.fetch_all_connectors()

    async def initialize_services(self):
        """Called once by coordinator during process init."""
        # Deserialize using validated services from environment
        self.services = await load_all_services(
            self.connectors,
            validated_services=self.environment.validated_services,
        )
```

---

## Lifecycle Events

### Environment Lifecycle (Coordinator → ExecutorEnvironment)

| Event | Coordinator Action | Executor Reaction (in sandbox) |
|-------|-------------------|-------------------------------|
| **CREATE_ENV** | `Coordinator._async_init()` calls `POST /environment` | Creates isolated environment |
| **REPLICATE_ENV** | Coordinator sends environment spec | Executor installs packages (pip/uv) |
| **VALIDATE_BYTECODE** | Coordinator sends serialized functions/services | Executor does: AST checks, undill, bytecode validation, attestation verification |
| **DESTROY_ENV** | `Coordinator._stop()` calls `DELETE /environment` | Cleans up environment, all processes |

**Security Note**: ALL validation happens on the executor side:
- AST analysis of deserialized code
- Bytecode inspection
- Import validation
- Signature verification
- This keeps untrusted code OUT of the coordinator

### Process Lifecycle (WorkerProcess → ExecutorProcess)

| Event | Coordinator Action | Executor Reaction (in sandbox) |
|-------|-------------------|-------------------------------|
| **CREATE_PROCESS** | `WorkerProcess._async_init()` calls `POST /processes/{id}` | Creates ExecutorProcess with empty caches |
| **INIT_CONNECTORS** | Coordinator calls `POST /processes/{id}/connectors` | Executor deserializes & validates connectors |
| **INIT_SERVICES** | Coordinator calls `POST /processes/{id}/services` | Executor deserializes, validates, instantiates services |
| **DESTROY_PROCESS** | `WorkerProcess._stop()` calls `DELETE /processes/{id}` | Terminates all threads/asyncs, clears all caches |

### Thread Lifecycle (WorkerThread → ExecutorThread)

| Event | Coordinator Action | Executor Reaction (in sandbox) |
|-------|-------------------|-------------------------------|
| **CREATE_THREAD** | `WorkerThread._async_init()` calls `POST /processes/{pid}/threads/{tid}` | Creates ExecutorThread within process |
| **DESTROY_THREAD** | `WorkerThread._stop()` calls `DELETE /processes/{pid}/threads/{tid}` | Terminates all async workers in thread |

### Async Lifecycle (WorkerAsync → ExecutorAsync)

| Event | Coordinator Action | Executor Reaction (in sandbox) |
|-------|-------------------|-------------------------------|
| **CREATE_ASYNC** | `WorkerAsync._async_init()` calls `POST /processes/{pid}/threads/{tid}/asyncs/{aid}` | Creates ExecutorAsync using process's shared caches |
| **EXECUTE** | WorkerAsync calls `POST /processes/{pid}/threads/{tid}/asyncs/{aid}/execute` | Executor deserializes function (if not cached), executes in sandbox |
| **POLL** | WorkerAsync calls `GET /processes/{pid}/threads/{tid}/asyncs/{aid}/status/{task_id}` | Returns result |
| **DESTROY_ASYNC** | `WorkerAsync._stop()` calls `DELETE /processes/{pid}/threads/{tid}/asyncs/{aid}` | Terminates async worker (caches remain) |

---

## API Design

### Executor Service Endpoints

```
# Environment Lifecycle (Coordinator-level, ONCE before any processes)
POST   /environment                           # Create isolated environment
POST   /environment/replicate                 # Install packages from env spec
POST   /environment/validate                  # Validate serialized code (AST, bytecode, attestations)
DELETE /environment                           # Destroy environment + all processes

# Process Lifecycle (WorkerProcess-level)
POST   /processes/{pid}                       # Create executor process (inherits environment)
POST   /processes/{pid}/connectors            # Deserialize & validate connectors
POST   /processes/{pid}/services             # Deserialize & validate services
DELETE /processes/{pid}                       # Destroy process + all threads/asyncs + caches

# Thread Lifecycle (WorkerThread-level, within process)
POST   /processes/{pid}/threads/{tid}         # Create executor thread
DELETE /processes/{pid}/threads/{tid}         # Destroy thread + all asyncs

# Async Lifecycle (WorkerAsync-level, within thread)
POST   /processes/{pid}/threads/{tid}/asyncs/{aid}          # Create executor async
DELETE /processes/{pid}/threads/{tid}/asyncs/{aid}          # Destroy async

# Task Execution
POST   /processes/{pid}/threads/{tid}/asyncs/{aid}/execute  # Submit task
GET    /processes/{pid}/threads/{tid}/asyncs/{aid}/status/{task_id}  # Poll result

# Health & Metrics
GET    /health                                              # Service health + environment status
GET    /environment/health                                  # Environment health + validation stats
GET    /processes/{pid}/health                              # Process health + cache stats
GET    /processes/{pid}/threads/{tid}/health                # Thread health
GET    /processes/{pid}/threads/{tid}/asyncs/{aid}/health   # Async worker health
```

### Security Validation Flow (All in Executor Sandbox)

```
Coordinator (Coordinator)                    Executor (Sandbox)
─────────────────────                    ──────────────────

1. POST /environment
   {env_spec: {...}}          ────────►  Create isolated venv/container

2. POST /environment/replicate
   {packages: [...],
    requirements: "..."}      ────────►  pip/uv install (sandboxed)
                                         Validate package signatures

3. POST /environment/validate
   {serialized_functions: [...],
    serialized_services: [...],
    attestations: [...]}      ────────►  For each serialized blob:
                                           • Undill (deserialize)
                                           • AST analysis
                                           • Bytecode inspection
                                           • Import validation
                                           • Verify attestation signature

                              ◄────────  {valid: true/false,
                                          violations: [...]}

4. IF valid: proceed to create processes
   IF invalid: reject, don't start
```

---

## Executor Internal Architecture

### Four-Level Structure

```python
@dataclass
class ExecutorEnvironment:
    """
    Coordinator-level environment. Created ONCE, shared by all processes.
    All security validation happens here in the sandbox.
    """

    created_at: datetime
    status: str                             # "initializing", "ready", "failed"

    # Environment (shared by ALL processes)
    python_version: str
    installed_packages: Dict[str, str]      # package -> version
    venv_path: Optional[str]                # Path to isolated venv

    # Validated code registry (after AST/bytecode checks pass)
    validated_functions: Dict[str, bytes]   # func_hash -> validated serialized
    validated_services: Dict[str, bytes]   # name -> validated serialized
    attestations: Dict[str, str]            # hash -> signature

    # Validation results
    validation_errors: List[str]
    security_policy: Dict[str, Any]         # Allowed imports, syscalls, etc.

    # Child processes (all inherit this environment)
    processes: Dict[str, ExecutorProcess]


@dataclass
class ExecutorProcess:
    """
    WorkerProcess-level. Created per coordinator WorkerProcess.
    Inherits environment, has its own caches.
    """

    process_id: str                         # "WP:0001"
    environment: ExecutorEnvironment        # Reference to parent environment
    created_at: datetime

    # Process-level caches (shared by ALL threads/asyncs in this process)
    # Deserialization happens HERE using validated code from environment
    connectors: Any                         # Initialized once
    services: Dict[str, Any]               # name -> service instance
    function_cache: Dict[str, Callable]     # func_hash -> deserialized function
    wrapped_cache: Dict[str, Callable]      # func_hash -> wrapped routing function

    # Threads in this process (all share above caches)
    threads: Dict[str, ExecutorThread]      # thread_id -> thread

    # Metrics
    total_tasks_executed: int
    cache_hits: int
    cache_misses: int


@dataclass
class ExecutorThread:
    """
    WorkerThread-level. Groups async workers within a process.
    Uses parent process's shared caches.
    """

    thread_id: str                          # "WT:00"
    process: ExecutorProcess                # Reference to parent (for cache access)
    created_at: datetime

    # Async workers in this thread
    asyncs: Dict[str, ExecutorAsync]        # async_id -> async worker

    status: str                             # "running", "terminated"


@dataclass
class ExecutorAsync:
    """
    WorkerAsync-level. Uses parent process's shared caches.
    """

    async_id: str                           # "WA:00"
    thread: ExecutorThread                  # Reference to parent thread
    process: ExecutorProcess                # Reference to process (for cache access)

    task_queue: asyncio.Queue
    tasks: Dict[str, TaskStatus]

    status: str                             # "idle", "executing", "terminated"
    tasks_executed: int


# Global state (single environment, multiple processes)
_environment: Optional[ExecutorEnvironment] = None
```

### Async Execution (Uses Shared Cache)

```python
async def _async_loop(executor_async: ExecutorAsync):
    """Async worker loop - uses parent process's shared caches."""
    process = executor_async.process  # Access shared caches via parent

    while executor_async.status != "terminated":
        task_id, request = await executor_async.task_queue.get()

        # Get function from PROCESS-LEVEL cache
        func_hash = _get_function_hash(request.serialized_function)

        if func_hash in process.function_cache:
            func = process.function_cache[func_hash]
            process.cache_hits += 1
        else:
            func = deserialize_function(request.serialized_function)
            process.function_cache[func_hash] = func
            process.cache_misses += 1

        # Execute with PROCESS-LEVEL services
        result = await execute_with_services(
            func,
            request.args,
            services=process.services,  # Shared
            connectors=process.connectors,  # Shared
        )

        executor_async.tasks[task_id] = result
```

---

## Cache Benefits (Process-Level)

| Aspect | Description |
|--------|-------------|
| **Single warm-up** | Connectors/services initialized once per process |
| **Shared across workers** | All WorkerAsync in same process benefit from cached functions |
| **Memory efficient** | O(processes × functions), not O(workers × functions) |
| **Mirrors original** | Same pattern as before executor split |
| **Process isolation** | Different WorkerProcesses have isolated caches |

### Cache Size Calculation

```
With 10 processes × 1 thread × 3 async workers = 30 WorkerAsync

Cache is at PROCESS level:
- 10 processes × (100 functions + 10 services) × avg_size
- ≈ 10 × 110 × 10KB = 11MB total (very efficient)

Compare to per-worker caching:
- 30 workers × 110 × 10KB = 33MB (3x more memory)
```

---

## Implementation Plan

### Phase 0: Executor Environment API (Coordinator-level)

1. **Add `ExecutorEnvironment` dataclass** with validated code registry
2. **Add environment endpoints**:
   - `POST /environment` - Create isolated environment
   - `POST /environment/replicate` - Install packages (pip/uv)
   - `POST /environment/validate` - AST, bytecode, attestation checks
   - `DELETE /environment` - Destroy all (env + processes + workers)
3. **Implement security validation in sandbox**:
   - Undill (deserialize) serialized functions
   - AST analysis for dangerous patterns
   - Bytecode inspection
   - Import validation against security policy
   - Attestation signature verification
4. **Add validation result tracking** (errors, violations, approved code)

### Phase 1: Executor Process/Thread/Async API (4-level hierarchy)

1. **Add `ExecutorProcess` dataclass** with process-level caches
2. **Add `ExecutorThread` dataclass** to group async workers
3. **Add `ExecutorAsync` dataclass** for individual async workers
4. **Link to parent environment**: process inherits validated code registry
5. **Add process CRUD endpoints**: `POST/DELETE /processes/{pid}`
6. **Add initialization endpoints**: `/processes/{pid}/connectors`, `/processes/{pid}/services`
7. **Add thread endpoints**: `POST/DELETE /processes/{pid}/threads/{tid}`
8. **Add async endpoints**: `POST/DELETE /processes/{pid}/threads/{tid}/asyncs/{aid}`

### Phase 2: Coordinator Integration

1. **Add environment setup to `Coordinator._async_init()`**:
   - Create ExecutorEnvironment
   - Replicate packages
   - Validate all serialized code BEFORE creating any processes
2. **Move `executor_backend` from WorkerThread to WorkerProcess**
3. **Create executor process in `WorkerProcess._async_init()`**
4. **Initialize connectors/services via executor backend**
5. **Pass `executor_backend` to WorkerThreads** (shared reference)
6. **WorkerThread creates/destroys ExecutorThread** within parent's process
7. **WorkerAsync creates/destroys ExecutorAsync** within parent's thread

### Phase 3: Cache Migration

1. **Remove global caches** from executor service
2. **Move caches to `ExecutorProcess`** instances
3. **Update worker execution** to use `process.function_cache`
4. **Ensure deserialization uses validated code** from environment

### Phase 4: Testing

1. Test environment lifecycle (create/replicate/validate/destroy)
2. Test security validation (malicious code rejection)
3. Test process lifecycle (create/destroy)
4. Test cache sharing within process
5. Test cache isolation between processes
6. Test service/connector initialization

### Phase 5: Cleanup

1. Remove legacy shared pool code
2. Update documentation
3. Update CLAUDE.md

---

## Implementation Status

### ✅ Completed (2025-11-27)

**Phase 0: ExecutorEnvironment API**
- Created `lifecycle.py` with `ExecutorEnvironment` dataclass
- Implemented `create_environment()`, `replicate_environment()`, `validate_environment()`, `destroy_environment()`
- Security validation framework (AST, bytecode, undill, attestations) - structure in place

**Phase 1: ExecutorProcess/Thread/Async API**
- Created `ExecutorProcess`, `ExecutorThread`, `ExecutorAsync` dataclasses in `lifecycle.py`
- Implemented all lifecycle functions for each level
- Created `lifecycle_api.py` with all FastAPI endpoints
- Integrated router into `executor_service.py`

**Phase 2: Coordinator Integration**
- Added lifecycle method implementations to `HTTPExecutorBackend` in `base.py`
- Integrated lifecycle calls into `runtime.py`:
  - `Coordinator._async_init()` → `create_environment()`
  - `Coordinator._stop()` → `destroy_environment()`
  - `WorkerThread._async_init()` → `create_process()`, `create_thread()`
  - `WorkerThread._stop()` → `destroy_thread()`
  - `WorkerAsync._async_init()` → `create_async()`
  - `WorkerAsync._stop()` → `destroy_async()`

**Phase 3: Cache Migration**
- Process-level caches defined in `ExecutorProcess` dataclass:
  - `function_cache` - deserialized functions shared within process
  - `services` - initialized services shared within process
  - `connectors` - initialized connectors shared within process
  - `wrapped_cache` - wrapped routing functions
- Updated `_run_operation()` in `executor_service.py` to:
  - Use process-level cache when `process_id` provided (preferred path)
  - Fall back to global cache for backward compatibility
  - Track cache hits/misses per process
  - Use process-level services when available
- Health endpoint updated to show lifecycle/process-level cache stats

**Phase 4: Testing**
- Added comprehensive lifecycle API tests to `test_z_executor_e2e.py`:
  - External backend: 5 tests (environment, process, thread, async, full hierarchy)
  - Docker backend: 2 tests (environment, full hierarchy)
  - Pyodide backend: 2 tests (environment, full hierarchy)
  - Cross-backend: 3 tests (backend types, lifecycle methods, code validation)
- Total: 12 new lifecycle tests across all 3 backends

### 📁 Key Files

| File | Description |
|------|-------------|
| `lifecycle.py` | Core dataclasses and lifecycle functions (executor-side) |
| `lifecycle_api.py` | FastAPI endpoints for 4-level API |
| `base.py` | `HTTPExecutorBackend` with lifecycle method implementations |
| `runtime.py` | Coordinator integration (Coordinator, WorkerThread, WorkerAsync) |
| `executor_service.py` | Updated with process-level cache support |
| `external_backend.py` | Thin wrapper inheriting HTTPExecutorBackend |
| `docker_backend.py` | Thin wrapper inheriting HTTPExecutorBackend |
| `pyodide_backend.py` | Thin wrapper inheriting HTTPExecutorBackend |
| `test_z_executor_e2e.py` | Lifecycle API tests for all backends |

---

## Migration Strategy

### Environment Variable Toggle

```python
EXECUTOR_MODE = os.getenv('EXECUTOR_MODE', 'shared')  # 'shared' or 'process'

if EXECUTOR_MODE == 'process':
    # New process-level 1:1 architecture
    await backend.create_process(process_id)
    await backend.initialize_connectors(process_id)
    await backend.initialize_services(process_id)
else:
    # Legacy shared pool
    await backend.execute_async(...)
```

---

## Future Considerations

### Python 3.13+ Free-Threading

```
Current (GIL workaround):          Future (free-threading):
10 processes × 1 thread            1 process × 10 threads
= 10 ExecutorProcesses             = 1 ExecutorProcess (larger cache)
= 10 separate caches               = 1 shared cache (more efficient)

Same architecture, just different process/thread ratio.
```

### Multi-Region

```
Region A                              Region B
────────                              ────────
WorkerProcess-A                       WorkerProcess-B
    │                                     │
    ▼                                     ▼
ExecutorProcess-A                     ExecutorProcess-B
(local caches)                        (local caches)
    │                                     │
    └────────── Shared Redis ─────────────┘
              (CRDT queues)
```

---

## Summary

| Level | Coordinator | Executor | Responsibility |
|-------|-------------|----------|----------------|
| **Coordinator** | Coordinator | ExecutorEnvironment | Environment replication, package install, bytecode validation, security policies |
| **Process** | WorkerProcess | ExecutorProcess | Connectors, services, function cache (initialized once, shared to threads/asyncs) |
| **Thread** | WorkerThread | ExecutorThread | Groups async workers, future-proof for Python 3.13+ free-threading |
| **Async** | WorkerAsync | ExecutorAsync | Task execution (uses parent process's shared caches) |

| Principle | Implementation |
|-----------|----------------|
| **1:1 at EVERY level** | Coordinator→ExecutorEnvironment, WorkerProcess→ExecutorProcess, WorkerThread→ExecutorThread, WorkerAsync→ExecutorAsync |
| **Security in sandbox** | ALL validation (AST, bytecode, undill, attestations) happens in executor |
| **Environment once** | Package install, validation done ONCE before any processes created |
| **Caches at Process level** | Connectors, services, functions shared within process |
| **Asyncs share parent cache** | Multiple WorkerAsync → Multiple ExecutorAsync, all using process cache |
| **Mirrors original architecture** | Same pattern as before executor split |
| **Coordinator owns lifecycle** | CREATE_ENV, CREATE_PROCESS, CREATE_THREAD, CREATE_ASYNC, EXECUTE, DESTROY |
| **Executor is dumb** | No decisions, just follows orders with shared resources |

---

## Rollout Checklist

- [ ] Phase 0: Executor environment API complete (security validation in sandbox)
- [ ] Phase 1: Executor process/thread/async API complete (4-level hierarchy)
- [ ] Phase 2: Coordinator integration (Coordinator→ExecutorEnvironment, WorkerProcess→ExecutorProcess, WorkerThread→ExecutorThread, WorkerAsync→ExecutorAsync)
- [ ] Phase 3: Cache migration to process level
- [ ] Phase 4: All tests passing (environment, security, process, thread, async lifecycle)
- [ ] Phase 5: Documentation updated
- [ ] Remove legacy shared pool code

---

## Estimated Effort

| Phase | Tasks | Description |
|-------|-------|-------------|
| Phase 0 | Executor Environment API | Environment endpoints, security validation (AST, bytecode, attestations) |
| Phase 1 | Executor 4-Level API | Process/Thread/Async CRUD, connector/service init |
| Phase 2 | Coordinator Integration | Coordinator env, WorkerProcess/Thread/Async executor creation |
| Phase 3 | Cache Migration | Move caches to process level, link to validated code |
| Phase 4 | Testing | Environment, security, process, thread, async lifecycle tests |
| Phase 5 | Cleanup | Remove legacy code, update docs |

---

*Document created: 2025-11-27*
*Updated: 2025-11-27 - Changed from WorkerAsync-level to Process-level 1:1 mapping*
*Updated: 2025-11-27 - Added Coordinator-level ExecutorEnvironment for security validation in sandbox*
*Updated: 2025-11-27 - Added Thread level, renamed ExecutorWorker→ExecutorAsync for naming alignment*
*Status: Architecture Design - Ready for Implementation*
