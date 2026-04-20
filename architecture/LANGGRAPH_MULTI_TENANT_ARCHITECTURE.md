# LangGraph Multi-Tenant Architecture for Blazing

## Executive Summary

This document describes the architecture for running **REAL LangGraph** (not a compatible implementation) on Blazing's distributed execution engine with full multi-tenant isolation. Each tenant gets:

- Isolated conversation state (checkpoints)
- Their own LLM providers and API keys
- Custom tools and prompts
- Separate scaling and billing

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              BLAZING PLATFORM                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        TENANT A: "acme-corp"                            │ │
│  │  ┌───────────────────────────────────────────────────────────────────┐ │ │
│  │  │  AcmeAgentService(LangGraphService)                               │ │ │
│  │  │  ├── connectors: {openai: AcmeOpenAIConnector(key="sk-acme...")} │ │ │
│  │  │  ├── tenant_id: "acme-corp"                                       │ │ │
│  │  │  ├── tools: [search_acme_docs, query_acme_db, ...]               │ │ │
│  │  │  └── checkpointer: RedisCheckpointer(tenant_id="acme-corp")      │ │ │
│  │  │                                                                    │ │ │
│  │  │  Redis Keys:                                                       │ │ │
│  │  │  └── blazing:langgraph:checkpoint:acme-corp:thread-*              │ │ │
│  │  └───────────────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        TENANT B: "globex-inc"                           │ │
│  │  ┌───────────────────────────────────────────────────────────────────┐ │ │
│  │  │  GlobexAgentService(LangGraphService)                             │ │ │
│  │  │  ├── connectors: {anthropic: GlobexClaudeConnector(key="...")}   │ │ │
│  │  │  ├── tenant_id: "globex-inc"                                      │ │ │
│  │  │  ├── tools: [search_globex_wiki, globex_api, ...]                │ │ │
│  │  │  └── checkpointer: RedisCheckpointer(tenant_id="globex-inc")     │ │ │
│  │  │                                                                    │ │ │
│  │  │  Redis Keys:                                                       │ │ │
│  │  │  └── blazing:langgraph:checkpoint:globex-inc:thread-*             │ │ │
│  │  └───────────────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ═══════════════════════════════════════════════════════════════════════════ │
│                              BLAZING INFRASTRUCTURE                           │
│  ═══════════════════════════════════════════════════════════════════════════ │
│                                                                               │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────────────────┐ │
│  │ Trusted        │    │ Sandboxed      │    │ Redis (Coordination +     │ │
│  │ Workers        │    │ Workers        │    │ Data Storage)             │ │
│  │ (Services run  │    │ (User code     │    │                           │ │
│  │  here)         │    │  runs here)    │    │ Tenant-isolated keys      │ │
│  └────────────────┘    └────────────────┘    └────────────────────────────┘ │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Security Model

### Trust Boundaries

| Layer | Trust Level | What Runs Here | Access |
|-------|-------------|----------------|--------|
| **Blazing Platform** | Highest | Coordinator, routing, scaling | Full infrastructure |
| **Tenant Services** | High | LangGraphService, Connectors | Tenant's API keys, DB credentials |
| **Sandboxed Steps** | Untrusted | User-provided code in Pyodide WASM | Service invocation only |

### Tenant Isolation

1. **Checkpoint Isolation**: Each tenant's checkpoints are stored under separate Redis key prefixes
   - Tenant A: `blazing:langgraph:checkpoint:acme-corp:*`
   - Tenant B: `blazing:langgraph:checkpoint:globex-inc:*`

2. **Credential Isolation**: Each tenant brings their own connectors with their own API keys
   - Tenant A uses their OpenAI key
   - Tenant B uses their Anthropic key

3. **Tool Isolation**: Each tenant defines their own tools
   - Tenant A's tools can access Acme's internal databases
   - Tenant B's tools can access Globex's APIs

## Implementation Components

### 1. LangGraphService (Core Service)

The `LangGraphService` class wraps the REAL LangGraph library and runs on trusted workers.

**Location**: `src/blazing/langgraph/services.py`

```python
from blazing.langgraph import LangGraphService
from blazing.base import BaseService

@app.service
class MyAgentService(LangGraphService):
    """Tenant-specific agent service."""

    async def _async_init(self):
        await self.build_react_agent(
            tools=[search_web, query_database],
            model="gpt-4",
            provider="openai",  # or "anthropic", "azure_openai", "google"
            system_prompt="You are a helpful assistant for Acme Corp.",
            checkpointer=RedisCheckpointer(tenant_id="acme-corp"),
        )
```

**Features**:
- Multi-provider LLM support (OpenAI, Anthropic, Azure, Google)
- Automatic tenant isolation for checkpoints
- Real LangGraph ReAct agent or custom graph support
- Message conversion between dict and LangChain formats

### 2. Multi-Provider LLM Support

The service supports multiple LLM providers through the `provider` parameter:

```python
# OpenAI (default)
await service.build_react_agent(
    tools=[...],
    model="gpt-4",
    provider="openai",
)

# Anthropic Claude
await service.build_react_agent(
    tools=[...],
    model="claude-3-opus-20240229",
    provider="anthropic",
)

# Azure OpenAI
await service.build_react_agent(
    tools=[...],
    model="gpt-4",
    provider="azure_openai",
    azure_deployment="my-gpt4-deployment",
)

# Google Gemini
await service.build_react_agent(
    tools=[...],
    model="gemini-pro",
    provider="google",
)
```

**Required Packages per Provider**:
| Provider | Package | Install Command |
|----------|---------|-----------------|
| OpenAI | langchain-openai | `pip install langchain-openai` |
| Anthropic | langchain-anthropic | `pip install langchain-anthropic` |
| Azure | langchain-openai | `pip install langchain-openai` |
| Google | langchain-google-genai | `pip install langchain-google-genai` |

### 3. Tenant-Aware Checkpointing

**Location**: `src/blazing/langgraph/checkpointer.py`

#### RedisCheckpointer with tenant_id

```python
from blazing.langgraph import RedisCheckpointer

# Create tenant-isolated checkpointer
checkpointer = RedisCheckpointer(
    redis_url="redis://localhost:6379",
    tenant_id="acme-corp",
)

# Keys are automatically namespaced:
# blazing:langgraph:checkpoint:acme-corp:thread-123
```

#### Dynamic Tenant Switching

```python
# Base checkpointer (shares Redis connection)
base = RedisCheckpointer()

# Create tenant-specific checkpointers dynamically
tenant_a = base.for_tenant("acme-corp")
tenant_b = base.for_tenant("globex-inc")

# Use based on request context
async def handle_request(request):
    tenant_id = request.headers.get("X-Tenant-ID")
    checkpointer = base.for_tenant(tenant_id)
    # ...
```

#### TenantCheckpointer Wrapper

Wraps ANY checkpointer (including LangGraph's native ones) with tenant isolation:

```python
from langgraph.checkpoint.memory import MemorySaver
from blazing.langgraph import TenantCheckpointer

# Wrap LangGraph's native MemorySaver
base_saver = MemorySaver()
tenant_saver = TenantCheckpointer(base_saver, tenant_id="acme-corp")

# Use with real LangGraph
app = graph.compile(checkpointer=tenant_saver)
```

### 4. Custom Graph Support

For complex multi-agent systems, use `build_custom_graph()`:

```python
@app.service
class ResearchTeamService(LangGraphService):
    async def _async_init(self):
        await self.build_custom_graph(
            graph_builder=self._build_research_team,
            model="gpt-4",
            provider="openai",
            checkpointer=RedisCheckpointer(tenant_id="acme-corp"),
        )

    def _build_research_team(self, llm, checkpointer):
        from langgraph.graph import StateGraph, START, END
        from langgraph.prebuilt import create_react_agent

        # Create specialized agents
        researcher = create_react_agent(llm, [search_web, read_papers])
        coder = create_react_agent(llm, [write_code, run_tests])

        # Build supervisor graph
        class State(TypedDict):
            messages: list
            task: str
            next: str

        async def supervisor(state):
            if "code" in state["task"].lower():
                return {"next": "coder"}
            return {"next": "researcher"}

        graph = StateGraph(State)
        graph.add_node("supervisor", supervisor)
        graph.add_node("researcher", researcher)
        graph.add_node("coder", coder)
        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges("supervisor", lambda s: s["next"])
        graph.add_edge("researcher", END)
        graph.add_edge("coder", END)

        return graph.compile(checkpointer=checkpointer)
```

## Execution Flow

### Service Invocation from Sandboxed Code

```
┌─────────────────────────────────────────────────────────────────────────┐
│ SANDBOXED STEP (Pyodide WASM - No Network Access)                       │
│                                                                          │
│  @app.route                                                              │
│  async def process_query(query: str, services=None):                    │
│      # Call LangGraph agent via service invocation                      │
│      result = await services['MyAgentService'].invoke(                  │
│          messages=[{"role": "user", "content": query}],                 │
│          config={"thread_id": f"user-{user_id}"}                        │
│      )                                                                   │
│      return result                                                       │
│                                                                          │
│  ↓ Service Invocation Bridge                                            │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ TRUSTED WORKER (Full Network Access)                                    │
│                                                                          │
│  LangGraphService.invoke()                                               │
│      ↓                                                                   │
│  Real LangGraph Agent Execution                                          │
│      ├── Convert messages to LangChain format                           │
│      ├── Invoke langgraph.prebuilt.create_react_agent                   │
│      ├── LLM calls via langchain-openai/anthropic                       │
│      ├── Tool execution with real network access                        │
│      ├── Checkpoint save via TenantCheckpointer                         │
│      └── Convert result back to dict format                             │
│                                                                          │
│  ↓ Return result                                                        │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ REDIS (Tenant-Isolated Storage)                                         │
│                                                                          │
│  Checkpoints:                                                            │
│  └── blazing:langgraph:checkpoint:acme-corp:user-123                    │
│      └── state: {"messages": [...], ...}                                │
│      └── metadata: {"next_node": "agent", ...}                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## API Reference

### LangGraphService

```python
class LangGraphService(BaseService):
    """Multi-tenant service to run REAL LangGraph agents."""

    def __init__(
        self,
        connectors: Dict[str, Any] = None,
        tenant_id: str = None,  # Optional tenant for isolation
    ): ...

    async def build_react_agent(
        self,
        tools: List[Callable],
        model: str = "gpt-4",
        provider: str = "openai",  # openai, anthropic, azure_openai, google
        system_prompt: str = None,
        checkpointer: Any = None,
        temperature: float = 0.7,
        **llm_kwargs,
    ) -> None: ...

    async def build_custom_graph(
        self,
        graph_builder: Callable[[LLM, Checkpointer], CompiledGraph],
        model: str = "gpt-4",
        provider: str = "openai",
        checkpointer: Any = None,
        temperature: float = 0.7,
        **llm_kwargs,
    ) -> None: ...

    async def invoke(
        self,
        messages: List[Dict[str, Any]],
        config: Dict[str, Any] = None,  # thread_id, recursion_limit
    ) -> Dict[str, Any]: ...

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        config: Dict[str, Any] = None,
    ) -> AsyncIterator[Dict[str, Any]]: ...

    async def get_state(
        self,
        config: Dict[str, Any],  # thread_id required
    ) -> Optional[Dict[str, Any]]: ...

    async def update_state(
        self,
        config: Dict[str, Any],  # thread_id required
        values: Dict[str, Any],
        as_node: str = None,
    ) -> None: ...
```

### RedisCheckpointer

```python
class RedisCheckpointer:
    """Redis-backed checkpointer with multi-tenant support."""

    def __init__(
        self,
        redis_url: str = None,  # Defaults to REDIS_URL env var
        key_prefix: str = "blazing:langgraph:checkpoint",
        tenant_id: str = None,  # Optional tenant isolation
        max_history: int = 10,
    ): ...

    def for_tenant(self, tenant_id: str) -> "RedisCheckpointer":
        """Create tenant-scoped checkpointer (shares connection)."""
        ...

    async def save(
        self,
        thread_id: str,
        state: dict,
        metadata: dict = None,
    ) -> str: ...

    async def load(self, thread_id: str) -> Optional[Dict[str, Any]]: ...

    async def list(self, thread_id: str) -> List[Dict[str, Any]]: ...

    async def delete(self, thread_id: str) -> int: ...
```

### TenantCheckpointer

```python
class TenantCheckpointer:
    """Wrapper that adds tenant isolation to any checkpointer."""

    def __init__(
        self,
        base_checkpointer: Any,  # Any checkpointer with save/load/list/delete
        tenant_id: str,
    ): ...

    # Implements same interface as wrapped checkpointer
    # All thread_ids are automatically prefixed with tenant_id
```

## Complete Example: Multi-Tenant Agent Platform

```python
from typing import TypedDict, List, Dict, Any
from blazing import Blazing
from blazing.base import BaseService
from blazing.langgraph import LangGraphService, RedisCheckpointer
from langchain_core.tools import tool

# Initialize Blazing
app = Blazing(api_url="http://localhost:8000", api_token="...")

# =============================================================================
# Define Tenant A's Agent Service
# =============================================================================

@tool
def search_acme_docs(query: str) -> str:
    """Search Acme Corp's internal documentation."""
    # Real implementation would search Acme's docs
    return f"Found docs for: {query}"

@tool
def query_acme_crm(customer_id: str) -> str:
    """Query Acme's CRM for customer information."""
    # Real implementation would query Acme's CRM
    return f"Customer {customer_id} info: Premium tier, 50 employees"

@app.service
class AcmeAgentService(LangGraphService):
    """Agent service for Acme Corp."""

    async def _async_init(self):
        await self.build_react_agent(
            tools=[search_acme_docs, query_acme_crm],
            model="gpt-4",
            provider="openai",
            system_prompt=(
                "You are an AI assistant for Acme Corp. "
                "Help employees find information and answer questions. "
                "Use tools to search docs and CRM when needed."
            ),
            checkpointer=RedisCheckpointer(tenant_id="acme-corp"),
        )

# =============================================================================
# Define Tenant B's Agent Service (Different provider, different tools)
# =============================================================================

@tool
def search_globex_wiki(query: str) -> str:
    """Search Globex Inc's internal wiki."""
    return f"Wiki results for: {query}"

@tool
def globex_inventory_check(sku: str) -> str:
    """Check Globex inventory levels."""
    return f"SKU {sku}: 1,234 units in stock"

@app.service
class GlobexAgentService(LangGraphService):
    """Agent service for Globex Inc - uses Claude instead of GPT."""

    async def _async_init(self):
        await self.build_react_agent(
            tools=[search_globex_wiki, globex_inventory_check],
            model="claude-3-opus-20240229",
            provider="anthropic",  # Different provider!
            system_prompt=(
                "You are an AI assistant for Globex Inc. "
                "Help with inventory management and knowledge base searches."
            ),
            checkpointer=RedisCheckpointer(tenant_id="globex-inc"),
        )

# =============================================================================
# Routes (Sandboxed) - Call services via invocation bridge
# =============================================================================

@app.route
async def acme_chat(query: str, user_id: str, services=None):
    """Chat endpoint for Acme Corp users."""
    result = await services['AcmeAgentService'].invoke(
        messages=[{"role": "user", "content": query}],
        config={"thread_id": f"acme-{user_id}"}
    )
    return result["messages"][-1]["content"]

@app.route
async def globex_chat(query: str, user_id: str, services=None):
    """Chat endpoint for Globex Inc users."""
    result = await services['GlobexAgentService'].invoke(
        messages=[{"role": "user", "content": query}],
        config={"thread_id": f"globex-{user_id}"}
    )
    return result["messages"][-1]["content"]

# =============================================================================
# Publish and Run
# =============================================================================

if __name__ == "__main__":
    # Register with Blazing
    app.publish()

    # Create tasks
    import asyncio

    async def main():
        # Acme Corp user asks a question
        acme_result = await app.create_route_task(
            "acme_chat",
            query="What's our refund policy?",
            user_id="alice@acme.com"
        ).result()
        print(f"Acme response: {acme_result}")

        # Globex Inc user asks a question
        globex_result = await app.create_route_task(
            "globex_chat",
            query="Check inventory for SKU-12345",
            user_id="bob@globex.com"
        ).result()
        print(f"Globex response: {globex_result}")

    asyncio.run(main())
```

## Redis Key Structure

```
blazing:langgraph:checkpoint:{tenant_id}:{thread_id}
├── state: JSON-encoded graph state
├── metadata: JSON-encoded metadata (next_node, etc.)
├── checkpoint_id: Unique checkpoint identifier
├── created_at: ISO timestamp
└── updated_at: ISO timestamp

blazing:langgraph:checkpoint:{tenant_id}:{thread_id}:history
└── List of checkpoint_ids (max 10 by default)
```

## Test Coverage

The implementation includes 103 tests:
- **75 unit tests**: Graph construction, state management, edge traversal, callbacks
- **28 integration tests**: LangGraphService, multi-provider LLM, tenant checkpointing

Run tests:
```bash
# All LangGraph tests
uv run pytest tests/test_langgraph_unit.py tests/test_langgraph_real.py -v

# Just multi-tenant tests
uv run pytest tests/test_langgraph_real.py::TestTenantCheckpointer -v
```

## Dependencies

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
langgraph = [
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.2.0",
]
```

Install:
```bash
pip install blazing[langgraph]

# For other providers
pip install langchain-anthropic  # Claude
pip install langchain-google-genai  # Gemini
pip install langchain-aws  # AWS Bedrock
```

## Production Features

### Automatic Retry with Exponential Backoff

All LLM calls include automatic retry logic:

```python
result = await service.invoke(
    messages=[{"role": "user", "content": "Hello"}],
    retry=True,  # Enable retry (default)
    max_retries=3,  # Maximum attempts
)
```

Retry behavior:
- Exponential backoff: 1s → 2s → 4s → ... up to 60s
- Jitter: Random 0-25% added to prevent thundering herd
- Logs warnings for each retry attempt

### Observability & Metrics

Built-in metrics collection for all LLM calls:

```python
from blazing.langgraph.services import _metrics_collector, LLMMetrics

# Add custom callback for metrics
def send_to_datadog(metrics: LLMMetrics):
    # Send to your observability platform
    datadog.increment('llm.calls', tags=[
        f'provider:{metrics.provider}',
        f'model:{metrics.model}',
        f'tenant:{metrics.tenant_id}',
    ])
    datadog.histogram('llm.latency', metrics.latency_ms)

_metrics_collector.add_callback(send_to_datadog)
```

Metrics captured:
- `provider`: LLM provider (openai, anthropic, etc.)
- `model`: Model name
- `latency_ms`: Request latency in milliseconds
- `success`: Whether the call succeeded
- `error`: Error message if failed
- `tenant_id`: Tenant identifier
- `thread_id`: Conversation thread

### Connection Pooling

Redis checkpointer uses connection pooling for high concurrency:

```python
checkpointer = RedisCheckpointer(
    pool_size=20,  # Max connections in pool
    socket_timeout=5.0,  # Timeout in seconds
)
```

### AWS Bedrock Support

Use Claude, Titan, or Llama models via AWS Bedrock:

```python
await service.build_react_agent(
    tools=[...],
    model="anthropic.claude-3-opus-20240229-v1:0",
    provider="bedrock",
    region_name="us-east-1",
)
```

## Future Enhancements

1. ~~**Observability Integration**~~: ✅ Built-in metrics collection
2. **Rate Limiting**: Per-tenant LLM call rate limiting
3. **Cost Tracking**: Track LLM costs per tenant for billing
4. **Human-in-the-Loop**: Interrupt graphs for human approval
5. **Graph Visualization**: Export graph structure for debugging
6. **Streaming to WebSockets**: Stream agent responses to frontend
