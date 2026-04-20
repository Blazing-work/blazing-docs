# Executor Image Customization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow `@app.step` and `@app.workflow` decorators to accept an `image` parameter, enabling per-step/workflow custom Docker images with full system-level customization (apt, run_commands, copy_local_dir) for executor containers. Deprecate the restricted `ExecutorImage` in favor of `Image.executor()`.

**Architecture:** Add `Image.executor()` factory method that creates images based on `blazing-executor-base`. Wire `image=` parameter through decorators → step/workflow metadata → registry sync payload → `ExecutorRegistry` image-aware routing. Build custom images during `publish()` using existing `LocalBuildService` pipeline. Deprecate `ExecutorImage`/`ExecutorImageSpec`/`ExecutorImages`/`set_executor_image()`.

**Tech Stack:** Python dataclasses, Pydantic models, Docker, existing `Image`/`ImageSpec` classes, existing `LocalBuildService` build pipeline.

---

## Phase A: Image.executor() and Decorator Wiring

### Task 1: Add `Image.executor()` factory method

**Files:**
- Modify: `src/blazing/image.py:153-266` (Image class factory methods)
- Test: `tests/test_executor_image.py`

**Step 1: Write the failing test**

Add to `tests/test_executor_image.py` at the end of `TestImage` class (after line 362):

```python
    def test_executor(self):
        """Create image from executor base."""
        image = Image.executor()
        assert image.spec.base == "blazing-executor-base:latest"

    def test_executor_with_customization(self):
        """Executor image supports full customization."""
        image = (
            Image.executor()
            .apt_install("ffmpeg", "libgl1-mesa-glx")
            .pip_install("opencv-python", "moviepy")
            .run_commands("mkdir -p /models")
            .env(MODEL_PATH="/models")
        )
        assert image.spec.base == "blazing-executor-base:latest"
        assert "ffmpeg" in image.spec.apt_packages
        assert "opencv-python" in image.spec.pip_packages
        assert "mkdir -p /models" in image.spec.commands
        assert image.spec.env_vars["MODEL_PATH"] == "/models"

    def test_executor_generates_valid_dockerfile(self):
        """Executor image generates Dockerfile with correct base."""
        image = Image.executor().pip_install("pandas").apt_install("curl")
        dockerfile = image.to_dockerfile()
        lines = dockerfile.strip().split("\n")
        assert lines[0] == "FROM blazing-executor-base:latest"
        assert "apt-get install" in dockerfile
        assert "pip install" in dockerfile

    def test_executor_content_hash(self):
        """Executor image has valid content hash."""
        image = Image.executor().pip_install("torch")
        assert len(image.content_hash()) == 12

    def test_executor_serialization_roundtrip(self):
        """Executor image survives dict serialization."""
        original = Image.executor().pip_install("pandas").env(FOO="bar")
        data = original.to_dict()
        restored = Image.from_dict(data)
        assert restored.spec.base == "blazing-executor-base:latest"
        assert restored.spec.pip_packages == ["pandas"]
        assert restored.spec.env_vars == {"FOO": "bar"}
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_executor_image.py::TestImage::test_executor -v`
Expected: FAIL with `AttributeError: type object 'Image' has no attribute 'executor'`

**Step 3: Write minimal implementation**

Add to `src/blazing/image.py` in the `Image` class, after the `from_dockerfile` classmethod (after line 265):

```python
    @classmethod
    def executor(cls) -> "Image":
        """Create an image based on the Blazing executor base.

        This creates a fully-customizable Image (apt, pip, run_commands,
        copy_local_dir, env) that extends blazing-executor-base:latest.
        The executor base already includes all required runtime dependencies
        (FastAPI, uvicorn, dill, redis, httpx, orjson, cryptography, psutil,
        pyarrow, grpcio).

        Use this when steps or workflows need system libraries, pre-downloaded
        model weights, or custom compiled software in the executor container.

        Returns:
            A new Image instance based on blazing-executor-base

        Example:
            image = (
                Image.executor()
                .apt_install("ffmpeg", "libgl1-mesa-glx")
                .pip_install("opencv-python", "moviepy")
                .run_commands("huggingface-cli download model /models/m")
                .env(MODEL_PATH="/models/m")
            )

            @app.step(image=image)
            async def process_video(url: str, services=None) -> dict:
                ...
        """
        spec = ImageSpec(base="blazing-executor-base:latest")
        return cls(spec)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_executor_image.py::TestImage::test_executor tests/test_executor_image.py::TestImage::test_executor_with_customization tests/test_executor_image.py::TestImage::test_executor_generates_valid_dockerfile tests/test_executor_image.py::TestImage::test_executor_content_hash tests/test_executor_image.py::TestImage::test_executor_serialization_roundtrip -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/blazing/image.py tests/test_executor_image.py
git commit -m "feat: add Image.executor() factory method for full executor image customization"
```

---

### Task 2: Add `image` parameter to `@app.step` decorator

**Files:**
- Modify: `src/blazing/blazing.py:458-687` (step decorator)
- Test: `tests/test_executor_image.py`

**Step 1: Write the failing test**

Add a new test class at the end of `tests/test_executor_image.py`:

```python
class TestStepImageParameter:
    """Tests for image parameter on @app.step decorator."""

    def _make_app(self):
        """Create minimal Blazing instance for testing decorators."""
        from blazing import Blazing
        app = Blazing.__new__(Blazing)
        app._step_funcs = {}
        app._pending_steps = []
        app._pending_workflows = []
        app._workflow_funcs = {}
        app._code_validator = None
        return app

    def test_step_accepts_image_parameter(self):
        """@app.step(image=...) stores image spec in metadata."""
        from blazing import Image
        app = self._make_app()

        image = Image.executor().pip_install("pandas")

        @app.step(image=image)
        async def my_step(x: int, services=None):
            return x * 2

        assert len(app._pending_steps) == 1
        step_meta = app._pending_steps[0]
        assert step_meta['name'] == 'my_step'
        assert 'image_spec' in step_meta
        assert step_meta['image_spec']['base'] == 'blazing-executor-base:latest'
        assert 'pandas' in step_meta['image_spec']['pip_packages']

    def test_step_without_image_has_no_image_spec(self):
        """@app.step without image has no image_spec in metadata."""
        app = self._make_app()

        @app.step
        async def my_step(x: int, services=None):
            return x * 2

        step_meta = app._pending_steps[0]
        assert step_meta.get('image_spec') is None

    def test_step_image_must_use_executor_base(self):
        """@app.step image must be based on blazing-executor-base."""
        from blazing import Image
        app = self._make_app()

        image = Image.debian_slim()  # Wrong base!

        with pytest.raises(ValueError, match="blazing-executor-base"):
            @app.step(image=image)
            async def my_step(x: int, services=None):
                return x * 2

    def test_step_image_full_customization(self):
        """Image.executor() with full customization works with @app.step."""
        from blazing import Image
        app = self._make_app()

        image = (
            Image.executor()
            .apt_install("ffmpeg")
            .pip_install("opencv-python")
            .run_commands("mkdir -p /data")
            .env(DATA_DIR="/data")
        )

        @app.step(image=image)
        async def process(x: str, services=None):
            return x

        step_meta = app._pending_steps[0]
        spec = step_meta['image_spec']
        assert spec['base'] == 'blazing-executor-base:latest'
        assert 'ffmpeg' in spec['apt_packages']
        assert 'opencv-python' in spec['pip_packages']
        assert 'mkdir -p /data' in spec['commands']
        assert spec['env_vars']['DATA_DIR'] == '/data'
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_executor_image.py::TestStepImageParameter::test_step_accepts_image_parameter -v`
Expected: FAIL (TypeError — step() doesn't accept `image` parameter)

**Step 3: Write minimal implementation**

In `src/blazing/blazing.py`, modify the `step()` method signature (line 458) to accept `image`:

```python
    def step(
        self,
        step_func=None,
        *,
        step_type: str = None,
        sandboxed: bool = False,
        gpu: Union[str, "GPUConfig", None] = None,
        gpu_count: Optional[int] = None,
        gpu_memory: Optional[str] = None,
        image: Optional["Image"] = None,
    ):
```

Then, inside the `decorator(func)` function (after `gpu_config` parsing, around line 540), add image validation:

```python
            # Validate custom image if provided
            image_spec_dict = None
            if image is not None:
                from blazing.image import Image as ImageClass
                if not isinstance(image, ImageClass):
                    raise TypeError(
                        f"Expected Image, got {type(image).__name__}. "
                        "Use Image.executor() for custom executor images."
                    )
                if image.spec.base != "blazing-executor-base:latest":
                    raise ValueError(
                        f"Step image must be based on 'blazing-executor-base:latest', "
                        f"got '{image.spec.base}'. Use Image.executor() to create "
                        f"executor-compatible images."
                    )
                image_spec_dict = image.to_dict()
```

Then add `image_spec` to the `step_metadata` dict (around line 591, before `self._pending_steps.append(step_metadata)`):

```python
            # Add custom image spec if specified
            if image_spec_dict is not None:
                step_metadata['image_spec'] = image_spec_dict
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_executor_image.py::TestStepImageParameter -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/blazing/blazing.py tests/test_executor_image.py
git commit -m "feat: add image parameter to @app.step decorator"
```

---

### Task 3: Add `image` parameter to `@app.workflow` (and deprecated `@app.route`)

**Files:**
- Modify: `src/blazing/blazing.py:689-811` (route/workflow decorators)
- Test: `tests/test_executor_image.py`

**Step 1: Write the failing test**

Add to `tests/test_executor_image.py`:

```python
class TestWorkflowImageParameter:
    """Tests for image parameter on @app.workflow decorator."""

    def _make_app(self):
        """Create minimal Blazing instance for testing decorators."""
        from blazing import Blazing
        app = Blazing.__new__(Blazing)
        app._step_funcs = {}
        app._pending_steps = []
        app._pending_workflows = []
        app._workflow_funcs = {}
        app._code_validator = None
        return app

    def test_workflow_accepts_image_parameter(self):
        """@app.workflow(image=...) stores image spec in metadata."""
        from blazing import Image
        app = self._make_app()

        image = Image.executor().pip_install("pandas")

        @app.workflow(image=image)
        async def my_workflow(x: int, services=None):
            return x * 2

        assert len(app._pending_workflows) == 1
        wf_meta = app._pending_workflows[0]
        assert wf_meta['name'] == 'my_workflow'
        assert 'image_spec' in wf_meta
        assert wf_meta['image_spec']['base'] == 'blazing-executor-base:latest'

    def test_workflow_without_image_has_no_image_spec(self):
        """@app.workflow without image has no image_spec in metadata."""
        app = self._make_app()

        @app.workflow
        async def my_workflow(x: int, services=None):
            return x * 2

        wf_meta = app._pending_workflows[0]
        assert wf_meta.get('image_spec') is None

    def test_workflow_image_must_use_executor_base(self):
        """@app.workflow image must be based on blazing-executor-base."""
        from blazing import Image
        app = self._make_app()

        image = Image.debian_slim()  # Wrong base!

        with pytest.raises(ValueError, match="blazing-executor-base"):
            @app.workflow(image=image)
            async def my_workflow(x: int, services=None):
                return x * 2
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_executor_image.py::TestWorkflowImageParameter::test_workflow_accepts_image_parameter -v`
Expected: FAIL (TypeError — workflow()/route() doesn't accept `image` parameter)

**Step 3: Write minimal implementation**

In `src/blazing/blazing.py`, modify the `route()` method signature (line 689) to accept `image`:

```python
    def route(self, workflow_func=None, *, version_pins=None, schedule=None, image=None):
```

Then modify the `workflow()` method (line 1061) to pass through `image`:

```python
    def workflow(self, workflow_func=None, *, version_pins=None, schedule=None, image=None):
        ...
        return self.route(workflow_func, version_pins=version_pins, schedule=schedule, image=image)
```

Inside the `route()` decorator function (around line 707), add image validation before storing metadata:

```python
            # Validate custom image if provided
            image_spec_dict = None
            if image is not None:
                from blazing.image import Image as ImageClass
                if not isinstance(image, ImageClass):
                    raise TypeError(
                        f"Expected Image, got {type(image).__name__}. "
                        "Use Image.executor() for custom executor images."
                    )
                if image.spec.base != "blazing-executor-base:latest":
                    raise ValueError(
                        f"Workflow image must be based on 'blazing-executor-base:latest', "
                        f"got '{image.spec.base}'. Use Image.executor() to create "
                        f"executor-compatible images."
                    )
                image_spec_dict = image.to_dict()
```

Then in the `_pending_workflows.append(...)` dict (line 774), add:

```python
            self._pending_workflows.append({
                'name': func.__name__,
                'module': func.__module__,
                'qualname': func.__qualname__,
                'version_pins': version_pins,
                'schedules': schedules_data,
                'image_spec': image_spec_dict,  # NEW
            })
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_executor_image.py::TestWorkflowImageParameter -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/blazing/blazing.py tests/test_executor_image.py
git commit -m "feat: add image parameter to @app.workflow and @app.route decorators"
```

---

### Task 4: Include `image_spec` in registration models and sync payload

**Files:**
- Modify: `src/blazing_service/server.py:448-531` (registration models)
- Test: `tests/test_executor_image.py`

**Step 1: Write the failing test**

Add to `tests/test_executor_image.py`:

```python
class TestRegistrationModels:
    """Tests for image_spec in registration models."""

    def test_step_registration_accepts_image_spec(self):
        """StepRegistration model can hold image_spec."""
        from blazing_service.server import StepRegistration
        reg = StepRegistration(
            name="my_step",
            module="__main__",
            qualname="my_step",
            image_spec={
                "base": "blazing-executor-base:latest",
                "pip_packages": ["pandas"],
                "apt_packages": ["ffmpeg"],
                "commands": [],
                "files": [],
                "env_vars": {},
                "workdir": "/app",
                "python_version": "3.11",
            }
        )
        assert reg.image_spec is not None
        assert reg.image_spec["base"] == "blazing-executor-base:latest"

    def test_step_registration_image_spec_optional(self):
        """StepRegistration image_spec is optional (None by default)."""
        from blazing_service.server import StepRegistration
        reg = StepRegistration(name="s", module="m", qualname="q")
        assert reg.image_spec is None

    def test_workflow_registration_accepts_image_spec(self):
        """WorkflowRegistration model can hold image_spec."""
        from blazing_service.server import WorkflowRegistration
        reg = WorkflowRegistration(
            name="my_wf",
            module="__main__",
            qualname="my_wf",
            image_spec={
                "base": "blazing-executor-base:latest",
                "pip_packages": ["torch"],
                "apt_packages": [],
                "commands": ["mkdir /models"],
                "files": [],
                "env_vars": {"MODEL": "/models"},
                "workdir": "/app",
                "python_version": "3.11",
            }
        )
        assert reg.image_spec is not None
        assert reg.image_spec["env_vars"]["MODEL"] == "/models"

    def test_workflow_registration_image_spec_optional(self):
        """WorkflowRegistration image_spec is optional (None by default)."""
        from blazing_service.server import WorkflowRegistration
        reg = WorkflowRegistration(name="w", module="m", qualname="q")
        assert reg.image_spec is None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_executor_image.py::TestRegistrationModels::test_step_registration_accepts_image_spec -v`
Expected: FAIL (ValidationError — unexpected field `image_spec`)

**Step 3: Write minimal implementation**

In `src/blazing_service/server.py`, add `image_spec` field to `StepRegistration` (after line 467):

```python
    # Custom executor image specification (full Image customization)
    image_spec: Optional[Dict[str, Any]] = None
```

And to `WorkflowRegistration` (after line 487):

```python
    # Custom executor image specification (full Image customization)
    image_spec: Optional[Dict[str, Any]] = None
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_executor_image.py::TestRegistrationModels -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/blazing_service/server.py tests/test_executor_image.py
git commit -m "feat: add image_spec field to StepRegistration and WorkflowRegistration models"
```

---

## Phase B: Custom Executor Image Builds

### Task 5: Build per-step/workflow custom images during `publish()`

**Files:**
- Modify: `src/blazing/blazing.py:1171-1249` (add _collect_unique_image_specs)
- Modify: `src/blazing/blazing.py:1714-1792` (publish method)
- Test: `tests/test_executor_image.py`

**Step 1: Write the failing test**

Add to `tests/test_executor_image.py`:

```python
class TestPublishWithImages:
    """Tests for building custom images during publish()."""

    def _make_app(self):
        from blazing import Blazing
        app = Blazing.__new__(Blazing)
        app._step_funcs = {}
        app._pending_steps = []
        app._pending_workflows = []
        app._workflow_funcs = {}
        app._code_validator = None
        return app

    def test_collect_unique_images_deduplicates(self):
        """_collect_unique_image_specs deduplicates by content hash."""
        from blazing import Blazing, Image
        app = self._make_app()

        image_a = Image.executor().pip_install("pandas")
        image_b = Image.executor().pip_install("torch")

        @app.step(image=image_a)
        async def step_a(x, services=None):
            return x

        @app.step(image=image_b)
        async def step_b(x, services=None):
            return x

        # Same image as step_a — should deduplicate
        @app.step(image=image_a)
        async def step_c(x, services=None):
            return x

        unique_images = Blazing._collect_unique_image_specs(
            app._pending_steps + app._pending_workflows
        )
        assert len(unique_images) == 2  # image_a and image_b (deduped)

    def test_collect_unique_images_empty_when_no_images(self):
        """_collect_unique_image_specs returns empty when no images specified."""
        from blazing import Blazing
        unique = Blazing._collect_unique_image_specs([
            {'name': 'step1'},
            {'name': 'step2'},
        ])
        assert len(unique) == 0
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_executor_image.py::TestPublishWithImages::test_collect_unique_images_deduplicates -v`
Expected: FAIL (AttributeError — Blazing has no `_collect_unique_image_specs`)

**Step 3: Write minimal implementation**

Add a static method to the `Blazing` class in `src/blazing/blazing.py` (after `_build_and_register_executor_image`, around line 1249):

```python
    @staticmethod
    def _collect_unique_image_specs(registrations: list) -> dict:
        """Collect unique image specs from step/workflow registrations.

        Deduplicates by content hash so the same image is only built once.

        Args:
            registrations: List of step/workflow metadata dicts

        Returns:
            Dict mapping content_hash -> image_spec dict
        """
        from blazing.image import ImageSpec
        unique = {}
        for reg in registrations:
            spec_dict = reg.get('image_spec')
            if spec_dict is not None:
                spec = ImageSpec.from_dict(spec_dict)
                h = spec.content_hash()
                if h not in unique:
                    unique[h] = spec_dict
        return unique
```

Then, in the `publish()` method, after the existing executor image build block (after line 1719), add logic to build per-step/workflow custom images:

```python
        # Build custom images for steps/workflows that specify image_spec
        all_registrations = self._pending_steps + self._pending_workflows
        unique_image_specs = self._collect_unique_image_specs(all_registrations)
        step_image_builds = {}  # content_hash -> build result

        if unique_image_specs:
            from blazing.image import ImageSpec
            print(f"🔨 BUILD-STEP-IMAGES: Building {len(unique_image_specs)} custom step/workflow images...", flush=True)

            for content_hash, spec_dict in unique_image_specs.items():
                spec = ImageSpec.from_dict(spec_dict)
                dockerfile_content = spec.to_dockerfile()

                app_id = self._extract_app_id_from_token()
                customer_id = self._extract_customer_id_from_token()
                image_name = f"step-executor-{customer_id}-{content_hash}" if customer_id else f"step-executor-{app_id}-{content_hash}"
                image_tag = content_hash

                print(f"  Building {image_name}:{image_tag}...", flush=True)

                if self._local_stack:
                    build_result = await self._local_stack.build_and_push_executor(
                        dockerfile_content=dockerfile_content,
                        name=image_name,
                        tag=image_tag,
                        token=self._api_token,
                    )
                    registry_url = build_result.get('registry_url', f"local://{image_name}:{image_tag}")
                else:
                    build_result = await self._backend.build_executor_image(
                        dockerfile_content=dockerfile_content,
                        image_name=image_name,
                        image_tag=image_tag,
                        executor_spec=spec_dict,
                    )
                    registry_url = build_result.get('registry_url')

                step_image_builds[content_hash] = {
                    'name': image_name,
                    'tag': image_tag,
                    'registry_url': registry_url,
                    'content_hash': content_hash,
                }
                print(f"  ✓ Built {image_name}:{image_tag}", flush=True)

            print(f"✓ BUILD-STEP-IMAGES: {len(step_image_builds)} images built", flush=True)

        # Attach image build references to steps/workflows for registry payload
        if step_image_builds:
            from blazing.image import ImageSpec
            for reg in all_registrations:
                spec_dict = reg.get('image_spec')
                if spec_dict is not None:
                    spec = ImageSpec.from_dict(spec_dict)
                    h = spec.content_hash()
                    if h in step_image_builds:
                        reg['image_build'] = step_image_builds[h]
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_executor_image.py::TestPublishWithImages -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/blazing/blazing.py tests/test_executor_image.py
git commit -m "feat: build per-step/workflow custom executor images during publish()"
```

---

## Phase C: Image-Aware Executor Routing

### Task 6: Add `image_tag` to `ExecutorInstance` and image-aware `get_executor`

**Files:**
- Modify: `src/blazing_service/engine/executor_registry.py:55-68` (ExecutorInstance dataclass)
- Modify: `src/blazing_service/engine/executor_registry.py:107-270` (ExecutorRegistry class)
- Test: `tests/test_executor_image.py`

**Step 1: Write the failing test**

Add to `tests/test_executor_image.py`:

```python
class TestImageAwareExecutorRegistry:
    """Tests for image-aware executor selection in ExecutorRegistry."""

    def test_register_executor_with_image_tag(self):
        """Can register executor with an image_tag."""
        from blazing_service.engine.executor_registry import (
            ExecutorRegistry, ExecutorType,
        )
        registry = ExecutorRegistry()
        instance = registry.register_executor(
            "exec-1", "http://exec-1:8000", ExecutorType.TRUSTED,
            image_tag="abc123def456",
        )
        assert instance.image_tag == "abc123def456"

    def test_register_executor_default_image_tag(self):
        """Executor without image_tag gets None."""
        from blazing_service.engine.executor_registry import (
            ExecutorRegistry, ExecutorType,
        )
        registry = ExecutorRegistry()
        instance = registry.register_executor(
            "exec-1", "http://exec-1:8000", ExecutorType.TRUSTED,
        )
        assert instance.image_tag is None

    def test_get_executor_by_image_tag(self):
        """get_executor with image_tag returns matching executor."""
        from blazing_service.engine.executor_registry import (
            ExecutorRegistry, ExecutorType,
        )
        registry = ExecutorRegistry()
        registry.register_executor(
            "exec-default", "http://default:8000", ExecutorType.TRUSTED,
        )
        registry.register_executor(
            "exec-custom", "http://custom:8000", ExecutorType.TRUSTED,
            image_tag="abc123",
        )

        result = registry.get_executor(ExecutorType.TRUSTED, image_tag="abc123")
        assert result is not None
        assert result.executor_id == "exec-custom"
        assert result.image_tag == "abc123"

    def test_get_executor_no_image_tag_returns_default(self):
        """get_executor without image_tag returns executor without image_tag."""
        from blazing_service.engine.executor_registry import (
            ExecutorRegistry, ExecutorType,
        )
        registry = ExecutorRegistry()
        registry.register_executor(
            "exec-default", "http://default:8000", ExecutorType.TRUSTED,
        )
        registry.register_executor(
            "exec-custom", "http://custom:8000", ExecutorType.TRUSTED,
            image_tag="abc123",
        )

        result = registry.get_executor(ExecutorType.TRUSTED)
        assert result is not None
        assert result.image_tag is None  # Returns default executor

    def test_get_executor_image_tag_not_found(self):
        """get_executor with unknown image_tag returns None."""
        from blazing_service.engine.executor_registry import (
            ExecutorRegistry, ExecutorType,
        )
        registry = ExecutorRegistry()
        registry.register_executor(
            "exec-default", "http://default:8000", ExecutorType.TRUSTED,
        )

        result = registry.get_executor(ExecutorType.TRUSTED, image_tag="nonexistent")
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_executor_image.py::TestImageAwareExecutorRegistry::test_register_executor_with_image_tag -v`
Expected: FAIL (TypeError — `register_executor()` got unexpected keyword argument `image_tag`)

**Step 3: Write minimal implementation**

In `src/blazing_service/engine/executor_registry.py`:

Add `image_tag` to `ExecutorInstance` (after line 60, before `is_healthy`):

```python
    image_tag: Optional[str] = None      # Custom image tag (None = default base image)
```

Modify `register_executor` (line 156) to accept `image_tag`:

```python
    def register_executor(
        self,
        executor_id: str,
        url: str,
        executor_type: ExecutorType,
        image_tag: Optional[str] = None,
    ) -> ExecutorInstance:
```

And pass it through in the `ExecutorInstance(...)` constructor (line 179):

```python
        instance = ExecutorInstance(
            executor_id=executor_id,
            url=url,
            executor_type=executor_type,
            image_tag=image_tag,
        )
```

Modify `get_executor` (line 213) to accept `image_tag`:

```python
    def get_executor(
        self,
        executor_type: ExecutorType,
        require_healthy: bool = True,
        image_tag: Optional[str] = None,
    ) -> Optional[ExecutorInstance]:
```

Add image_tag filtering after healthy filtering (around line 246, after `healthy_ids` is computed):

```python
        # Filter by image_tag
        if image_tag is not None:
            healthy_ids = [
                eid for eid in healthy_ids
                if self._executors[eid].image_tag == image_tag
            ]
        else:
            # No image_tag requested — only return executors without custom images
            healthy_ids = [
                eid for eid in healthy_ids
                if self._executors[eid].image_tag is None
            ]
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_executor_image.py::TestImageAwareExecutorRegistry -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/blazing_service/engine/executor_registry.py tests/test_executor_image.py
git commit -m "feat: add image-aware executor selection to ExecutorRegistry"
```

---

## Phase D: Deprecate ExecutorImage

### Task 7: Deprecate `ExecutorImage`, `ExecutorImageSpec`, `ExecutorImages`, `set_executor_image()`

**Files:**
- Modify: `src/blazing/image.py:605-889` (ExecutorImage classes)
- Modify: `src/blazing/blazing.py:400-456` (set_executor_image method)
- Test: `tests/test_executor_image.py`

**Step 1: Write the failing test**

Add to `tests/test_executor_image.py`:

```python
class TestExecutorImageDeprecation:
    """Tests that ExecutorImage classes emit deprecation warnings."""

    def test_executor_image_init_warns(self):
        """ExecutorImage() emits DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="Image.executor()"):
            ExecutorImage()

    def test_executor_image_spec_init_warns(self):
        """ExecutorImageSpec() emits DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="Image.executor()"):
            ExecutorImageSpec()

    def test_executor_images_factory_warns(self):
        """ExecutorImages.default() emits DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="Image.executor()"):
            ExecutorImages.default()

    def test_set_executor_image_warns(self):
        """app.set_executor_image() emits DeprecationWarning."""
        import warnings
        from blazing import Blazing

        app = Blazing.__new__(Blazing)
        app._executor_image = None

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Still need to pass the type check — create with warning suppressed
            with pytest.warns(DeprecationWarning):
                img = ExecutorImage()
            app.set_executor_image(img)

        # Check set_executor_image also warned
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert any("Image.executor()" in str(x.message) for x in dep_warnings)
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_executor_image.py::TestExecutorImageDeprecation::test_executor_image_init_warns -v`
Expected: FAIL (no DeprecationWarning emitted)

**Step 3: Write minimal implementation**

In `src/blazing/image.py`, add deprecation warnings to `ExecutorImageSpec.__post_init__` and `ExecutorImage.__init__`:

Add `__post_init__` to `ExecutorImageSpec` (after line 624):

```python
    def __post_init__(self):
        import warnings
        warnings.warn(
            "ExecutorImageSpec is deprecated. Use Image.executor() instead, "
            "which provides full customization (apt, pip, run_commands, etc.). "
            "ExecutorImageSpec will be removed in v3.0.",
            DeprecationWarning,
            stacklevel=2,
        )
```

Modify `ExecutorImage.__init__` (line 699) to emit warning:

```python
    def __init__(self, spec: Optional[ExecutorImageSpec] = None):
        import warnings
        warnings.warn(
            "ExecutorImage is deprecated. Use Image.executor() instead, "
            "which provides full customization (apt, pip, run_commands, etc.). "
            "ExecutorImage will be removed in v3.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._spec = spec or ExecutorImageSpec()
```

Add deprecation to each `ExecutorImages` static method (e.g., `default()` at line 814):

```python
    @staticmethod
    def default() -> ExecutorImage:
        """Default executor with no additional packages.

        .. deprecated:: 2.5
            Use Image.executor() instead.
        """
        import warnings
        warnings.warn(
            "ExecutorImages is deprecated. Use Image.executor() instead. "
            "ExecutorImages will be removed in v3.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return ExecutorImage()
```

(Repeat for all ExecutorImages static methods: data_science, ml, ml_gpu, nlp, web_scraping)

In `src/blazing/blazing.py`, add deprecation to `set_executor_image` (line 400):

```python
    def set_executor_image(self, image: "ExecutorImage") -> "Blazing":
        """Set a custom executor image for this app.

        .. deprecated:: 2.5
            Use @app.step(image=Image.executor().pip_install(...)) instead.
        """
        import warnings
        warnings.warn(
            "set_executor_image() is deprecated. Use Image.executor() with "
            "@app.step(image=...) or @app.workflow(image=...) instead. "
            "set_executor_image() will be removed in v3.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        ...  # rest of method unchanged
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_executor_image.py::TestExecutorImageDeprecation -v`
Expected: All PASS

Note: Existing `TestExecutorImage*` tests will now emit warnings. Add `@pytest.mark.filterwarnings("ignore::DeprecationWarning")` to existing test classes that create `ExecutorImage`/`ExecutorImageSpec` instances to keep them clean:
- `TestExecutorImageSpec`
- `TestExecutorImage`
- `TestExecutorImages`
- `TestExecutorImageSecurity`
- `TestExecutorImageEdgeCases`

**Step 5: Commit**

```bash
git add src/blazing/image.py src/blazing/blazing.py tests/test_executor_image.py
git commit -m "deprecate: mark ExecutorImage, ExecutorImageSpec, ExecutorImages, set_executor_image() as deprecated in favor of Image.executor()"
```

---

### Task 8: Run full test suite to verify no regressions

**Step 1: Run all image tests**

Run: `python -m pytest tests/test_executor_image.py -v`
Expected: All PASS

**Step 2: Run executor-related tests**

Run: `python -m pytest tests/ -k "executor" -v`
Expected: All PASS

**Step 3: Run full unit test suite**

Run: `python -m pytest tests/ -v --ignore=tests/test_z_all_frameworks_real_http_e2e.py --ignore=tests/test_z_orchestrator_endpoints_e2e.py -x`
Expected: All PASS

**Step 4: Commit (if any fixups needed)**

Only commit if fixes were needed — otherwise skip.

---

## Summary of Changes

| File | Change |
|------|--------|
| `src/blazing/image.py` | Add `Image.executor()` factory; deprecate `ExecutorImage`, `ExecutorImageSpec`, `ExecutorImages` |
| `src/blazing/blazing.py` | Add `image` param to `step()`, `route()`, `workflow()`; add `_collect_unique_image_specs()`; build step images in `publish()`; deprecate `set_executor_image()` |
| `src/blazing_service/server.py` | Add `image_spec: Optional[Dict]` to `StepRegistration` and `WorkflowRegistration` |
| `src/blazing_service/engine/executor_registry.py` | Add `image_tag` to `ExecutorInstance`; add `image_tag` filtering to `get_executor()` and `register_executor()` |
| `tests/test_executor_image.py` | New test classes for all features + deprecation warnings |
