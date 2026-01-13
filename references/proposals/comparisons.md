# Comparing Blazing with Other Orchestration Frameworks

This brief positions Blazing against Modal, Celery, and Dask so you can articulate when to choose each platform. It focuses on architectural differences, workload fit, and operational trade-offs.

---

## Summary Table

| Dimension | **Blazing** | **Modal** | **Celery** | **Dask** |
|-----------|-------------|-----------|------------|----------|
| Deployment model | Self-hosted, Redis-backed control plane | Managed serverless platform | Self-managed workers + broker | Self-managed distributed scheduler |
| Worker lifetime | Long-lived workers with stateful connectors | Ephemeral containers (minutes–hours) | Long-lived processes | Long-lived processes |
| Workload sweet spot | Mixed async/blocking pipelines with state | Stateless tasks, bursty workloads | High-volume stateless jobs | Dataframe/array processing, analytics |
| State persistence | Redis/KeyDB + Arrow Flight | Externalise manually (S3, DB) | Optional result backend | Distributed memory structures |
| Optimisation | Automatic worker mix (async vs blocking) | Managed scaling, fixed profiles | Manual tuning (concurrency, prefetch) | Task graph optimisation |
| Monitoring | CLI/terminal tools (`btop`, charts, logs) | Modal Dashboard | Flower, Prometheus integrations | Dask Dashboard |

---

## Blazing vs Modal

### When Blazing Wins
- Need persistent workers that retain DB pools, SSH tunnels, or ML models across tasks.
- Require fine-grained control over how async and blocking tasks interleave.
- Prefer self-hosting for compliance or network locality reasons.

### When Modal Wins
- Want fully managed infrastructure with true pay-per-use economics.
- Workloads are stateless and tolerate container cold starts.
- Need tight integration with Modal’s workflow DAG tooling and storage integrations.

### Talking Points
- Blazing’s Redis-backed metadata and Arrow Flight transport eliminate repeated serialisation and connection churn.
- Modal excels at simple fan-out/fan-in serverless jobs; stateful pipelines still require external stores that you must manage.

---

## Blazing vs Celery

### When Blazing Wins
- Workflows mix long-running CPU work with high-throughput async operations.
- Need built-in checkpointing, partial reruns, or dynamic branching.
- Want the platform to auto-tune worker roles instead of hand-tuning concurrency.

### When Celery Wins
- You already operate Celery within a Django/Flask ecosystem and value its mature plugin ecosystem.
- Tasks are small, stateless, and latency sensitive—Celery’s lower overhead shines here.
- Broker semantics (prefetch, acks, retries) match your requirements out of the box.

### Talking Points
- Celery’s concurrency and worker allocation are static; Blazing’s hybrid worker mix automatically shifts capacity as queue pressure changes.
- Blazing’s service concept keeps reusable logic warm inside workers, reducing cold start penalties for resource-heavy code.

---

## Blazing vs Dask

### When Blazing Wins
- You need a workflow engine rather than a dataframe/array processing library.
- Tasks depend on external systems (databases, APIs) and must orchestrate side effects.
- Mixed async/blocking execution and long-lived resource pools are critical.

### When Dask Wins
- Workloads revolve around pandas/NumPy/SciPy operations across large datasets.
- You want to scale Python analytics code with minimal changes.
- Interactive dashboards (Jupyter, Dask Distributed) and dataframe APIs are primary requirements.

### Talking Points
- Dask provides an in-memory scheduler optimised for task graphs with shared data sets.
- Blazing focuses on durable orchestration, incremental checkpointing, and integration with heterogeneous services.

---

## Choosing the Right Tool

| Scenario | Recommended Framework |
|----------|----------------------|
| Financial or ETL pipelines with staged enrichment, backtesting, and reporting | **Blazing** |
| Sending transactional emails, processing small background jobs | **Celery** |
| Large-scale dataframe analytics or ML feature engineering | **Dask** |
| Burst workloads that must scale to zero between runs | **Modal** |

If you need to migrate from an existing framework, evaluate:

- **State requirements**: Do you rely on warm connectors, caches, or local state?
- **Latency vs throughput**: Celery may outpace Blazing for microtasks; Blazing overtakes Celery on heavier workloads that benefit from mix optimisation.
- **Operational ownership**: Modal removes infrastructure management at the cost of customisability; Blazing and Celery require more ops investment but offer flexibility.
- **Programming model**: Dask’s dataframe APIs differ significantly from Blazing’s route/station abstraction.

---

## Additional Resources

- [Architecture Overview](architecture.md)
- [Benchmarking Guide](benchmarking.md)
- [Worker Mix Optimiser](worker-mix-optimizer.md)
- [Testing Guide](testing.md)

For customer-facing collateral (slide decks, ROI calculators, migration checklists), contact the product marketing team.

