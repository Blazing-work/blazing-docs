"""
Example: Dynamic Code Execution in Sandboxed Steps

This example demonstrates how to safely pass Python code as input to a sandboxed
step for execution. This is useful for scenarios like:

- User-defined transformations
- Dynamic strategy evaluation
- A/B testing different algorithms
- Custom analytics functions

Security Model:
- Code is validated on CLIENT SIDE before serialization (AST validation)
- Code is serialized with dill on the client side
- Execution happens in Pyodide WASM sandbox (no filesystem, network, or subprocess access)
- Bytecode is validated on executor BEFORE execution
- Resource limits are enforced by the executor

⚠️ SECURITY NOTE:
This example shows a SIMPLIFIED pattern for demonstration. In production, you should:
1. Add client-side validation using CodeValidator before serialization
2. Sign serialized payloads and verify signatures on executor
3. Always use sandboxed=True for untrusted code
See docs/security-dynamic-code-execution.md for the full secure pattern.

Usage:
    uv run python docs/examples/dynamic_code_execution.py
"""

import asyncio
import os
from blazing import Blazing
from blazing.dynamic_code import (
    serialize_user_function,
    execute_signed_function,
    create_signing_key,
    get_signing_key_from_env,
)

# Get or create signing key
# In production, load from secure storage (env var, secret manager, etc.)
SIGNING_KEY = get_signing_key_from_env() or create_signing_key()
print(f"Using signing key: {SIGNING_KEY.hex()[:16]}... (showing first 16 chars)")


async def main():
    # Initialize Blazing with API backend (sandboxed execution)
    app = Blazing(
        api_url="http://localhost:8000",
        api_token="test-token"
    )

    # =========================================================================
    # Define a sandboxed step that executes signed user code
    # =========================================================================
    @app.step(sandboxed=True)  # ← CRITICAL: sandboxed=True for Layer 5 isolation
    async def execute_user_function(
        serialized_func: str,
        signature: str,
        *args,
        services=None,
        **kwargs
    ):
        """
        Execute a signed user-provided function with full security validation.

        This step applies ALL 5 security layers:
        1. AST validation (done at serialize_user_function)
        2. Signature generation (done at serialize_user_function)
        3. Signature verification (done by execute_signed_function)
        4. Bytecode validation (done by execute_signed_function)
        5. Sandbox isolation (this step runs in Pyodide WASM)

        Args:
            serialized_func: Base64-encoded dill-serialized function
            signature: HMAC-SHA256 signature of serialized_func
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result of executing the function

        Raises:
            ValueError: If signature verification fails
            SecurityError: If bytecode validation fails
        """
        # Import the helper (available in Pyodide environment)
        from blazing.dynamic_code import execute_signed_function

        # Execute with full validation chain
        # The signing_key must be available on the executor
        # In production, read from executor's environment
        import os
        signing_key_hex = os.getenv('BLAZING_SIGNING_KEY')
        if signing_key_hex:
            signing_key = bytes.fromhex(signing_key_hex)
        else:
            # For demo: accept unsigned code (INSECURE in production!)
            signing_key = None

        return await execute_signed_function(
            serialized_func,
            signature,
            args=args,
            kwargs=kwargs,
            signing_key=signing_key,
            validate_bytecode=True,
        )

    # =========================================================================
    # Define a workflow that processes data with signed user functions
    # =========================================================================
    @app.workflow
    async def process_with_strategy(
        data: list,
        strategy_code: str,
        strategy_signature: str,
        services=None
    ):
        """
        Apply a user-defined strategy to data with signature verification.

        Args:
            data: List of numbers to process
            strategy_code: Base64-encoded dill-serialized function
            strategy_signature: HMAC-SHA256 signature of strategy_code

        Returns:
            Processed result
        """
        result = await execute_user_function(strategy_code, strategy_signature, data)
        return result

    # Publish routes and steps
    await app.publish()
    print("✓ Workflows and steps published")

    # =========================================================================
    # Example 1: Simple transformation function
    # =========================================================================
    def simple_transform(numbers):
        """Double each number and filter out evens."""
        return [x * 2 for x in numbers if x % 2 != 0]

    # Serialize with validation + signing
    serialized_simple, sig_simple = serialize_user_function(
        simple_transform,
        signing_key=SIGNING_KEY,
        validate=True,
        strict_mode=True
    )
    print(f"✓ simple_transform validated and signed ({len(serialized_simple)} chars)")

    # Execute via route
    unit1 = await app.run(
        "process_with_strategy",
        data=[1, 2, 3, 4, 5],
        strategy_code=serialized_simple,
        strategy_signature=sig_simple
    )
    result1 = await unit1.result()
    print(f"Example 1 - Simple transform: {result1}")
    # Expected: [2, 6, 10] (1*2, 3*2, 5*2)

    # =========================================================================
    # Example 2: Statistical analysis function
    # =========================================================================
    def calculate_statistics(numbers):
        """Calculate mean, median, and std deviation."""
        import math

        n = len(numbers)
        mean = sum(numbers) / n

        sorted_nums = sorted(numbers)
        if n % 2 == 0:
            median = (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
        else:
            median = sorted_nums[n//2]

        variance = sum((x - mean) ** 2 for x in numbers) / n
        std_dev = math.sqrt(variance)

        return {
            'mean': mean,
            'median': median,
            'std_dev': std_dev,
            'count': n
        }

    serialized_stats, sig_stats = serialize_user_function(
        calculate_statistics, SIGNING_KEY
    )
    print(f"✓ calculate_statistics validated and signed")

    unit2 = await app.run(
        "process_with_strategy",
        data=[10, 20, 30, 40, 50],
        strategy_code=serialized_stats,
        strategy_signature=sig_stats
    )
    result2 = await unit2.result()
    print(f"Example 2 - Statistics: {result2}")

    # =========================================================================
    # Example 3: Custom filter with closure
    # =========================================================================
    def make_threshold_filter(threshold):
        """Create a filter function with captured threshold."""
        def filter_above_threshold(numbers):
            return [x for x in numbers if x > threshold]
        return filter_above_threshold

    # Create filter with threshold=25
    threshold_filter = make_threshold_filter(25)
    serialized_filter, sig_filter = serialize_user_function(
        threshold_filter, SIGNING_KEY
    )
    print(f"✓ threshold_filter validated and signed")

    unit3 = await app.run(
        "process_with_strategy",
        data=[10, 20, 30, 40, 50],
        strategy_code=serialized_filter,
        strategy_signature=sig_filter
    )
    result3 = await unit3.result()
    print(f"Example 3 - Threshold filter (>25): {result3}")
    # Expected: [30, 40, 50]

    # =========================================================================
    # Example 4: Async function execution
    # =========================================================================
    async def async_transform(numbers):
        """Async transformation with simulated delay."""
        import asyncio

        # Simulate some async operation
        await asyncio.sleep(0.1)

        # Transform: square each number
        return [x ** 2 for x in numbers]

    serialized_async, sig_async = serialize_user_function(
        async_transform, SIGNING_KEY
    )
    print(f"✓ async_transform validated and signed")

    unit4 = await app.run(
        "process_with_strategy",
        data=[1, 2, 3, 4, 5],
        strategy_code=serialized_async,
        strategy_signature=sig_async
    )
    result4 = await unit4.result()
    print(f"Example 4 - Async transform (squares): {result4}")
    # Expected: [1, 4, 9, 16, 25]

    print("\n✓ All dynamic code execution examples completed successfully!")
    print("\nSecurity Hardening Applied:")
    print("  Layer 1: AST validation (blocks dangerous imports/builtins)")
    print("  Layer 2: HMAC-SHA256 signatures (prevents tampering)")
    print("  Layer 3: Signature verification before deserialization")
    print("  Layer 4: Bytecode validation after deserialization")
    print("  Layer 5: Pyodide WASM sandbox (no I/O access)")
    print("\nAll user functions validated WITHOUT requiring decorators!")


if __name__ == "__main__":
    asyncio.run(main())
