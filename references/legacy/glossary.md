# Glossary

This document defines common terms used in the Blazing framework.

### C

See **Concurrency**.

### Concurrency

The number of coroutines that an **Async Worker** can execute concurrently. Represented as `C` in the worker mix.

### BTOP (Blazing Top)

The web-based monitoring dashboard for Blazing. BTOP provides real-time visibility into worker statistics, queue depths, throughput, and system health by querying the `/v1/stats` API.

### Connector

A configuration object that stores details for connecting to external systems, such as database DSNs, API credentials, or SSH tunnels. Connectors are stored in Redis and can be requested by **Services** and **Workflows**.

### Coordinator

A process that runs on each machine in the Blazing cluster. The Coordinator is responsible for managing **Worker Processes**, collecting telemetry, and applying worker mix optimization decisions based on queue metrics and execution timing.

### Run

A single, end-to-end execution of a **Workflow**. A run tracks the initial arguments, the status of all its **Step Runs**, and the final result of the pipeline.

### Service

A class, decorated with `@app.service`, that bundles reusable logic and long-lived resources (like database connections). Services are instantiated once per **Worker Process** and can be accessed by **Steps**.

### Step

A function (sync or async), decorated with `@app.step`, that represents a single processing unit in a pipeline. Each step has its own queue and is executed by a **Worker**.

### Step Run

A single invocation of a **Step** as part of a **Run**. **Workers** dequeue step runs, execute them, and record the results.

### Worker

A process that executes the work of a **Step**. There are two types of workers:

-   **Async Worker**: Runs an event loop and can execute multiple I/O-bound tasks concurrently.
-   **Blocking Worker**: Executes one CPU-bound or long-running task at a time.

### Workflow

An `async` function, decorated with `@app.workflow`, that defines the overall logic of a pipeline. A workflow orchestrates calls to one or more **Steps**.

---

## Legacy Terms (Deprecated)

The following terms are deprecated as of v2.0 and will be removed in v3.0:

- **Route** → Use **Workflow** instead
- **Station** → Use **Step** instead
- **Service** → Use **Service** instead
- **Unit** → Use **Run** instead
- **Operation** → Use **Step Run** instead
