# Blazing Flow - Product Naming Guide

## Product Hierarchy

```
Blazing Flow (Main Product)
├── Blazing Flow Sandbox (Sub-feature: Security isolation for untrusted code)
└── Blazing Flow Endpoints (Sub-feature: HTTP/WebSocket API exposure)

Future Products:
└── Blazing Flow Gateway (Separate product: API gateway/routing layer)
```

## Naming Rules

### ✅ Use These Terms

**Main Product:**
- "Blazing Flow" - Main product name
- "Blazing Flow workflows" - Workflow orchestration
- "Blazing Flow client" - Python client library

**Sub-Features:**
- "Blazing Flow Sandbox" - Sandboxed execution (WASM/Pyodide)
- "Blazing Flow Endpoints" - HTTP/WebSocket endpoint exposure
- "Blazing Flow Endpoint" (singular) - Individual endpoint

**Technical Terms:**
- "workflow" (not "route") - Orchestrator function
- "step" (not "station") - Individual task/function
- "service" - Reusable capability with connectors
- "connector" - External integration (DB, API, etc.)

### ❌ Avoid These Terms

**Deprecated (v1.x lexicon):**
- "route" → use "workflow"
- "station" → use "step"

**Confusing/Generic:**
- "web endpoint" → use "Blazing Flow Endpoint"
- "FastAPI endpoint wrapper" → use "Blazing Flow Endpoints"
- "API layer" → use "Blazing Flow Endpoints layer"

**Reserved for Future:**
- "Blazing Flow Gateway" - Reserved for separate gateway product

## Documentation Structure

### Main Documentation
```
docs/
├── README.md                           # Blazing Flow overview
├── workflows.md                        # Core workflow orchestration
├── steps.md                            # Step definitions
├── services.md                        # Service and connector guide
├── blazing-flow-sandbox.md             # Sandbox sub-feature
└── blazing-flow-endpoints.md           # Endpoints sub-feature
```

### Current Files (Legacy Names - to be renamed)
```
docs/
├── web-endpoints.md                    → blazing-flow-endpoints.md
├── web-endpoints-tests.md              → blazing-flow-endpoints-tests.md
└── web-endpoints-test-improvements.md  → blazing-flow-endpoints-test-improvements.md
```

## Code and API Naming

### Python API (Keep as-is for backwards compatibility)
```python
from blazing import Blazing

app = Blazing(api_url="...", api_token="...")

# Decorator names stay the same (breaking changes not allowed)
@app.workflow       # Core orchestration
@app.step          # Individual task
@app.service      # Reusable capability
@app.endpoint      # Blazing Flow Endpoint exposure
```

### Module Structure
```python
# Core
from blazing import Blazing

# Sandbox feature
from blazing.sandbox import SandboxedExecutor  # (if exposed)

# Endpoints feature
from blazing.web import create_asgi_app
```

## Marketing/Communication

### Feature Descriptions

**Blazing Flow:**
"Distributed workflow orchestration for Python with async/sync execution, worker pools, and intelligent scaling."

**Blazing Flow Sandbox:**
"Execute untrusted user code safely in WASM isolation while maintaining access to trusted services and connectors."

**Blazing Flow Endpoints:**
"Expose Blazing Flow workflows as public HTTP/WebSocket endpoints with auto-generated request models, authentication, and job management."

### Example Marketing Copy

**Landing Page:**
```
# Blazing Flow
Build complex workflows with simple Python decorators.

## Core Features
- Distributed execution
- Async/sync support
- Intelligent worker scaling
- Multi-station orchestration

## Security with Blazing Flow Sandbox
Execute untrusted code safely in WASM isolation

## Public APIs with Blazing Flow Endpoints
Expose workflows as HTTP/WebSocket endpoints
```

**Documentation Section Headers:**
```
# Getting Started with Blazing Flow
## Creating Your First Workflow
## Adding Steps
## Using Services
## Enabling Blazing Flow Sandbox (optional)
## Exposing Endpoints (optional)
```

## Test and Code Comments

### ✅ Correct Usage in Comments
```python
# Test Blazing Flow Endpoint creation
def test_endpoint_decorator():
    """Verify that @app.endpoint creates a Blazing Flow Endpoint."""
    pass

# Test Blazing Flow Sandbox execution
def test_sandboxed_execution():
    """Verify Blazing Flow Sandbox isolates untrusted code."""
    pass
```

### ❌ Incorrect Usage
```python
# Test web endpoint creation (too generic)
# Test FastAPI wrapper (implementation detail)
# Test route decorator (deprecated v1.x term)
```

## File and Directory Naming

### Source Code (Keep current structure)
```
src/blazing/
├── blazing.py          # Main client
├── base.py             # Base classes
├── web.py              # Endpoints feature
└── sandbox/            # Sandbox feature (if separated)
```

### Tests (Keep current structure)
```
tests/
├── test_web_endpoints*.py              # Endpoints tests (keep legacy name for git history)
├── test_sandbox*.py                    # Sandbox tests
└── test_z_comprehensive_e2e.py         # Full integration tests
```

### Documentation (Rename files)
```
docs/
├── blazing-flow-endpoints.md           # Main endpoints guide (was web-endpoints.md)
├── blazing-flow-endpoints-tests.md     # Test documentation (was web-endpoints-tests.md)
└── blazing-flow-sandbox.md             # Sandbox guide
```

## SEO and Keywords

### Primary Keywords
- "Blazing Flow"
- "Python workflow orchestration"
- "distributed workflows"
- "async workflow engine"

### Feature-Specific Keywords
- "Blazing Flow Sandbox" + "WASM isolation", "untrusted code execution"
- "Blazing Flow Endpoints" + "workflow API", "HTTP endpoints", "WebSocket workflows"

### Avoid Confusion With
- Apache Airflow (different use case)
- Prefect (different architecture)
- Temporal (different paradigm)
- FastAPI (we use it, but we're not a FastAPI wrapper)

## Version History

- **v1.x**: Used "route" and "station" terminology
- **v2.0**: Renamed to "workflow" and "step"
- **v2.1**: Introduced "Blazing Flow" branding, sub-features named

## Related Products (Future)

- **Blazing Flow Gateway**: API gateway/routing layer (separate product)
- **Blazing Flow Cloud**: Hosted/managed service
- **Blazing Flow Enterprise**: Self-hosted enterprise edition

---

**Last Updated:** 2025-12-09
**Status:** Official branding guide
