# Python Version Compatibility Matrix

This document provides a comprehensive overview of Python version support in Blazing v1.7+, including executor compatibility, Pyodide version mapping, wheel handling, and snapshot behavior.

## Supported Python Versions

| Python Version | Patch Version | Status | Default |
|----------------|---------------|--------|---------|
| 3.11 | 3.11.9 | Supported | No |
| 3.12 | 3.12.7 | Supported | **Yes** (default for existing apps) |
| 3.13 | 3.13.1 | Supported | No |

**Minimum supported version:** Python 3.11

Versions below 3.11 are rejected at publish time with a validation error. This ensures compatibility with modern Python features and security updates.

## Executor Support Matrix

| Feature | Docker Executor | Pyodide Executor |
|---------|----------------|-----------------|
| **Python 3.11** | Yes (pyenv) | Yes (Pyodide 0.25.1) |
| **Python 3.12** | Yes (pyenv) | Yes (Pyodide 0.27.7) |
| **Python 3.13** | Yes (pyenv) | Yes (Pyodide 0.28.3) |
| **Version switching** | Runtime (pyenv shell) | Container-per-version |
| **Native wheels** | Yes | No (WASM only) |
| **Snapshot support** | Yes | No |
| **Cold start time** | ~500ms-2s | ~100-300ms |
| **Memory overhead** | Higher (full Python) | Lower (WASM) |

### Docker Executor

- **Architecture**: Single container with pyenv managing multiple Python versions
- **Base image**: `python:3.13-slim` with pyenv installed
- **Installed versions**: 3.11.9, 3.12.7, 3.13.1
- **Default version**: 3.12.7 (set via `pyenv global`)
- **Runtime activation**: Uses `PYENV_VERSION` environment variable to activate the correct version before code execution
- **Snapshots**: Supported with version validation (dill serialization)

### Pyodide Executor

- **Architecture**: Separate containers per Python version
- **Base image**: `node:20-slim` with Pyodide installed via npm
- **Version routing**: Coordinator routes to version-specific container based on service metadata
- **Snapshots**: Not supported (Pyodide limitation)
- **Use case**: Fast cold starts for lightweight Python workloads

## Pyodide Version Mapping

Each Pyodide version is compiled for a specific Python version. Cross-version usage is **not supported**.

| Python Version | Pyodide Version | npm Package | Container Port | Build ARG |
|----------------|----------------|-------------|----------------|-----------|
| 3.11 | 0.25.1 | pyodide@0.25.1 | 8011 | `PYODIDE_VERSION=0.25.1` |
| 3.12 | 0.27.7 | pyodide@0.27.7 | 8012 | `PYODIDE_VERSION=0.27.7` |
| 3.13 | 0.28.3 | pyodide@0.28.3 | 8013 | `PYODIDE_VERSION=0.28.3` |

**Why separate containers?**

Pyodide's WASM runtime is tied to the Python version it was compiled with. Unlike CPython (which can have multiple versions via pyenv), each Pyodide npm package contains a pre-compiled WASM binary for a specific Python minor version.

**Port 8004 (backward compatibility):**

Port 8004 continues to run Python 3.12/Pyodide 0.27.7 for backward compatibility with pre-v1.7 deployments. This is the default fallback when the ExecutorRegistry is empty.

## Wheel Compatibility

Wheels are built and stored based on whether they contain C extensions (native code) or are pure Python.

| Wheel Type | Cross-Version | Storage Path | Detection Method |
|------------|---------------|-------------|------------------|
| **Pure Python** (`py3-none-any`) | Yes (shared) | `wheels/{app_id}/pure/{filename}` | `packaging.utils.parse_wheel_filename()` checks `abi='none'` |
| **Native** (`cp311-...`, `cp312-...`, `cp313-...`) | No (version-specific) | `wheels/{app_id}/{version}/{filename}` | `abi != 'none'` (e.g., `cp312`, `abi3`) |

### Pure Python Wheels

Pure Python wheels are built once and shared across all Python versions. The platform:
1. Detects pure Python wheels using `packaging.utils.parse_wheel_filename()`
2. Sets `effective_version='pure'` in WheelDAO
3. Stores in `wheels/{app_id}/pure/` directory
4. Reuses the same wheel for 3.11, 3.12, and 3.13 services

### Native Wheels

Native wheels contain C extensions and are compiled for a specific Python version. The platform:
1. Detects native wheels by checking `abi != 'none'`
2. Sets `effective_version` to the service's `python_version` (e.g., `'3.12'`)
3. Stores in `wheels/{app_id}/{version}/` directory
4. Builds separate wheels for each Python version using version-matched build containers

**Build container versioning:**

Native wheels are built using Docker containers with the target Python version installed:
```dockerfile
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim
# Build dependencies installed here
```

## Snapshot Compatibility

Blazing uses [dill](https://github.com/uqfoundation/dill) for Python environment serialization. Dill snapshots are **not portable across Python minor versions**.

| Scenario | Behavior | Implementation |
|----------|----------|----------------|
| **Same version restore** | Normal restoration | Snapshot `python_version` matches executor version |
| **Cross-version restore** | Rejected, cold start fallback | Executor checks `snapshot.python_version != executor.python_version` |
| **Version change** | Snapshot auto-invalidated | Publish pipeline calls `snapshot_dao.invalidate_all()` when version changes |
| **Environment change** | Snapshot auto-invalidated | Dependencies/code changes trigger invalidation (existing behavior) |
| **Pre-v1.7 snapshot** | Restored normally (backward compat) | Snapshots without `python_version` metadata default to 3.12 |

### Implementation Details

**SNAP-01: Snapshot Tagging**

Every snapshot is tagged with the `python_version` it was created with:
```python
snapshot_metadata = {
    "python_version": service.python_version,  # e.g., "3.12"
    "app_id": app_id,
    "service_name": service_name,
    # ...
}
```

**SNAP-02: Version Mismatch Detection**

At executor startup, the snapshot is rejected if versions don't match:
```python
if snapshot.python_version != executor.python_version:
    logger.warning(f"Snapshot version mismatch: {snapshot.python_version} != {executor.python_version}")
    return None  # Cold start fallback
```

**SNAP-03: Automatic Invalidation on Version Change**

When `blazing publish --python-version X.Y` changes a service's version:
```python
if new_version != old_version:
    await snapshot_dao.invalidate_all(app_id=app_id, service_name=service_name)
```

## Docker Image Architecture

Blazing uses multi-stage builds with shared base layers to minimize image size and build time.

| Component | Base Image | Pyenv Versions | Purpose |
|-----------|-----------|----------------|---------|
| **executor-base** | `python:3.13-slim` | 3.11.9, 3.12.7, 3.13.1 | Shared base layer with pyenv and all Python versions |
| **executor** | `blazing-executor-base` | Inherited from base | Final runtime image (build dependencies excluded) |
| **pyodide-executor** | `node:20-slim` | N/A (Pyodide handles Python) | Node.js runtime for Pyodide WASM execution |

### Dockerfile.executor Structure

```dockerfile
# Stage 1: Base layer with pyenv and all Python versions
FROM python:3.13-slim as executor-base
RUN apt-get update && apt-get install -y \
    build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev \
    curl git
ENV PYENV_ROOT="/root/.pyenv"
ENV PATH="$PYENV_ROOT/bin:$PATH"
RUN curl https://pyenv.run | bash
RUN pyenv install 3.11.9 && \
    pyenv install 3.12.7 && \
    pyenv install 3.13.1 && \
    pyenv global 3.12.7

# Stage 2: Final runtime image (build deps excluded)
FROM executor-base
# Runtime code copied here
```

**Why Python 3.13-slim as base?**

Using the latest Python version as the base image ensures access to the newest security updates and stdlib improvements. Older Python versions (3.11, 3.12) are installed via pyenv for backward compatibility.

## Known Limitations

### Dill Serialization Limitations

- **Not portable across Python minor versions**: A snapshot created on Python 3.12 cannot be restored on Python 3.13
- **Binary compatibility**: Dill relies on Python's internal object representation, which changes between minor versions
- **Mitigation**: Version validation prevents cross-version restoration, ensuring cold start fallback instead of deserialization failures

### Pyodide Package Availability

- **Pyodide 0.25.1 (Python 3.11)**: Has fewer supported packages than 0.27.7/0.28.3 due to older Pyodide release
- **WASM compilation**: Not all Python packages can be compiled to WASM (e.g., packages with system-level dependencies)
- **Check availability**: Use [Pyodide package index](https://pyodide.org/en/stable/usage/packages-in-pyodide.html) to verify package support

### Native Wheel Building

- **Version-matched build containers required**: Native wheels must be built using a container with the target Python version installed
- **Build time overhead**: Building wheels for 3 Python versions takes ~3x longer than building for a single version
- **Mitigation**: Pure Python wheels are shared (no rebuild), reducing overhead for most packages

### Snapshot Support

- **Docker executor only**: Snapshots are not supported on Pyodide executor due to Pyodide limitations
- **Cold start penalty**: Pyodide services always experience cold start latency (no snapshot warmth)
- **Use case**: Pyodide is best for lightweight, stateless workloads where cold start time (~100-300ms) is acceptable

## Version Selection Best Practices

### When to Use Python 3.11

- **Legacy dependencies**: Package requires Python 3.11 (not yet compatible with 3.12+)
- **Testing**: Verifying backward compatibility with older Python versions
- **Known limitation**: Fewer Pyodide packages available on 0.25.1

### When to Use Python 3.12 (Default)

- **General purpose**: Most production workloads
- **Balanced**: Good package availability on both CPython and Pyodide
- **Mature ecosystem**: Most packages have Python 3.12 wheels available
- **Zero-touch upgrade**: Existing apps auto-assigned to 3.12

### When to Use Python 3.13

- **Latest features**: Need Python 3.13-specific stdlib improvements (e.g., improved error messages)
- **Performance**: Python 3.13 includes performance optimizations (e.g., PEP 709 inlined comprehensions)
- **Future-proofing**: Preparing codebase for eventual Python 3.14+ migration
- **Known limitation**: Some packages may not have Python 3.13 wheels yet (fallback to source builds)

## Migration Checklist

For existing apps upgrading to v1.7:

- [ ] Verify local Python version: `python --version`
- [ ] Review service dependencies for Python 3.11+ compatibility
- [ ] Run `blazing publish` to auto-detect and assign Python version
- [ ] Check publish output for detected version
- [ ] Verify service runs correctly with assigned version
- [ ] (Optional) Test on different Python version using `--python-version` flag
- [ ] Update CI/CD pipelines to use Python 3.11+ if needed
- [ ] Review [migration guide](../migration/v1.7-python-version-migration.md) for detailed upgrade instructions

## References

- **Migration guide**: [v1.7 Migration Guide](../migration/v1.7-python-version-migration.md)
- **Pyodide documentation**: https://pyodide.org/en/stable/
- **pyenv documentation**: https://github.com/pyenv/pyenv
- **dill documentation**: https://github.com/uqfoundation/dill
- **Python 3.11 release notes**: https://docs.python.org/3.11/whatsnew/3.11.html
- **Python 3.12 release notes**: https://docs.python.org/3.12/whatsnew/3.12.html
- **Python 3.13 release notes**: https://docs.python.org/3.13/whatsnew/3.13.html
