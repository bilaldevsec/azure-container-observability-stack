# Containerized Monitoring & Observability Stack on Azure using Docker, Redis, Prometheus & Grafana

[![Docker](https://img.shields.io/badge/Docker-20.10%2B-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-v2-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-7.2-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Prometheus](https://img.shields.io/badge/Prometheus-v2.51.0-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Grafana-10.4.1-F46800?logo=grafana&logoColor=white)](https://grafana.com/)
[![Terraform](https://img.shields.io/badge/Terraform-1.5%2B-844FBA?logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Azure ACI](https://img.shields.io/badge/Azure-Container_Instances-0078D4?logo=microsoftazure&logoColor=white)](https://azure.microsoft.com/en-us/products/container-instances)

A production-style Site Reliability Engineering (SRE) and Cloud DevOps observability platform. This repository demonstrates end-to-end telemetry instrumentation, container networking, automated dashboard provisioning, load testing, and serverless cloud deployment on **Azure Container Instances (ACI)** in the `southeastasia` region.

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Visual Architecture Diagram](#visual-architecture-diagram)
3. [Container Network Topology & Ports](#container-network-topology--ports)
4. [Microservice Architecture & Native Metrics](#microservice-architecture--native-metrics)
5. [PromQL Metrics & SRE Dashboard Reference](#promql-metrics--sre-dashboard-reference)
6. [Local Quickstart Guide](#local-quickstart-guide)
7. [Automated Load Testing & Traffic Simulation](#automated-load-testing--traffic-simulation)
8. [Serverless Azure ACI Deployment Guide](#serverless-azure-aci-deployment-guide)
9. [SRE & Security Best Practices](#sre--security-best-practices)
10. [Repository File Structure](#repository-file-structure)

---

## Architecture Overview

Modern distributed systems require continuous visibility into request rates, latency distributions, error budgets, and backing infrastructure utilization. This repository implements the **Four Golden Signals of SRE** (Latency, Traffic, Errors, Saturation) across two environments:

1. **Local Multi-Service Docker Compose Environment**:
   - **`notes-app`**: Custom Python 3.12 FastAPI microservice with non-root security and native Prometheus instrumentation (`prometheus-client`).
   - **`redis`**: High-performance in-memory key-value cache and persistent data store running on an isolated internal network (`172.28.0.0/16`).
   - **`redis-exporter`**: Metrics adapter exposing Redis internal commands, memory allocations, and connection pools to Prometheus format.
   - **`prometheus`**: Time-Series Database (TSDB) configured with high-frequency 5-second scraping intervals for rapid anomaly detection.
   - **`grafana`**: Visualization platform with auto-provisioned Prometheus datasources and a rich 6-panel pre-built SRE dashboard.

2. **Serverless Cloud Deployment on Azure (ACI)**:
   - Deploys `prom/prometheus:v2.51.0`, `redis:7.2-alpine`, and `oliver006/redis_exporter:v1.58.0-alpine` side-by-side inside a single **Azure Container Group**.
   - Containers share a private `localhost` (`127.0.0.1`) loopback network within the Azure hypervisor sandbox.
   - Exposes a public FQDN (`*.southeastasia.azurecontainer.io:9090`) for immediate verification.
   - Designed for **Azure for Students** subscriptions with total resource caps of **1.0 vCPU and 1.5 GB RAM**, keeping test execution costs at **~$0.01**.

---

## Visual Architecture Diagram

A high-resolution, interactive SVG diagram is available at [`docs/architecture-diagram.html`](file:///home/muhammad-bilal/projects/azure-container-observability-stack/docs/architecture-diagram.html). Open this file in any web browser to inspect the container boundaries, CIDR subnets, and metric telemetry flows.

```
       +-------------------------------------------------------------+
       |             Host / Client Browser (localhost)               |
       +-------------------------------------------------------------+
            | (:8000)                   | (:9090)             | (:3000)
            v                           v                     v
+-------------------------------------------------------------------------+
| Docker Custom Bridge Network: observability-net (172.28.0.0/16)         |
|                                                                         |
|   +-----------------------+              +--------------------------+   |
|   |   notes-app:8000      |---CRUD/Ping->|   redis:6379             |   |
|   |   (FastAPI Microsvc)  |              |   (In-Memory Cache)      |   |
|   |   [appuser, 256M]     |              |   [Internal only, 128M]  |   |
|   +-----------------------+              +--------------------------+   |
|              ^                                         ^                |
|              | GET /metrics (every 5s)                 | poll           |
|              |                                         |                |
|   +-----------------------+              +--------------------------+   |
|   |   prometheus:9090     |              |   redis-exporter:9121    |   |
|   |   (TSDB Storage)      |--5s Scrape-->|   (Metrics Adapter)      |   |
|   |   [256M Limit]        |              |   [64M Limit]            |   |
|   +-----------------------+              +--------------------------+   |
|              ^                                                          |
|              | PromQL Queries via auto-provisioned Datasource           |
|              |                                                          |
|   +-----------------------+                                             |
|   |   grafana:3000        |                                             |
|   |   (SRE Dashboards)    |                                             |
|   |   [256M Limit]        |                                             |
|   +-----------------------+                                             |
+-------------------------------------------------------------------------+
```

---

## Container Network Topology & Ports

| Service Name | Base Docker Image | Internal Port | Host Port | Network CIDR | Memory Limit | Healthcheck Probe |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`redis`** | `redis:7.2-alpine` | `6379` | *None (Hidden)* | `172.28.0.2` | `128 MB` | `redis-cli ping` (every 5s) |
| **`redis-exporter`** | `oliver006/redis_exporter:v1.58.0-alpine` | `9121` | `9121:9121` | `172.28.0.3` | `64 MB` | TCP socket check |
| **`notes-app`** | `python:3.12-slim` (custom) | `8000` | `8000:8000` | `172.28.0.4` | `256 MB` | `curl -f /health` (every 15s) |
| **`prometheus`** | `prom/prometheus:v2.51.0` | `9090` | `9090:9090` | `172.28.0.5` | `256 MB` | TSDB ready probe |
| **`grafana`** | `grafana/grafana:10.4.1` | `3000` | `3000:3000` | `172.28.0.6` | `256 MB` | HTTP status 200 probe |

---

## Microservice Architecture & Native Metrics

The application layer (`app/main.py`) is written in Python FastAPI with non-blocking ASGI execution and instrumented natively using the official `prometheus-client` library.

### Key Microservice Endpoints
- `GET /` — Responsive dark-mode single-page application (CloudNotes Observability Demo) with real-time health indicator, CRUD note management, live telemetry counters, and a one-click **"Simulate Traffic Spike (50 Requests)"** button.
- `GET /health` — Service readiness probe verifying end-to-end Redis ping connectivity (returns HTTP `200` if healthy, `503` if degraded).
- `GET /api/notes` — Retrieves notes stored in the Redis hash `cloudnotes:store`.
- `POST /api/notes` — Persists new notes with automatic UUID generation.
- `DELETE /api/notes/{note_id}` — Deletes notes and adjusts gauge metrics.
- `GET /metrics` — Exposes Prometheus OpenMetrics exposition format.

### Cardinality Protection Middleware
To prevent metric explosion in Prometheus TSDB (a common SRE failure mode), dynamic route parameters (e.g. `/api/notes/a1b2c3d4`) are normalized to static templates (`/api/notes/{note_id}`) before being labeled into time-series counters.

---

## PromQL Metrics & SRE Dashboard Reference

The auto-provisioned Grafana dashboard (`monitoring/grafana/dashboards/cloudnotes-observability.json`) is configured with 6 production-grade panels:

| Panel Title | Metric Type | PromQL Query | Purpose / Alerting Rule |
| :--- | :--- | :--- | :--- |
| **1. Total HTTP Request Rate** | Counter | `sum(rate(cloudnotes_http_requests_total[1m])) by (method, endpoint)` | Tracks incoming request throughput per second by API route. |
| **2. p95 API Latency** | Histogram | `histogram_quantile(0.95, sum(rate(cloudnotes_http_request_duration_seconds_bucket[1m])) by (le, endpoint))` | Measures 95th percentile response latency; alerts if latency exceeds 200ms. |
| **3. Active Notes in Redis** | Gauge | `cloudnotes_active_notes` | Real-time gauge reflecting cached items in Redis. |
| **4. Redis Commands/sec** | Counter | `rate(redis_commands_processed_total[1m])` | Evaluates cache operational throughput and pipeline saturation. |
| **5. HTTP Status Code Breakdown** | Counter | `sum by (status) (rate(cloudnotes_http_requests_total[1m]))` | Error budget monitoring: visualizes 2xx success vs 4xx/5xx failure rates. |
| **6. Redis Memory & Clients** | Gauge | `redis_memory_used_bytes`, `redis_connected_clients` | Saturation monitoring for cache memory limits and connection leaks. |

---

## Local Quickstart Guide

### Prerequisites
- Docker Engine `20.10+` and Docker Compose `v2+`
- `curl` and `bash`

### 1. Build and Start the Observability Stack
```bash
# Validate Compose configuration
docker compose config --quiet

# Start all 5 services in detached mode
docker compose up -d
```

### 2. Verify Container Health
```bash
docker compose ps
```
All containers will display `healthy` or `running`.

### 3. Access UIs in Browser
- **CloudNotes Interactive App**: [http://localhost:8000](http://localhost:8000)
- **Prometheus TSDB**: [http://localhost:9090](http://localhost:9090)
- **Grafana Observability Dashboard**: [http://localhost:3000](http://localhost:3000)
  * Credentials: User `admin` / Password `admin`
  * Dashboard path: *Dashboards > CloudNotes SRE > CloudNotes Observability & SRE Dashboard*

---

## Automated Load Testing & Traffic Simulation

To instantly observe Prometheus scraping curves and Grafana latency percentiles without manual clicking, two traffic generation options are available:

### Option A: Interactive UI Spike Generator
1. Open [http://localhost:8000](http://localhost:8000) in your browser.
2. Click the gradient **"⚡ Simulate Traffic Spike (50 Requests)"** button.
3. Observe real-time progress bars, request logs, and metric counters updating on-screen.

### Option B: Automated SRE Bash Script
Run the included load generator script to fire 100 realistic CRUD operations:
```bash
./scripts/load_test.sh
```

**Script execution output:**
```
==================================================================
  CloudNotes SRE Load Generator: 100 Realistic CRUD Requests     
==================================================================
Target Application : http://localhost:8000
Total Requests     : 100
Scrape Target      : http://localhost:8000/metrics

[1/3] Probing CloudNotes service healthcheck...
[OK] Service is healthy and Redis connection is active.

[2/3] Firing 100 simulated HTTP requests...
Progress: [##############################] 100% (100/100 requests)

[3/3] Load Generation Summary
--------------------------------------------------
Elapsed Time         : 3.42 seconds
Average Throughput   : 29.2 req/sec
POST Requests (201)  : 40
GET Requests (200)   : 40
DELETE Requests (200): 20
Failed Requests      : 0
--------------------------------------------------
✔ Traffic generation complete! Inspect the live telemetry in your browser:
  - Grafana Dashboard:   http://localhost:3000 (admin/admin)
  - Prometheus Graph:    http://localhost:9090
```

---

## Serverless Azure ACI Deployment Guide

For cloud deployments, Terraform provisions an Azure Container Group running Prometheus, Redis, and Redis Exporter directly on serverless infrastructure.

### Cost & Region Design
- **Region**: `southeastasia` (strictly permitted under Azure for Students).
- **Resource Constraints**: Total CPU = `1.0 vCPU`, Total Memory = `1.5 GB RAM`.
- **Testing Cost**: Serverless per-second execution billing (~$0.0000125/vCPU-s + ~$0.0000015/GB-s). A standard 15-minute verification run costs **~$0.01 USD**.
- **No VM or ACR Overhead**: Runs public Docker Hub images without requiring a paid Azure Container Registry or dedicated Virtual Machine.

### 1. Initialize and Validate Terraform
```bash
cd terraform
terraform init -backend=false
terraform fmt -check
terraform validate
```

### 2. Authenticate to Azure and Deploy
```bash
# Log in to Azure CLI
az login

# Preview execution plan
terraform plan

# Apply infrastructure
terraform apply -auto-approve
```

### 3. Verify Public Cloud Telemetry
Terraform outputs the public domain and IP:
```bash
terraform output prometheus_ui_url
# Example: http://cloudnotes-obs-a1b2c3.southeastasia.azurecontainer.io:9090
```
Open the URL in any browser to verify that Prometheus is actively scraping Redis and Redis Exporter metrics in Azure!

### 4. Teardown Cloud Infrastructure
To guarantee zero unexpected cloud expenditure, destroy all Azure resources immediately after testing:
```bash
terraform destroy -auto-approve
```

---

## SRE & Security Best Practices

1. **Non-Root Execution (Principle of Least Privilege)**:
   - The FastAPI container runs as an unprivileged user (`appuser`, UID `1001`), preventing container breakout vulnerabilities.
2. **Explicit Memory Capping**:
   - Every service in `docker-compose.yml` has declared memory limits (`deploy.resources.limits.memory`) to protect the host against Out-Of-Memory (OOM) kernel panics.
3. **Internal-Only Data Stores**:
   - Redis port `6379` is only accessible inside `observability-net`; it is never published to the host machine interface.
4. **Resilient Health Probes**:
   - `notes-app` uses a multi-retried healthcheck that waits for Redis readiness before serving incoming traffic.
5. **Decoupled Telemetry Scraping**:
   - Prometheus operates on a pull-based 5-second scrape model, decoupling observability overhead from microservice critical paths.

---

## Repository File Structure

```
azure-container-observability-stack/
├── app/
│   ├── Dockerfile                  # Multi-stage non-root Python 3.12 container
│   ├── main.py                     # FastAPI microservice with Prometheus instrumentation & dark UI
│   └── requirements.txt            # Python dependencies (fastapi, uvicorn, redis, prometheus-client)
├── docker-compose.yml              # 5-service stack with custom bridge network & memory limits
├── docs/
│   └── architecture-diagram.html   # Standalone interactive SVG architecture diagram
├── monitoring/
│   ├── grafana/
│   │   ├── dashboards/
│   │   │   └── cloudnotes-observability.json # 6 prebuilt SRE panels (schemaVersion 38)
│   │   └── provisioning/
│   │       ├── dashboards/
│   │       │   └── dashboard.yml   # Auto-loads dashboards from /var/lib/grafana/dashboards
│   │       └── datasources/
│   │           └── datasource.yml  # Auto-provisions Prometheus datasource (proxy mode)
│   └── prometheus/
│       └── prometheus.yml          # Scrapes notes-app, redis-exporter, and self every 5s
├── scripts/
│   └── load_test.sh                # Automated 100-request CRUD load simulation script
├── terraform/
│   ├── main.tf                     # Azure Container Group (Prometheus + Redis + Exporter) in southeastasia
│   ├── outputs.tf                  # Public FQDN, IP, and Prometheus UI URL outputs
│   └── variables.tf                # Region defaults, tags, and container parameters
└── README.md                       # Comprehensive SRE & DevOps documentation
```

---

## License
MIT License. Built for Cloud DevOps & Site Reliability Engineering Demonstrations.
