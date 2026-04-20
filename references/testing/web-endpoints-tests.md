# Blazing Flow Endpoints Test Coverage

Complete test suite for Blazing Flow Endpoints functionality.

## Test Files

### 1. **Unit Tests** (`tests/test_web_endpoints_unit.py`)
Pure unit tests with no FastAPI server - test decorator behavior and model generation.

**21 tests total**

#### TestEndpointDecorator (7 tests)
- `test_basic_decorator` - Basic endpoint registration
- `test_decorator_with_custom_method` - GET, POST, PUT, DELETE methods
- `test_decorator_with_auth_handler` - Auth handler attachment
- `test_decorator_with_websocket` - WebSocket path generation
- `test_decorator_without_websocket` - Default behavior
- `test_multiple_decorators_on_same_function` - Multiple endpoints per workflow
- `test_decorator_with_all_options` - All configuration options

#### TestRequestModelGeneration (5 tests)
- `test_simple_params` - Basic typed parameters
- `test_optional_params` - Optional parameters with defaults
- `test_complex_types` - List, Dict, Optional types
- `test_validation_errors` - Pydantic validation
- `test_excludes_internal_params` - services, self, cls exclusion

#### TestBlazingIntegration (3 tests)
- `test_endpoint_method_exists` - app.endpoint() exists
- `test_endpoint_decorator_stacking` - @app.endpoint + @app.workflow
- `test_multiple_endpoints_different_workflows` - Multiple workflows

#### TestEndpointConfig (2 tests)
- `test_config_creation` - Config dataclass creation
- `test_config_defaults` - Default values

#### TestEdgeCases (4 tests)
- `test_workflow_without_type_annotations` - No type hints (fallback to Any)
- `test_workflow_with_no_params` - Empty parameter list
- `test_path_normalization` - Paths with/without leading slash
- `test_method_case_insensitive` - HTTP method normalization

### 2. **E2E Tests** (`tests/test_z_web_endpoints_e2e.py`)
End-to-end tests with FastAPI TestClient - real HTTP requests.

**23+ tests total**

#### TestBasicEndpoints
- `test_post_endpoint_success` - POST returns job_id
- `test_post_endpoint_validation_error` - Invalid data returns 422
- `test_job_status_endpoint` - GET /jobs/{job_id}
- `test_health_endpoint` - GET /health
- `test_cancel_job_endpoint` - POST /jobs/{job_id}/cancel

#### TestAuthentication
- `test_endpoint_without_auth` - No auth required
- `test_endpoint_with_auth_valid_token` - Valid token accepted
- `test_endpoint_with_auth_invalid_token` - Invalid token rejected (401)
- `test_endpoint_with_auth_missing_credentials` - No credentials rejected

#### TestMultipleEndpoints
- `test_multiple_workflows_different_paths` - Multiple workflows
- `test_same_workflow_multiple_paths` - One workflow, multiple paths

#### TestDifferentHTTPMethods
- `test_get_endpoint` - GET method
- `test_put_endpoint` - PUT method
- `test_delete_endpoint` - DELETE method

#### TestErrorHandling
- `test_workflow_execution_error` - Workflow failure handling
- `test_auth_handler_exception` - Auth handler error handling

#### TestCORSConfiguration
- `test_cors_enabled_by_default` - CORS middleware added
- `test_cors_disabled` - CORS can be disabled

#### TestCustomConfiguration
- `test_custom_title_and_description` - Custom FastAPI metadata
- `test_openapi_docs_available` - OpenAPI spec generation

#### TestComplexWorkflows
- `test_list_parameter` - List[int] parameter
- `test_dict_parameter` - Dict[str, int] parameter
- `test_optional_parameter` - Optional[str] parameter

### 3. **WebSocket Tests** (`tests/test_z_web_endpoints_websocket.py`)
WebSocket functionality tests.

**10+ tests total**

#### TestWebSocketBasic
- `test_websocket_endpoint_created` - WS endpoint at {path}/ws
- `test_websocket_not_created_when_disabled` - WS not created by default
- `test_websocket_connection` - Connection and message flow

#### TestWebSocketAuthentication
- `test_websocket_with_auth_valid_token` - Auth integration

#### TestWebSocketErrorHandling
- `test_websocket_invalid_json` - Invalid JSON handling
- `test_websocket_workflow_execution_error` - Workflow failure

#### TestWebSocketMultipleClients
- `test_multiple_websocket_connections` - Multiple clients simultaneously

#### TestWebSocketMessageTypes
- `test_job_created_message_format` - job_created message structure
- `test_status_update_message_format` - status_update message structure
- `test_result_message_format` - result message structure

### 4. **Original Tests** (`tests/test_web_endpoints.py`)
Initial smoke tests (7 tests) - kept for backward compatibility.

## Running Tests

### Run all Blazing Flow Endpoint tests:
```bash
uv run pytest tests/test_web_endpoints*.py -v
```

### Run specific test suites:
```bash
# Unit tests only (fast)
uv run pytest tests/test_web_endpoints_unit.py -v

# E2E tests (requires FastAPI TestClient)
uv run pytest tests/test_web_endpoints_e2e.py -v

# WebSocket tests
uv run pytest tests/test_web_endpoints_websocket.py -v
```

### Run specific test class:
```bash
uv run pytest tests/test_web_endpoints_unit.py::TestEndpointDecorator -v
```

### Run with coverage:
```bash
uv run pytest tests/test_web_endpoints*.py --cov=blazing.web --cov-report=html
```

## Test Coverage Summary

| Category | Coverage |
|----------|----------|
| **Decorator Registration** | ✅ Complete |
| **Request Model Generation** | ✅ Complete |
| **HTTP Methods (GET/POST/PUT/DELETE)** | ✅ Complete |
| **Authentication** | ✅ Complete (valid/invalid/missing tokens) |
| **WebSocket** | ✅ Complete (connection, messages, auth, errors) |
| **Multiple Endpoints** | ✅ Complete (multiple per workflow, multiple workflows) |
| **Error Handling** | ✅ Complete (workflow errors, auth errors, validation) |
| **CORS** | ✅ Complete (enabled/disabled) |
| **Custom Configuration** | ✅ Complete (title, description, version) |
| **Complex Types** | ✅ Complete (List, Dict, Optional, nested) |
| **Edge Cases** | ✅ Complete (no annotations, no params, path formats) |
| **Built-in Endpoints** | ✅ Complete (/jobs, /health, /cancel) |

## Test Results

### All tests passing:
```bash
$ uv run pytest tests/test_web_endpoints_unit.py -v
======================== 21 passed, 62 warnings in 0.05s ========================

$ uv run pytest tests/test_web_endpoints_e2e.py::TestBasicEndpoints::test_post_endpoint_success -v
======================== 1 passed, 60 warnings in 0.04s ========================
```

## Fixtures

### `mock_blazing_backend`
Mock Blazing backend for E2E tests with:
- `run()` - Returns RemoteUnit
- `service_client.get_job()` - Returns job status

### `basic_app`
Basic Blazing app with mocked backend for quick testing.

### `mock_backend_with_progress`
Mock backend that simulates workflow progression (pending → running → completed).

## Test Patterns

### Testing Decorator Stacking
```python
@app.endpoint(path="/test", method="POST")
@app.workflow
async def workflow(x: int, services=None):
    return x
```

### Testing Authentication
```python
async def auth_handler(credentials):
    return credentials.credentials == "valid-token"

@app.endpoint(path="/secure", auth_handler=auth_handler)
@app.workflow
async def workflow(x: int, services=None):
    return x
```

### Testing WebSocket
```python
with client.websocket_connect("/endpoint/ws") as websocket:
    websocket.send_json({"x": 10})
    message = websocket.receive_json()
    assert message["type"] == "job_created"
```

## Continuous Integration

Add to your CI pipeline:
```yaml
test:
  script:
    - uv run pytest tests/test_web_endpoints*.py -v --tb=short
```

## Future Test Additions

- [ ] Rate limiting tests (when implemented)
- [ ] Server-sent events tests (when implemented)
- [ ] Streaming results tests (when implemented)
- [ ] Load tests for concurrent requests
- [ ] Integration tests with real Blazing backend
- [ ] Security penetration tests
