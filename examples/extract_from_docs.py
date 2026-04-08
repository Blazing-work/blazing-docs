"""
Extract examples from blazing-docs MDX files and generate executable Python files.
"""

import os
import re

# Documentation source files
CORE_DOCS = "/Users/jonathanborduas/code/blazing-docs/blazing-flow/core-examples.mdx"
ENDPOINTS_DOCS = (
    "/Users/jonathanborduas/code/blazing-docs/blazing-flow/endpoints/examples.mdx"
)
SANDBOX_DOCS = (
    "/Users/jonathanborduas/code/blazing-docs/blazing-flow-sandbox/examples.mdx"
)

# Output directory
OUTPUT_DIR = "/Users/jonathanborduas/code/blazing-examples"


def extract_code_by_heading(mdx_file, heading_text):
    """Extract code block following a specific heading from MDX file."""
    with open(mdx_file) as f:
        content = f.read()

    # Pattern to match: ## Heading\n...```python\nCODE\n```
    # Escape special regex characters in heading
    escaped_heading = re.escape(heading_text)
    pattern = rf"## {escaped_heading}\s*\n.*?```python\n(.*?)\n```"
    match = re.search(pattern, content, re.DOTALL)

    if match:
        return match.group(1).strip()
    return None


def extract_code_from_mdx(mdx_file, example_num):
    """Extract code block for a specific example number from MDX file."""
    with open(mdx_file) as f:
        content = f.read()

    # Pattern to match: ### NUMBER. Title\n```python\nCODE\n```
    pattern = rf"### {example_num}\..*?\n```python\n(.*?)\n```"
    match = re.search(pattern, content, re.DOTALL)

    if match:
        return match.group(1).strip()
    return None


def create_example_file(example_metadata):
    """Create a Python example file with docstring and code."""

    # Extract code from docs
    if "heading" in example_metadata:
        code = extract_code_by_heading(
            example_metadata["source"], example_metadata["heading"]
        )
    else:
        code = extract_code_from_mdx(
            example_metadata["source"], example_metadata["example_num"]
        )

    if not code:
        print(f"⚠ Could not extract code for: {example_metadata['title']}")
        return

    # Build docstring
    learn_points = "\n".join([f"- {point}" for point in example_metadata["learn"]])

    docstring = f'''"""
# {example_metadata["title"]}

{example_metadata["description"]}

## Metadata
- **Product**: {example_metadata["product"].replace("blazing-flow", "Blazing Flow").replace("blazing-core", "Blazing Core").replace("blazing-endpoints", "Blazing Flow Endpoints").replace("blazing-sandbox", "Blazing Flow Sandbox")}
- **Difficulty**: {example_metadata["difficulty"]}
- **Time**: {example_metadata["time"]}
- **Tags**: {example_metadata["tags"]}

## Description

{example_metadata["description"]}

## What you'll learn

{learn_points}
"""

'''

    # Add necessary imports if not present
    full_code = docstring + code

    # Wrap top-level await statements in async main() if needed
    if "await app.publish()" in code and "async def main()" not in code:
        # Replace top-level awaits with wrapped version
        code_lines = code.split("\n")
        imports = []
        body_lines = []

        for line in code_lines:
            if line.strip().startswith(("from ", "import ")):
                imports.append(line)
            else:
                body_lines.append(line)

        # Build wrapped code
        full_code = docstring
        full_code += "\n".join(imports) + "\n\n"
        full_code += "async def main():\n"

        for line in body_lines:
            if line.strip():  # Skip empty lines initially
                full_code += "    " + line + "\n"
            elif body_lines.index(line) > 0:  # Keep empty lines but not at start
                full_code += "\n"

        full_code += '\n\nif __name__ == "__main__":\n    import asyncio\n    asyncio.run(main())\n'
    else:
        full_code = docstring + code
        # Add main block if not present
        if '__name__ == "__main__"' not in full_code and "async def" in full_code:
            full_code += '\n\nif __name__ == "__main__":\n    import asyncio\n    asyncio.run(main())\n'

    # Ensure category directory exists
    category_dir = os.path.join(OUTPUT_DIR, example_metadata["category"])
    os.makedirs(category_dir, exist_ok=True)

    # Write file
    filepath = os.path.join(category_dir, example_metadata["file"])
    with open(filepath, "w") as f:
        f.write(full_code)

    print(f"✓ Created: {example_metadata['category']}/{example_metadata['file']}")


# ========================================
# ALL EXAMPLES METADATA
# ========================================

EXAMPLES = [
    # ===== 01_getting_started (Core examples 1-6) =====
    {
        "file": "simple_step.py",
        "category": "01_getting_started",
        "source": CORE_DOCS,
        "example_num": 1,
        "title": "Simple Step",
        "description": "The simplest possible Blazing Flow example - a single processing step.",
        "difficulty": "Beginner",
        "time": "5 min",
        "tags": "step, basics, quickstart",
        "product": "blazing-flow",
        "learn": [
            "How to create a Blazing app",
            "How to define a step with @app.step",
            "How to publish steps to the execution engine",
        ],
    },
    {
        "file": "step_with_math.py",
        "category": "01_getting_started",
        "source": CORE_DOCS,
        "example_num": 2,
        "title": "Step with Math",
        "description": "Basic arithmetic operations in a distributed step.",
        "difficulty": "Beginner",
        "time": "5 min",
        "tags": "step, math, basics",
        "product": "blazing-flow",
        "learn": [
            "How to pass parameters to steps",
            "How to return values from steps",
            "Basic type annotations for step parameters",
        ],
    },
    {
        "file": "data_processing_step.py",
        "category": "01_getting_started",
        "source": CORE_DOCS,
        "example_num": 3,
        "title": "Data Processing Step",
        "description": "Filter and transform data in a single step.",
        "difficulty": "Beginner",
        "time": "5 min",
        "tags": "step, data, filtering",
        "product": "blazing-flow",
        "learn": [
            "How to work with lists in steps",
            "How to use list comprehensions for data filtering",
            "Basic data transformation patterns",
        ],
    },
    {
        "file": "basic_workflow.py",
        "category": "01_getting_started",
        "source": CORE_DOCS,
        "example_num": 4,
        "title": "Basic Workflow",
        "description": "Multi-step orchestration - the foundation of distributed workflows.",
        "difficulty": "Beginner",
        "time": "10 min",
        "tags": "workflow, orchestration, multi-step",
        "product": "blazing-flow",
        "learn": [
            "How to define workflows with @app.workflow",
            "How to chain multiple steps together",
            "How workflows pass data between steps",
        ],
    },
    {
        "file": "data_transformation_workflow.py",
        "category": "01_getting_started",
        "source": CORE_DOCS,
        "example_num": 5,
        "title": "Data Transformation Workflow",
        "description": "Multi-stage data pipeline with cleaning and normalization.",
        "difficulty": "Beginner",
        "time": "10 min",
        "tags": "workflow, data, transformation, pipeline",
        "product": "blazing-flow",
        "learn": [
            "How to build data processing pipelines",
            "How to handle data cleaning steps",
            "Data normalization techniques",
        ],
    },
    {
        "file": "multi_branch_workflow.py",
        "category": "01_getting_started",
        "source": CORE_DOCS,
        "example_num": 6,
        "title": "Multi-Branch Workflow",
        "description": "Parallel execution with asyncio.gather for concurrent processing.",
        "difficulty": "Intermediate",
        "time": "15 min",
        "tags": "workflow, parallel, asyncio, branching",
        "product": "blazing-flow",
        "learn": [
            "How to run steps in parallel with asyncio.gather",
            "How to combine results from parallel branches",
            "When to use parallel vs sequential execution",
        ],
    },
    # ===== 02_web_endpoints (Endpoints examples) =====
    {
        "file": "basic_calculator_api.py",
        "category": "02_web_endpoints",
        "source": ENDPOINTS_DOCS,
        "heading": "Basic Calculator API",
        "title": "Basic Calculator API",
        "description": "The simplest possible endpoint: expose a workflow as a public HTTP API.",
        "difficulty": "Beginner",
        "time": "10 min",
        "tags": "endpoint, api, rest, basic",
        "product": "blazing-endpoints",
        "learn": [
            "How to expose workflows as HTTP endpoints",
            "How to use @app.endpoint decorator",
            "How to create and run a FastAPI app with Blazing",
        ],
    },
    {
        "file": "multi_step_pipeline_api.py",
        "category": "02_web_endpoints",
        "source": ENDPOINTS_DOCS,
        "heading": "Multi-Step Data Pipeline",
        "title": "Multi-Step Data Pipeline API",
        "description": "Expose a multi-step workflow that processes data through several stages.",
        "difficulty": "Intermediate",
        "time": "15 min",
        "tags": "endpoint, pipeline, multi-step, statistics",
        "product": "blazing-endpoints",
        "learn": [
            "How to expose multi-step workflows as endpoints",
            "How to organize internal steps vs public endpoints",
            "Data validation and transformation via REST API",
        ],
    },
    {
        "file": "authenticated_api.py",
        "category": "02_web_endpoints",
        "source": ENDPOINTS_DOCS,
        "heading": "API with Authentication",
        "title": "API with Authentication",
        "description": "Protect endpoints with custom authentication (JWT, API keys, OAuth).",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "endpoint, authentication, jwt, api-key, security",
        "product": "blazing-endpoints",
        "learn": [
            "How to add authentication to endpoints",
            "How to implement JWT verification",
            "How to implement API key authentication",
        ],
    },
    {
        "file": "websocket_realtime.py",
        "category": "02_web_endpoints",
        "source": ENDPOINTS_DOCS,
        "heading": "WebSocket Real-Time Updates",
        "title": "WebSocket Real-Time Updates",
        "description": "Enable WebSocket for real-time progress updates from long-running workflows.",
        "difficulty": "Advanced",
        "time": "25 min",
        "tags": "endpoint, websocket, real-time, streaming",
        "product": "blazing-endpoints",
        "learn": [
            "How to enable WebSocket on endpoints",
            "How to receive real-time progress updates",
            "WebSocket client implementation patterns",
        ],
    },
    {
        "file": "batch_processing_api.py",
        "category": "02_web_endpoints",
        "source": ENDPOINTS_DOCS,
        "heading": "Batch Processing API",
        "title": "Batch Processing API",
        "description": "Process multiple items concurrently with result aggregation.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "endpoint, batch, concurrent, aggregation",
        "product": "blazing-endpoints",
        "learn": [
            "How to process batches via REST API",
            "Concurrent processing patterns",
            "Result aggregation strategies",
        ],
    },
    {
        "file": "error_handling_api.py",
        "category": "02_web_endpoints",
        "source": ENDPOINTS_DOCS,
        "heading": "Error Handling",
        "title": "Error Handling in APIs",
        "description": "Proper error handling with custom error responses.",
        "difficulty": "Intermediate",
        "time": "15 min",
        "tags": "endpoint, error-handling, validation",
        "product": "blazing-endpoints",
        "learn": [
            "How to handle errors in endpoints",
            "Input validation patterns",
            "Error response formatting",
        ],
    },
    {
        "file": "multiple_endpoints.py",
        "category": "02_web_endpoints",
        "source": ENDPOINTS_DOCS,
        "heading": "Multiple Endpoints with Different Paths",
        "title": "Multiple Endpoints with Different Paths",
        "description": "Organize multiple endpoints with different paths and versions.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "endpoint, versioning, api-design, organization",
        "product": "blazing-endpoints",
        "learn": [
            "How to organize multiple endpoints",
            "API versioning patterns (v1, v2)",
            "Path organization strategies",
        ],
    },
    {
        "file": "production_deployment.py",
        "category": "02_web_endpoints",
        "source": ENDPOINTS_DOCS,
        "heading": "Production Deployment Example",
        "title": "Production Deployment",
        "description": "Complete production setup with Docker, Kubernetes, and monitoring.",
        "difficulty": "Expert",
        "time": "40 min",
        "tags": "endpoint, deployment, docker, production",
        "product": "blazing-endpoints",
        "learn": [
            "How to deploy endpoints with Docker",
            "Production environment configuration",
            "Multi-service orchestration",
        ],
    },
    # ===== 03_data_processing (Error handling 14-16, Aggregation 17-18, ETL 19-20, Files 25-26) =====
    {
        "file": "retry_logic.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 14,
        "title": "Retry Logic with Exponential Backoff",
        "description": "Handle transient failures with automatic retry and exponential backoff.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "error-handling, retry, backoff, resilience",
        "product": "blazing-flow",
        "learn": [
            "Retry patterns for unreliable operations",
            "Exponential backoff implementation",
            "Error recovery strategies",
        ],
    },
    {
        "file": "validation_error_handling.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 15,
        "title": "Validation & Error Handling",
        "description": "Validate input data and handle errors gracefully in workflows.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "validation, error-handling, data-quality",
        "product": "blazing-flow",
        "learn": [
            "Input validation patterns",
            "Graceful error handling in workflows",
            "Error propagation strategies",
        ],
    },
    {
        "file": "timeout_handling.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 16,
        "title": "Timeout Handling",
        "description": "Prevent workflows from hanging with asyncio.wait_for timeouts.",
        "difficulty": "Intermediate",
        "time": "15 min",
        "tags": "timeout, error-handling, asyncio",
        "product": "blazing-flow",
        "learn": [
            "How to implement timeouts with asyncio.wait_for",
            "Handling TimeoutError exceptions",
            "When to use timeouts in workflows",
        ],
    },
    {
        "file": "aggregating_results.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 17,
        "title": "Aggregating Results",
        "description": "Fetch data from multiple sources and aggregate into summary statistics.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "aggregation, data, statistics, parallel",
        "product": "blazing-flow",
        "learn": [
            "Parallel data fetching patterns",
            "Result aggregation techniques",
            "Computing summary statistics",
        ],
    },
    {
        "file": "map_reduce.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 18,
        "title": "Map-Reduce Pattern",
        "description": "Distributed map-reduce for processing large datasets in chunks.",
        "difficulty": "Advanced",
        "time": "30 min",
        "tags": "map-reduce, distributed, big-data, parallel",
        "product": "blazing-flow",
        "learn": [
            "Map-reduce pattern implementation",
            "Data chunking strategies",
            "Distributed computing fundamentals",
        ],
    },
    {
        "file": "etl_pipeline.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 19,
        "title": "ETL Pipeline",
        "description": "Complete Extract-Transform-Load pipeline for data warehousing.",
        "difficulty": "Advanced",
        "time": "30 min",
        "tags": "etl, pipeline, data-warehouse, workflow",
        "product": "blazing-flow",
        "learn": [
            "ETL pipeline architecture",
            "Data extraction from sources",
            "Data transformation and loading",
        ],
    },
    {
        "file": "event_processing.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 20,
        "title": "Event Processing Pipeline",
        "description": "Validate, enrich, and store incoming events with multi-step processing.",
        "difficulty": "Intermediate",
        "time": "25 min",
        "tags": "events, pipeline, enrichment, validation",
        "product": "blazing-flow",
        "learn": [
            "Event processing architecture",
            "Data enrichment patterns",
            "Event storage strategies",
        ],
    },
    {
        "file": "csv_import.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 25,
        "title": "CSV Import Pipeline",
        "description": "Download, parse, validate, and import CSV files from cloud storage.",
        "difficulty": "Advanced",
        "time": "30 min",
        "tags": "csv, file-processing, import, validation",
        "product": "blazing-flow",
        "learn": [
            "CSV parsing with Python csv module",
            "File validation patterns",
            "Bulk import strategies",
        ],
    },
    {
        "file": "pdf_generation.py",
        "category": "03_data_processing",
        "source": CORE_DOCS,
        "example_num": 26,
        "title": "PDF Generation Workflow",
        "description": "Generate PDF documents from templates with data from multiple sources.",
        "difficulty": "Advanced",
        "time": "35 min",
        "tags": "pdf, generation, template, file-processing",
        "product": "blazing-flow",
        "learn": [
            "PDF generation with WeasyPrint",
            "Template rendering patterns",
            "Document storage and delivery",
        ],
    },
    # ===== 04_async_parallel (Concurrent processing 11-13) =====
    {
        "file": "parallel_processing.py",
        "category": "04_async_parallel",
        "source": CORE_DOCS,
        "example_num": 11,
        "title": "Parallel Data Processing",
        "description": "Process multiple items concurrently with asyncio.gather.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "parallel, asyncio, batch, performance",
        "product": "blazing-flow",
        "learn": [
            "How to process items in parallel",
            "Using asyncio.gather for concurrency",
            "Batch processing optimization",
        ],
    },
    {
        "file": "fan_out_fan_in.py",
        "category": "04_async_parallel",
        "source": CORE_DOCS,
        "example_num": 12,
        "title": "Fan-Out / Fan-In Pattern",
        "description": "Fetch data from multiple sources in parallel, then combine results.",
        "difficulty": "Advanced",
        "time": "25 min",
        "tags": "parallel, fan-out, fan-in, aggregation",
        "product": "blazing-flow",
        "learn": [
            "Fan-out/fan-in orchestration pattern",
            "Parallel data fetching strategies",
            "Result aggregation techniques",
        ],
    },
    {
        "file": "rate_limited_api.py",
        "category": "04_async_parallel",
        "source": CORE_DOCS,
        "example_num": 13,
        "title": "Rate-Limited API Calls",
        "description": "Control concurrency with asyncio.Semaphore for rate limiting.",
        "difficulty": "Advanced",
        "time": "25 min",
        "tags": "rate-limiting, semaphore, api, concurrency",
        "product": "blazing-flow",
        "learn": [
            "How to implement rate limiting with Semaphore",
            "Controlling concurrent API calls",
            "Preventing API throttling errors",
        ],
    },
    # ===== 05_integrations (Services 7-10, Webhooks 21-22, Notifications 23-24) =====
    {
        "file": "database_service.py",
        "category": "05_integrations",
        "source": CORE_DOCS,
        "example_num": 7,
        "title": "Database Service",
        "description": "Connect to PostgreSQL and perform database operations with SQLAlchemy.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "service, database, sqlalchemy, postgres",
        "product": "blazing-flow",
        "learn": [
            "How to create services with @app.service",
            "How to use SQLAlchemy connectors",
            "Database query patterns in services",
        ],
    },
    {
        "file": "rest_api_service.py",
        "category": "05_integrations",
        "source": CORE_DOCS,
        "example_num": 8,
        "title": "REST API Service",
        "description": "Call external REST APIs with httpx and handle responses.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "service, api, httpx, rest",
        "product": "blazing-flow",
        "learn": [
            "How to make HTTP requests from services",
            "How to manage API credentials with connectors",
            "Error handling for external API calls",
        ],
    },
    {
        "file": "cache_service.py",
        "category": "05_integrations",
        "source": CORE_DOCS,
        "example_num": 9,
        "title": "Cache Service",
        "description": "Implement caching with Redis for faster lookups.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "service, cache, redis, performance",
        "product": "blazing-flow",
        "learn": [
            "How to use Redis for caching",
            "Setting TTL (time-to-live) on cached values",
            "Cache-aside pattern implementation",
        ],
    },
    {
        "file": "email_service.py",
        "category": "05_integrations",
        "source": CORE_DOCS,
        "example_num": 10,
        "title": "Email Service",
        "description": "Send emails via SMTP service integration.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "service, email, smtp, notifications",
        "product": "blazing-flow",
        "learn": [
            "How to configure SMTP connectors",
            "Sending emails from workflows",
            "Template-based email composition",
        ],
    },
    {
        "file": "github_webhook.py",
        "category": "05_integrations",
        "source": CORE_DOCS,
        "example_num": 21,
        "title": "GitHub Webhook Handler",
        "description": "Process GitHub webhooks with signature validation and event handling.",
        "difficulty": "Advanced",
        "time": "30 min",
        "tags": "webhook, github, security, events",
        "product": "blazing-flow",
        "learn": [
            "How to validate webhook signatures",
            "Processing GitHub pull request events",
            "Secure webhook handling patterns",
        ],
    },
    {
        "file": "stripe_webhook.py",
        "category": "05_integrations",
        "source": CORE_DOCS,
        "example_num": 22,
        "title": "Stripe Payment Webhook",
        "description": "Handle Stripe payment webhooks with signature verification.",
        "difficulty": "Advanced",
        "time": "30 min",
        "tags": "webhook, stripe, payments, events",
        "product": "blazing-flow",
        "learn": [
            "Stripe webhook signature verification",
            "Processing payment intent events",
            "Order fulfillment workflow patterns",
        ],
    },
    {
        "file": "email_queue.py",
        "category": "05_integrations",
        "source": CORE_DOCS,
        "example_num": 23,
        "title": "Email Queue Processor",
        "description": "Process email queues in batches with Redis.",
        "difficulty": "Intermediate",
        "time": "25 min",
        "tags": "queue, email, batch, redis",
        "product": "blazing-flow",
        "learn": [
            "Queue-based email processing",
            "Batch processing patterns",
            "Redis as a message queue",
        ],
    },
    {
        "file": "multi_channel_notification.py",
        "category": "05_integrations",
        "source": CORE_DOCS,
        "example_num": 24,
        "title": "Multi-Channel Notification",
        "description": "Send notifications across email, SMS, and push channels simultaneously.",
        "difficulty": "Intermediate",
        "time": "25 min",
        "tags": "notifications, multi-channel, email, sms, push",
        "product": "blazing-flow",
        "learn": [
            "Multi-channel notification patterns",
            "Parallel notification delivery",
            "Channel selection logic",
        ],
    },
    # ===== 06_advanced (Scheduled 27-28, Streaming 29, Monitoring 30, Sandbox examples) =====
    {
        "file": "daily_reports.py",
        "category": "06_advanced",
        "source": CORE_DOCS,
        "example_num": 27,
        "title": "Daily Report Generation",
        "description": "Scheduled job to generate and distribute daily reports via email.",
        "difficulty": "Intermediate",
        "time": "25 min",
        "tags": "scheduled, reports, automation, email",
        "product": "blazing-flow",
        "learn": [
            "Scheduled workflow patterns",
            "Report generation from metrics",
            "Automated email distribution",
        ],
    },
    {
        "file": "cleanup_expired_records.py",
        "category": "06_advanced",
        "source": CORE_DOCS,
        "example_num": 28,
        "title": "Cleanup Expired Records",
        "description": "Batch delete expired database records on a schedule.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "cleanup, scheduled, batch, database",
        "product": "blazing-flow",
        "learn": [
            "Batch cleanup patterns",
            "Scheduled maintenance jobs",
            "Database cleanup strategies",
        ],
    },
    {
        "file": "event_stream_processor.py",
        "category": "06_advanced",
        "source": CORE_DOCS,
        "example_num": 29,
        "title": "Event Stream Processor",
        "description": "Process event streams from Kafka in batches with aggregation.",
        "difficulty": "Expert",
        "time": "40 min",
        "tags": "streaming, kafka, events, real-time",
        "product": "blazing-flow",
        "learn": [
            "Kafka consumer patterns",
            "Stream processing in batches",
            "Real-time event aggregation",
        ],
    },
    {
        "file": "health_check_workflow.py",
        "category": "06_advanced",
        "source": CORE_DOCS,
        "example_num": 30,
        "title": "Health Check Workflow",
        "description": "Monitor system health across database, cache, and external APIs.",
        "difficulty": "Intermediate",
        "time": "20 min",
        "tags": "monitoring, health-check, observability",
        "product": "blazing-flow",
        "learn": [
            "Health check implementation patterns",
            "Parallel service monitoring",
            "System observability strategies",
        ],
    },
    # ===== Sandbox Examples =====
    {
        "file": "sandbox_basic_transform.py",
        "category": "06_advanced",
        "source": SANDBOX_DOCS,
        "heading": "Basic User-Provided Transform",
        "title": "Sandbox: Basic User-Provided Transform",
        "description": "The simplest sandbox example: let users write transformation logic while your infrastructure stays protected.",
        "difficulty": "Intermediate",
        "time": "15 min",
        "tags": "sandbox, wasm, security, user-code",
        "product": "blazing-sandbox",
        "learn": [
            "How to run untrusted code in WASM sandbox",
            "Security guarantees of sandboxed execution",
            "Basic transformation patterns in sandbox",
        ],
    },
    {
        "file": "sandbox_database_service.py",
        "category": "06_advanced",
        "source": SANDBOX_DOCS,
        "heading": "Service Bridge: Database Access",
        "title": "Sandbox: Service Bridge with Database",
        "description": "Let user code process data while keeping database credentials safe.",
        "difficulty": "Advanced",
        "time": "25 min",
        "tags": "sandbox, service-bridge, database, security",
        "product": "blazing-sandbox",
        "learn": [
            "How the Service Bridge pattern works",
            "Allowing database access from sandboxed code",
            "Protecting credentials in multi-tenant systems",
        ],
    },
    {
        "file": "sandbox_rest_api_service.py",
        "category": "06_advanced",
        "source": SANDBOX_DOCS,
        "heading": "Service Bridge: REST API Calls",
        "title": "Sandbox: Service Bridge with REST APIs",
        "description": "Let users integrate with external APIs while keeping API keys safe.",
        "difficulty": "Advanced",
        "time": "25 min",
        "tags": "sandbox, service-bridge, api, security",
        "product": "blazing-sandbox",
        "learn": [
            "How to call external APIs from sandboxed code",
            "API key protection patterns",
            "Rate limiting at service level",
        ],
    },
    {
        "file": "sandbox_multi_tenant.py",
        "category": "06_advanced",
        "source": SANDBOX_DOCS,
        "heading": "Multi-Tenant Data Processing",
        "title": "Sandbox: Multi-Tenant Data Processing",
        "description": "Safely run different tenants' code in isolated sandboxes.",
        "difficulty": "Expert",
        "time": "35 min",
        "tags": "sandbox, multi-tenant, isolation, security",
        "product": "blazing-sandbox",
        "learn": [
            "Multi-tenant code execution patterns",
            "Tenant data isolation strategies",
            "Running different tenant code safely",
        ],
    },
    {
        "file": "sandbox_async_service_calls.py",
        "category": "06_advanced",
        "source": SANDBOX_DOCS,
        "heading": "Advanced: Async Service Calls",
        "title": "Sandbox: Async Service Calls",
        "description": "User code making concurrent service calls for performance.",
        "difficulty": "Expert",
        "time": "30 min",
        "tags": "sandbox, async, concurrent, service-bridge",
        "product": "blazing-sandbox",
        "learn": [
            "Concurrent service calls from sandbox",
            "Performance optimization in WASM",
            "Async patterns in sandboxed code",
        ],
    },
    {
        "file": "sandbox_security_validation.py",
        "category": "06_advanced",
        "source": SANDBOX_DOCS,
        "heading": "Security: What User Code CANNOT Do",
        "title": "Sandbox: Security Validation",
        "description": "Examples of malicious code that fails in the sandbox.",
        "difficulty": "Advanced",
        "time": "20 min",
        "tags": "sandbox, security, validation, attacks",
        "product": "blazing-sandbox",
        "learn": [
            "What code is blocked by WASM sandbox",
            "Security boundaries and guarantees",
            "Common attack patterns that fail",
        ],
    },
    {
        "file": "sandbox_production_deployment.py",
        "category": "06_advanced",
        "source": SANDBOX_DOCS,
        "heading": "Deployment: Production Setup",
        "title": "Sandbox: Production Deployment",
        "description": "Deploy sandboxed execution with Docker Compose.",
        "difficulty": "Expert",
        "time": "40 min",
        "tags": "sandbox, deployment, docker, production",
        "product": "blazing-sandbox",
        "learn": [
            "How to deploy sandboxed workers",
            "Production architecture for sandbox",
            "Worker type configuration",
        ],
    },
    {
        "file": "sandbox_monitoring.py",
        "category": "06_advanced",
        "source": SANDBOX_DOCS,
        "heading": "Monitoring Sandbox Execution",
        "title": "Sandbox: Monitoring & Observability",
        "description": "Monitor sandboxed operations and service calls.",
        "difficulty": "Advanced",
        "time": "25 min",
        "tags": "sandbox, monitoring, observability, metrics",
        "product": "blazing-sandbox",
        "learn": [
            "Monitoring sandboxed execution",
            "Tracking service calls from sandbox",
            "Key metrics for sandbox operations",
        ],
    },
]


if __name__ == "__main__":
    print("Extracting examples from docs...\n")

    created_count = 0
    failed_count = 0

    for example in EXAMPLES:
        try:
            create_example_file(example)
            created_count += 1
        except Exception as e:
            print(f"✗ Failed: {example['file']} - {e}")
            failed_count += 1

    print(f"\n{'=' * 60}")
    print("Summary:")
    print(f"  ✓ Created: {created_count} examples")
    print(f"  ✗ Failed: {failed_count} examples")
    print(f"{'=' * 60}")

    if created_count > 0:
        print("\nNext step: Run 'python generate_manifest.py' to update examples.json")
