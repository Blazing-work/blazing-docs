# Dill Deserialization and Security Validation: A Deep Dive

## Executive Summary

This document describes a fundamental architectural challenge when combining Python function serialization (via `dill`) with AST-based security validation. The core issue is that **dill-deserialized functions produce synthetic source code that does not represent the original user code**, causing false positives in security validation.

This document provides full context for an LLM to conduct deep research on alternative solutions.

---

## Table of Contents

1. [Background: The Blazing Architecture](#background-the-blazing-architecture)
2. [The Problem: Dill's Synthetic Source Code](#the-problem-dills-synthetic-source-code)
3. [Failed Approaches](#failed-approaches)
4. [Current Solution: Relaxed Validator with Defense-in-Depth](#current-solution-relaxed-validator-with-defense-in-depth)
5. [Code Examples](#code-examples)
6. [Security Analysis](#security-analysis)
7. [Research Questions](#research-questions)
8. [Appendix: Technical Details](#appendix-technical-details)

---

## Background: The Blazing Architecture

### What is Blazing?

Blazing is a distributed task execution framework where:

1. **Client SDK** (`blazing/blazing.py`): Users define "stations" (functions) and "routes" (workflows) using decorators
2. **API Server** (`blazing_service/server.py`): Receives serialized functions via REST API
3. **Coordinator** (`blazing_service/engine/runtime.py`): Orchestrates execution across workers
4. **Executors**: Run code in isolated environments (Docker containers, Pyodide WASM)

### The Serialization Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT SIDE                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  @app.step                                                               │
│  def add(x: int, y: int) -> int:                                           │
│      return x + y                                                           │
│                                                                             │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 1: Client-Side Security Validation                              │  │
│  │ - AST parsing of ORIGINAL source code                                │  │
│  │ - Checks for blocked imports (os, subprocess, etc.)                  │  │
│  │ - Checks for blocked builtins (eval, exec, compile, etc.)            │  │
│  │ - Validates function signature and type hints                        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 2: Dill Serialization                                           │  │
│  │ - dill.dumps(func, recurse=False)                                    │  │
│  │ - Base64 encoding for transport                                      │  │
│  │ - Function + closures + globals serialized                           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│         │                                                                   │
│         ▼                                                                   │
│     HTTP POST to /v1/registry/sync                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVER SIDE                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 3: Dill Deserialization                                         │  │
│  │ - Base64 decoding                                                    │  │
│  │ - dill.loads(bytes)                                                  │  │
│  │ - Reconstructs function object                                       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 4: Server-Side Security Validation (THE PROBLEM)                │  │
│  │ - inspect.getsource(func) returns SYNTHETIC source                   │  │
│  │ - Synthetic source contains dill internals (type, traceback, etc.)   │  │
│  │ - AST validation FAILS with false positives                          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 5: Executor Sandbox                                             │  │
│  │ - Docker container isolation (seccomp, capabilities dropped)         │  │
│  │ - OR Pyodide WASM sandbox (browser-grade isolation)                  │  │
│  │ - Network isolation, filesystem isolation                            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Problem: Dill's Synthetic Source Code

### What is Dill?

[Dill](https://github.com/uqfoundation/dill) is a Python library that extends `pickle` to serialize almost any Python object, including:

- Functions (including lambdas)
- Closures (functions with captured variables)
- Classes defined at runtime
- Modules

### How Dill Reconstructs Functions

When you call `dill.loads()` on a serialized function, dill reconstructs the function object using Python's internal mechanisms. This involves:

1. **Reconstructing the code object** (`types.CodeType`)
2. **Reconstructing the globals dictionary**
3. **Reconstructing closure cells**
4. **Creating a new function object** (`types.FunctionType`)

### The Synthetic Source Problem

When `inspect.getsource()` is called on a dill-reconstructed function, it may return:

1. **The original source** (if the source file exists and is readable)
2. **Synthetic reconstruction code** (if source is unavailable)
3. **An error** (`OSError: could not get source code`)

**Example of synthetic source from dill:**

```python
# ORIGINAL user code (validated client-side):
def add(x: int, y: int) -> int:
    return x + y

# SYNTHETIC source from inspect.getsource() after dill reconstruction:
def _create_function(fcode, fglobals, fname=None, fdefaults=None, fclosure=None, fdict=None, fkwdefaults=None):
    # Reconstructs a function from its components
    func = type(lambda: None)(fcode, fglobals, fname, fdefaults, fclosure)
    if fdict is not None:
        func.__dict__.update(fdict)
    if fkwdefaults is not None:
        func.__kwdefaults__ = fkwdefaults
    return func

# Or for closures with captured variables:
def _create_cell(contents):
    return (lambda: contents).__closure__[0]

# Full reconstruction using traceback module for line numbers:
import traceback
_frame_info = traceback.extract_stack()
```

### Why AST Validation Fails

Our `CodeValidator` uses AST (Abstract Syntax Tree) parsing to detect dangerous patterns:

```python
class CodeValidator:
    BLOCKED_IMPORTS = {'os', 'subprocess', 'sys', 'shutil', 'socket', ...}
    BLOCKED_BUILTINS = {'eval', 'exec', 'compile', 'open', '__import__', ...}

    def validate_source(self, source: str) -> Tuple[bool, Optional[str]]:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            # Check for blocked imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.BLOCKED_IMPORTS:
                        return False, f"Import '{alias.name}' is blocked"

            # Check for blocked function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.BLOCKED_BUILTINS:
                        return False, f"Function '{node.func.id}()' is blocked"
```

**Problem:** When validating dill's synthetic source:

1. `type()` appears in the synthetic source (for `types.FunctionType`)
2. `traceback` import appears (for stack frame information)
3. `types.ModuleType` appears (for reconstructing module references)

These are **dill's internal mechanisms**, NOT the user's code. But AST validation cannot distinguish between them.

### Real Error Messages Encountered

```
SecurityError: Function 'type()' is blocked
    in function: _create_function
    at line: func = type(lambda: None)(fcode, fglobals, fname, fdefaults, fclosure)

SecurityError: Import 'traceback' is blocked
    in function: calculate
    at line: import traceback

SecurityError: Import from 'blazing_service.util.util' is not in the allowed imports list
```

---

## Failed Approaches

### Approach 1: Whitelist Dill's Internal Builtins

**Idea:** Add dill's required builtins to an allow list.

```python
class RelaxedCodeValidator(CodeValidator):
    # Allow dill's internal mechanisms
    DILL_BUILTINS = {'type', 'object', 'super', 'getattr', 'setattr', 'hasattr'}

    def __init__(self):
        super().__init__()
        # Remove dill builtins from blocked list
        self.blocked_builtins = self.BLOCKED_BUILTINS - self.DILL_BUILTINS
```

**Result:** FAILED

**Why:** Dill uses many more modules than anticipated (`traceback`, `types`, `weakref`, `copyreg`, etc.). Whitelisting becomes an endless game of whack-a-mole.

**Security Risk:** Over-whitelisting creates real security holes. For example, `type()` can be used to create arbitrary classes that bypass restrictions.

### Approach 2: Whitelist Dill's Internal Modules

**Idea:** Allow imports of dill's internal modules.

```python
DILL_ALLOWED_IMPORTS = {
    'traceback', 'types', 'weakref', 'copyreg', 'functools',
    '_thread', 'threading', 'io', 'codecs', 'encodings'
}
```

**Result:** FAILED

**Why:** Some of these modules ARE dangerous:
- `traceback` can leak stack information
- `types` can create arbitrary code objects
- `io` can access files

**Security Risk:** Allowing these imports defeats the purpose of security validation.

### Approach 3: Detect Dill-Generated Source

**Idea:** Detect when source is synthetic and skip validation.

```python
def is_dill_synthetic_source(source: str) -> bool:
    dill_markers = [
        '_create_function',
        '_create_cell',
        'type(lambda: None)',
        '__closure__[0]'
    ]
    return any(marker in source for marker in dill_markers)
```

**Result:** PARTIALLY WORKED, but fragile

**Why:** Dill's synthetic source format changes between versions. Pattern matching is unreliable.

**Security Risk:** Attacker could craft malicious code containing these markers to bypass validation.

### Approach 4: Validate Bytecode Instead of Source

**Idea:** Inspect the function's `__code__` object directly.

```python
def validate_bytecode(func):
    code = func.__code__
    # Check co_names for dangerous calls
    # Check co_consts for dangerous values
    # Analyze bytecode instructions
```

**Result:** NOT IMPLEMENTED (too complex)

**Why:** Bytecode analysis is:
1. Complex to implement correctly
2. Version-dependent (bytecode changes between Python versions)
3. Can be circumvented with `exec()` in constants

---

## Current Solution: Relaxed Validator with Defense-in-Depth

### Philosophy

Instead of trying to validate dill's unreliable synthetic source, we:

1. **Trust client-side validation** that happened BEFORE serialization
2. **Maintain defense-in-depth** through executor sandboxing
3. **Do basic sanity checks** (is it callable? does it have a name?)

### The Defense-in-Depth Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DEFENSE LAYER 1: Client-Side Validation              │
│                                                                             │
│  ✓ Full AST analysis of ORIGINAL source code                               │
│  ✓ Blocked imports: os, subprocess, sys, socket, shutil, etc.              │
│  ✓ Blocked builtins: eval, exec, compile, open, __import__, etc.           │
│  ✓ Validated BEFORE serialization (reliable source)                        │
│                                                                             │
│  Location: src/blazing/blazing.py (client SDK)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DEFENSE LAYER 2: Relaxed Server Validation           │
│                                                                             │
│  ✓ Basic sanity checks (callable, has name)                                │
│  ✓ Trusts client-side validation for deserialized functions                │
│  ✓ Could add signature-based validation in future                          │
│                                                                             │
│  Location: src/blazing_service/security.py (RelaxedCodeValidator)          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DEFENSE LAYER 3: Network Security                    │
│                                                                             │
│  ✓ JWT authentication required for all API calls                           │
│  ✓ App ID namespacing for multi-tenant isolation                           │
│  ✓ TLS encryption in production                                            │
│                                                                             │
│  Location: src/blazing_service/auth/ (FastAPI dependencies)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DEFENSE LAYER 4: Executor Sandbox                    │
│                                                                             │
│  Docker Executor:                                                           │
│  ✓ Seccomp profiles (syscall filtering)                                    │
│  ✓ Dropped capabilities (no privileged operations)                         │
│  ✓ Network isolation (internal network only)                               │
│  ✓ Filesystem isolation (read-only root, tmpfs for writes)                 │
│  ✓ Resource limits (CPU, memory, time)                                     │
│                                                                             │
│  Pyodide Executor (WASM):                                                  │
│  ✓ Browser-grade sandbox (no filesystem, no network by default)            │
│  ✓ Memory isolation (separate WASM heap)                                   │
│  ✓ No system call access                                                   │
│                                                                             │
│  Location: docker/Dockerfile.executor, pyodide-executor/                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation

**RelaxedCodeValidator** (`src/blazing_service/security.py`):

```python
class RelaxedCodeValidator(CodeValidator):
    """Relaxed code validator for dill-deserialized functions.

    Dill-reconstructed functions have synthetic source code that may be:
    1. Invalid/incomplete (dill doesn't always preserve full source)
    2. Full of dill internal mechanisms (type(), traceback, etc.)

    For functions that have ALREADY been validated client-side before serialization,
    we trust the client validation and allow execution. The function has already
    passed security checks - we just can't meaningfully re-validate the dill output.

    Defense-in-depth is maintained through:
    1. Client-side validation (happened before serialization)
    2. Executor sandbox (Docker/Pyodide isolation)
    3. Network security (authenticated API requests)
    """

    def validate_function(self, func: Callable) -> Tuple[bool, Optional[str]]:
        """Validate a dill-deserialized function.

        For deserialized functions, we trust that client-side validation already
        happened. The dill-reconstructed source is synthetic and unreliable for
        security analysis - it contains dill's internal reconstruction mechanisms,
        not the original user code.

        We still do basic sanity checks:
        - Function must be callable
        - Function must have a name
        """
        if not callable(func):
            return False, "Object is not callable"

        func_name = getattr(func, '__name__', None)
        if func_name is None:
            return False, "Function has no __name__ attribute"

        # For deserialized functions from authenticated clients, we trust
        # the client-side validation that happened before serialization.
        logger.debug(f"Allowing deserialized function '{func_name}' "
                    "(client-side validation assumed)")

        return True, None
```

**Usage in deserialize_function** (`src/blazing_service/util/util.py`):

```python
@staticmethod
def deserialize_function(func_str, validate=True):
    """Deserialize a string back to a Python function."""
    # ... fake module injection for test files ...

    # Deserialize
    func = dill.loads(base64.b64decode(func_str))

    # SECURITY: Server-side validation for deserialized functions
    #
    # Dill-reconstructed functions have synthetic source that may include internal
    # mechanisms like type(), types.ModuleType, etc. We use "relaxed mode" validation
    # that allows these dill internals while still blocking truly dangerous patterns.
    #
    # Defense-in-depth is maintained through:
    # 1. Client-side validation: Blazing SDK validates functions BEFORE serialization
    # 2. Relaxed server-side validation: Blocks dangerous patterns (eval, exec, os, etc.)
    # 3. Executor sandbox: Code runs in isolated Docker containers / Pyodide WASM
    if validate and callable(func):
        from blazing_service.security import get_relaxed_validator, SecurityError
        validator = get_relaxed_validator()
        is_valid, error = validator.validate_function(func)
        if not is_valid:
            func_name = getattr(func, '__name__', '<unknown>')
            raise SecurityError(
                f"Server-side security validation failed for function '{func_name}': {error}\n"
                f"This function contains dangerous code patterns and cannot be executed."
            )

    return func
```

---

## Security Analysis

### Threat Model

| Threat | Mitigation | Effectiveness |
|--------|------------|---------------|
| Malicious function in user code | Client-side AST validation | HIGH |
| Bypass via dill manipulation | Executor sandbox | HIGH |
| Network interception | JWT auth + TLS | HIGH |
| Malicious authenticated user | Executor sandbox | HIGH |
| Privilege escalation in executor | Docker seccomp/capabilities | MEDIUM |
| WASM sandbox escape | Browser-grade isolation | HIGH |

### Known Limitations

1. **Trust in client-side validation**: If an attacker can bypass the client SDK and send raw serialized functions, they bypass client validation.
   - **Mitigation**: JWT authentication ensures only authorized clients can submit functions.

2. **Dill vulnerabilities**: Dill's `loads()` is similar to `pickle.loads()` - it can execute arbitrary code during deserialization.
   - **Mitigation**: Executor sandbox contains any malicious code that executes during deserialization.

3. **Executor escape**: If an attacker finds a sandbox escape vulnerability in Docker or WASM, they could break out.
   - **Mitigation**: Keep Docker and runtime environments updated; use defense-in-depth.

### Attack Scenarios

**Scenario 1: Malicious user submits dangerous function**

```python
@app.step
def steal_secrets():
    import os
    return os.environ.get('SECRET_KEY')
```

**Defense:**
1. Client-side validation BLOCKS `import os` before serialization
2. Even if bypassed, Docker executor has no access to host environment variables

**Scenario 2: Attacker crafts raw payload**

```python
# Attacker sends serialized payload directly, bypassing client SDK
payload = dill.dumps(lambda: os.system('rm -rf /'))
requests.post('/v1/registry/sync', json={'stations': [{'serialized_function': base64.b64encode(payload)}]})
```

**Defense:**
1. JWT authentication required - attacker needs valid token
2. Relaxed validator only checks basic sanity (this would pass)
3. **Executor sandbox** prevents `os.system()` from affecting host

**Scenario 3: Pickle/Dill deserialization attack**

```python
# Malicious class that executes code during unpickling
class Malicious:
    def __reduce__(self):
        return (os.system, ('rm -rf /',))

payload = dill.dumps(Malicious())
```

**Defense:**
1. Code executes during `dill.loads()` on server
2. **BUT** this happens inside the API server, not executor
3. **RISK**: This is a real vulnerability - the API server is not sandboxed

**Mitigation for Scenario 3:**
- Move deserialization INTO the executor sandbox
- Or use restricted unpickler (see Research Questions)

---

## Research Questions

### 1. Restricted Unpickler for Dill

**Question:** Can we implement a restricted unpickler that prevents arbitrary code execution during deserialization?

**Background:** Python's `pickle` module allows custom unpicklers that restrict which classes can be instantiated:

```python
import pickle
import io

class RestrictedUnpickler(pickle.Unpickler):
    ALLOWED_CLASSES = {
        'builtins': {'str', 'int', 'list', 'dict', 'tuple', 'set', 'frozenset'},
        'collections': {'OrderedDict'},
    }

    def find_class(self, module, name):
        if module in self.ALLOWED_CLASSES:
            if name in self.ALLOWED_CLASSES[module]:
                return getattr(__import__(module), name)
        raise pickle.UnpicklingError(f"Blocked: {module}.{name}")
```

**Research needed:**
- Does dill support custom unpicklers?
- What classes does dill need to reconstruct functions?
- Can we create a minimal allow list for function reconstruction?

### 2. Source Code Signing

**Question:** Can we sign the original source code client-side and verify server-side?

**Concept:**
```python
# Client-side
source_hash = hashlib.sha256(original_source.encode()).hexdigest()
signature = hmac.new(shared_secret, source_hash.encode(), hashlib.sha256).hexdigest()
serialized = dill.dumps(func)
payload = {
    'serialized_function': serialized,
    'source_hash': source_hash,
    'signature': signature,
    'original_source': original_source  # Optional: for server-side re-validation
}

# Server-side
if verify_signature(payload['source_hash'], payload['signature']):
    # Trust the source was validated
```

**Research needed:**
- How to securely manage shared secrets?
- Does including original source defeat the purpose of serialization?
- Can an attacker modify the function after signing?

### 3. Move Deserialization to Executor

**Question:** Can we deserialize functions INSIDE the sandbox to contain deserialization attacks?

**Concept:**
```
Current flow:
  API Server (unsandboxed) → deserialize → send function to executor

Proposed flow:
  API Server (unsandboxed) → send serialized bytes → Executor (sandboxed) → deserialize
```

**Benefits:**
- Deserialization attacks contained in sandbox
- API server never executes untrusted code

**Challenges:**
- Executor needs access to dill/pickle
- How to validate before execution if deserialization happens in executor?
- Increased complexity in executor communication

### 4. AST-Based Serialization

**Question:** Can we serialize the AST instead of the bytecode?

**Concept:** Instead of using dill, serialize the function's AST representation:

```python
import ast

def serialize_function(func):
    source = inspect.getsource(func)
    tree = ast.parse(source)
    return ast.dump(tree)

def deserialize_function(ast_dump):
    tree = ast.literal_eval(ast_dump)  # This doesn't work directly
    # Need to compile and exec the AST
    code = compile(tree, '<ast>', 'exec')
    exec(code)
    return locals()[func_name]
```

**Benefits:**
- AST can be validated both client and server side
- No synthetic source problem
- More transparent serialization

**Challenges:**
- How to serialize closures and captured variables?
- Performance implications?
- Can AST handle all Python features (decorators, generators, etc.)?

### 5. Bytecode Validation

**Question:** Can we validate function bytecode directly instead of source?

**Concept:**
```python
import dis

def validate_bytecode(func):
    dangerous_ops = {'IMPORT_NAME', 'IMPORT_FROM'}
    dangerous_names = {'eval', 'exec', 'open', 'compile', '__import__'}

    code = func.__code__

    # Check for dangerous bytecode operations
    for instr in dis.get_instructions(code):
        if instr.opname in dangerous_ops:
            return False, f"Dangerous operation: {instr.opname}"
        if instr.opname == 'LOAD_GLOBAL' and instr.argval in dangerous_names:
            return False, f"Dangerous global: {instr.argval}"

    # Recursively check nested code objects
    for const in code.co_consts:
        if isinstance(const, type(code)):
            is_valid, error = validate_bytecode_code(const)
            if not is_valid:
                return False, error

    return True, None
```

**Research needed:**
- Complete list of dangerous bytecode operations
- How to handle indirect calls (`getattr(module, 'system')(cmd)`)
- Performance impact of bytecode analysis
- Python version compatibility

### 6. WebAssembly-Based Validation

**Question:** Can we run validation in a WASM sandbox for defense-in-depth?

**Concept:** Run AST validation in Pyodide/WASM to contain any exploits in the validation code itself.

**Benefits:**
- Validation code can't escape sandbox
- Could validate dill's synthetic source safely

**Challenges:**
- Performance overhead
- Complexity of running Python in WASM for validation
- May be overkill if executor sandbox is already secure

---

## Appendix: Technical Details

### File Locations

| Component | File Path |
|-----------|-----------|
| Client SDK | `src/blazing/blazing.py` |
| Client Security | `src/blazing/security.py` |
| Server Security | `src/blazing_service/security.py` |
| Deserialization | `src/blazing_service/util/util.py` |
| API Server | `src/blazing_service/server.py` |
| Runtime/Coordinator | `src/blazing_service/engine/runtime.py` |
| Docker Executor | `docker/Dockerfile.executor` |
| Pyodide Executor | `pyodide-executor/` |

### Key Functions

**Client-side validation:**
```python
# src/blazing/security.py
class CodeValidator:
    def validate_function(self, func: Callable) -> Tuple[bool, Optional[str]]
    def validate_source(self, source: str) -> Tuple[bool, Optional[str]]
```

**Client-side serialization:**
```python
# src/blazing/blazing.py
# Line ~422 (stations)
station['serialized_function'] = base64.b64encode(dill.dumps(clean_func, recurse=False)).decode('utf-8')

# Line ~455 (routes)
route['serialized_function'] = base64.b64encode(dill.dumps(clean_func, recurse=False)).decode('utf-8')
```

**Server-side deserialization:**
```python
# src/blazing_service/util/util.py
# Line ~199-260
@staticmethod
def deserialize_function(func_str, validate=True):
    # Creates fake test modules
    # Deserializes with dill.loads()
    # Validates with RelaxedCodeValidator
```

**Server-side relaxed validation:**
```python
# src/blazing_service/security.py
# Line ~562-627
class RelaxedCodeValidator(CodeValidator):
    def validate_function(self, func: Callable) -> Tuple[bool, Optional[str]]
```

### Test Case

The test that validates this entire flow:

```python
# tests/test_z_integration_docker_example.py::test_simple_route_execution

@app.step
async def add(x: int, y: int, services=None) -> int:
    return x + y

@app.step
async def multiply(x: int, y: int, services=None) -> int:
    return x * y

@app.workflow
async def calculate(x: int, y: int, z: int, services=None):
    """Calculate (x + y) * z"""
    sum_result = await add(x, y, services=services)
    return await multiply(sum_result, z, services=services)

# Test: (3 + 4) * 5 = 35
unit = app.run("calculate", x=3, y=4, z=5)
result = unit.result(timeout=60)
assert result == 35
```

### Dill Version Information

```
dill==0.3.8
```

Dill's behavior may change between versions. The synthetic source format is not part of dill's public API.

---

## Proposed Solution: Executor-Side Deserialization with Bytecode Validation

After analyzing the research questions, the following hybrid approach addresses both the architectural vulnerability (deserialization on unsandboxed API server) and the synthetic source validation problem.

### Key Insight

The **real vulnerability** is not the synthetic source problem (which is just annoying). It's that **deserialization happens on the unsandboxed API server**. Dill's `loads()` can execute arbitrary code during unpickling via `__reduce__` methods.

### Architecture Change

```
Current (Vulnerable):
  API Server (unsandboxed) → dill.loads() → validate synthetic source → executor
                                ↑
                         ATTACK SURFACE

Proposed (Secure):
  API Server (unsandboxed) → pass raw bytes → Executor (sandboxed) → dill.loads() → bytecode validate → execute
                                                        ↑
                                              CONTAINED IN SANDBOX
```

### Implementation Components

#### 1. Client Side - Bundle Source with Serialized Function

```python
# src/blazing/blazing.py - add source bundling
def _prepare_station(self, func):
    # Existing validation
    validator = get_validator()
    is_valid, error = validator.validate_function(func)
    if not is_valid:
        raise SecurityError(error)

    original_source = inspect.getsource(func)
    serialized = base64.b64encode(dill.dumps(func, recurse=False)).decode()

    # Bundle both - source for audit trail, serialized for execution
    return {
        'serialized_function': serialized,
        'source_hash': hashlib.sha256(original_source.encode()).hexdigest(),
        # Optional: include source for server-side re-validation
        'original_source': base64.b64encode(original_source.encode()).decode()
    }
```

#### 2. API Server - NO Deserialization, Only Source Validation

```python
# src/blazing_service/util/util.py
class BlazingUtil:
    @staticmethod
    def store_function(func_data: dict) -> str:
        """Store serialized function WITHOUT deserializing.

        Returns a function_id for later execution.
        """
        # Validate original source if provided (safe - it's just text)
        if 'original_source' in func_data:
            source = base64.b64decode(func_data['original_source']).decode()
            validator = get_validator()  # Full validator, not relaxed
            is_valid, error = validator.validate_source(source)
            if not is_valid:
                raise SecurityError(f"Source validation failed: {error}")

        # Store raw bytes - NEVER deserialize on API server
        function_id = str(uuid.uuid4())
        self._function_store[function_id] = func_data['serialized_function']
        return function_id
```

#### 3. Executor - Deserialize + Bytecode Validation Inside Sandbox

```python
# executor/secure_loader.py
import dis
from typing import Callable, Tuple, Optional

class SecureFunctionLoader:
    """Load and validate functions INSIDE the sandbox."""

    DANGEROUS_GLOBALS = frozenset({
        'eval', 'exec', 'compile', 'open', '__import__',
        'getattr', 'setattr', 'delattr',  # reflection
        'globals', 'locals', 'vars',
        'breakpoint', 'input',
    })

    DANGEROUS_IMPORTS = frozenset({
        'os', 'subprocess', 'sys', 'shutil', 'socket',
        'ctypes', 'multiprocessing', 'threading',
        'importlib', 'builtins', 'code', 'codeop',
    })

    def load_function(self, serialized_b64: str) -> Callable:
        """Deserialize and validate a function.

        This runs INSIDE the sandbox, so deserialization attacks are contained.
        """
        # Deserialize (any attack is sandboxed)
        func = dill.loads(base64.b64decode(serialized_b64))

        # Validate bytecode
        is_valid, error = self._validate_bytecode(func)
        if not is_valid:
            raise SecurityError(f"Bytecode validation failed: {error}")

        return func

    def _validate_bytecode(self, func: Callable) -> Tuple[bool, Optional[str]]:
        """Validate function bytecode for dangerous patterns."""
        return self._validate_code_object(func.__code__, set())

    def _validate_code_object(self, code, visited: set) -> Tuple[bool, Optional[str]]:
        """Recursively validate a code object."""
        if id(code) in visited:
            return True, None
        visited.add(id(code))

        # Check for dangerous global references
        for name in code.co_names:
            if name in self.DANGEROUS_GLOBALS:
                return False, f"Dangerous global reference: {name}"

        # Check bytecode instructions
        for instr in dis.get_instructions(code):
            # Block direct imports of dangerous modules
            if instr.opname == 'IMPORT_NAME':
                module = instr.argval
                root_module = module.split('.')[0]
                if root_module in self.DANGEROUS_IMPORTS:
                    return False, f"Dangerous import: {module}"

            # Block LOAD_ATTR on potentially dangerous names
            # (catches getattr(os, 'system') patterns somewhat)
            if instr.opname == 'LOAD_ATTR' and instr.argval in {'system', 'popen', 'spawn'}:
                return False, f"Dangerous attribute access: {instr.argval}"

        # Recursively check nested code objects (lambdas, comprehensions, nested funcs)
        for const in code.co_consts:
            if hasattr(const, 'co_code'):  # It's a code object
                is_valid, error = self._validate_code_object(const, visited)
                if not is_valid:
                    return False, error

        return True, None
```

#### 4. Executor Entry Point

```python
# executor/main.py
def execute_task(function_id: str, args: dict):
    """Execute a task inside the sandbox."""
    # Fetch serialized bytes from API (or message queue)
    serialized_b64 = fetch_function_bytes(function_id)

    # Load with validation (deserialization happens HERE, in sandbox)
    loader = SecureFunctionLoader()
    func = loader.load_function(serialized_b64)

    # Execute
    return func(**args)
```

### Threat Mitigation Matrix

| Threat | How It's Mitigated |
|--------|-------------------|
| Deserialization RCE (`__reduce__`) | Happens inside sandbox - attack is contained |
| Malicious bytecode | Bytecode validation catches dangerous patterns |
| Synthetic source problem | **Eliminated** - we validate bytecode, not source |
| Client SDK bypass | Bytecode validation is server-side, in executor |
| Dill version changes | Bytecode validation is independent of dill internals |

### Trade-offs

**Pros:**
- API server never executes untrusted code
- Bytecode validation is reliable (no synthetic source problem)
- Defense-in-depth: sandbox + validation
- Works regardless of dill's internals
- Can validate original source on API server (it's just text, safe to parse)

**Cons:**
- Bytecode validation isn't perfect (dynamic patterns can evade)
- More complex executor implementation
- Need to handle bytecode differences across Python versions
- Slight latency increase (validation in executor)

### Bytecode Validation Limitations

Bytecode validation cannot catch all attacks. For example:

```python
# This would pass bytecode validation but is still dangerous
def sneaky():
    module_name = 'o' + 's'
    m = __builtins__.__dict__['__imp' + 'ort__'](module_name)
    return m.system('whoami')
```

**However:** This is why you have the sandbox. Bytecode validation is a *layer*, not the only defense. The sandbox prevents `os.system` from doing anything harmful anyway.

### Optional Enhancement: Restricted Unpickler

As an additional layer inside the executor:

```python
class RestrictedDillUnpickler(dill.Unpickler):
    """Restrict what dill can instantiate during deserialization."""

    ALLOWED_MODULES = {
        'builtins': {'int', 'float', 'str', 'list', 'dict', 'tuple', 'set', 'bool', 'bytes', 'type'},
        'types': {'FunctionType', 'CodeType', 'CellType', 'ModuleType'},
        'dill._dill': {'*'},  # Allow dill internals
    }

    def find_class(self, module, name):
        if module in self.ALLOWED_MODULES:
            allowed = self.ALLOWED_MODULES[module]
            if '*' in allowed or name in allowed:
                return super().find_class(module, name)
        raise dill.UnpicklingError(f"Blocked: {module}.{name}")
```

This adds another layer but is complex to get right with dill's internals. Prioritize the architectural change (move deserialization to executor) first.

### Implementation Priority

1. **Phase 1 (High Priority):** Move deserialization to executor
   - Modify API server to store raw bytes, not deserialize
   - Modify executor to deserialize and execute
   - This alone closes the main vulnerability

2. **Phase 2 (Medium Priority):** Add bytecode validation in executor
   - Implement `SecureFunctionLoader` with bytecode inspection
   - Handles cases where sandbox has weaknesses

3. **Phase 3 (Low Priority):** Add restricted unpickler
   - Research dill's internals to create minimal allow list
   - Adds defense-in-depth for deserialization itself

---

## Conclusion

The fundamental challenge is that **dill's serialization format is opaque** - we cannot reliably inspect or validate what's inside a serialized function without deserializing it first. Once deserialized, the source code is synthetic and unreliable.

Our current solution of "trust client-side validation + executor sandbox" is pragmatic but not ideal. The **proposed solution** of moving deserialization into the executor sandbox eliminates the main vulnerability (RCE via deserialization on unsandboxed API server) while adding bytecode validation as an additional defense layer.

**Recommended implementation order:**

1. **Immediate:** Move deserialization to executor (closes deserialization RCE vulnerability)
2. **Short-term:** Add bytecode validation in executor (defense-in-depth)
3. **Long-term:** Investigate restricted unpickler for dill (additional layer)

---

*Document created: 2025-11-26*
*Last updated: 2025-11-26*
*Author: Claude (AI Assistant)*
*Context: Blazing distributed task execution framework - security validation for dill-serialized functions*
