# Deployment Guide

This guide provides instructions and best practices for deploying a Blazing application to production.

## Overview

A Blazing application consists of three main components that need to be deployed:

1.  **Redis:** The central message broker and state store. A production-grade Redis setup (e.g., with persistence and high availability) is recommended.
2.  **HQ (Headquarters):** The central control plane for Blazing. You should run at least one HQ process.
3.  **Coordinator:** The process that manages worker processes on each machine. You should run one Coordinator process on each machine where you want to execute tasks.

## Configuration

It is recommended to configure your Blazing application using environment variables for production deployments. This avoids hardcoding sensitive information in your code.

### Redis Configuration

The HQ and Coordinator processes need to connect to Redis. You can configure the connection via environment variables that the `Blazing` object can read. For example:

```bash
export REDIS_HOST=your-redis-host
export REDIS_PORT=6379
export REDIS_PASSWORD=your-redis-password
```

Your application code would then read these environment variables to configure the `redis_config` for the `Blazing` object.

### Encryption Key

For security, you should use an encryption key to protect sensitive data like connector credentials. This can also be provided via an environment variable:

```bash
export BLAZING_ENCRYPTION_KEY=your-secret-key
```

## Deployment Strategies

### Using Docker

Docker is a recommended way to deploy Blazing components, as it provides a consistent and isolated environment.

**1. Dockerfile for your application:**

You'll need a `Dockerfile` for your application that includes your code and dependencies.

```Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY . .

# Command to run will be provided at runtime
```

**2. Docker Compose for local development and testing:**

You can use `docker-compose.yml` to orchestrate the services for local testing.

```yaml
version: '3.8'
services:
  redis:
    image: "redis/redis-stack:latest"
    ports:
      - "6379:6379"

  hq:
    build: .
    command: python scripts/start_HQ.py
    environment:
      - REDIS_HOST=redis
    depends_on:
      - redis

  coordinator:
    build: .
    command: python scripts/start_coordinator.py
    environment:
      - REDIS_HOST=redis
    depends_on:
      - redis
```

**3. Kubernetes for production:**

For a production deployment, you can use Kubernetes to manage your Blazing services. You would create deployments for the HQ and Coordinator processes, and a StatefulSet for Redis.

### Using systemd

On a Linux server, you can use `systemd` to manage the HQ and Coordinator processes.

**1. HQ Service (`/etc/systemd/system/blazing-hq.service`):**

```ini
[Unit]
Description=Blazing HQ Service
After=network.target

[Service]
User=your-user
Group=your-group
WorkingDirectory=/path/to/your/project
Environment="REDIS_HOST=your-redis-host"
ExecStart=/path/to/your/venv/bin/python scripts/start_HQ.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**2. Coordinator Service (`/etc/systemd/system/blazing-coordinator.service`):**

```ini
[Unit]
Description=Blazing Coordinator Service
After=network.target

[Service]
User=your-user
Group=your-group
WorkingDirectory=/path/to/your/project
Environment="REDIS_HOST=your-redis-host"
ExecStart=/path/to/your/venv/bin/python scripts/start_coordinator.py
Restart=always

[Install]
WantedBy=multi-user.target
```

You can then enable and start the services:

```bash
sudo systemctl enable blazing-hq.service
sudo systemctl start blazing-hq.service

sudo systemctl enable blazing-coordinator.service
sudo systemctl start blazing-coordinator.service
```

## Scaling

-   **Workers:** The number of workers is managed by the Coordinator. You can scale your application horizontally by adding more machines and running a Coordinator on each. The worker mix (async vs. blocking) is automatically optimized by the Coordinator based on the workload.
-   **HQ:** The HQ is stateless (all state is in Redis), so you can run multiple HQ instances for high availability, although only one is strictly necessary for the system to function.
-   **Redis:** For large-scale deployments, you should use a clustered Redis setup to handle the load.

## Monitoring

The `architecture.md` file mentions `blazing_service/monitoring/btop.py` and `blazing_service/monitoring/monitor_coordinator_charts.py` for monitoring. These tools can be used to get real-time insights into your Blazing application.

For production monitoring, you can:

-   **Log analysis:** Collect and analyze the logs from the HQ and Coordinator processes. The `worker_mix.log` file is particularly useful for understanding how the worker mix is being optimized.
-   **Redis monitoring:** Monitor the health and performance of your Redis instance. Pay attention to memory usage, CPU usage, and the number of connected clients.
-   **Prometheus/Grafana:** You could extend the Blazing components to expose metrics in a Prometheus format, and then use Grafana to create dashboards for monitoring your application.
