#!/usr/bin/env bash
# ==============================================================================
# CloudNotes Observability Stack - SRE Automated Load Generator
# Sends 100 realistic CRUD requests to populate Prometheus & Grafana telemetry
# ==============================================================================

set -euo pipefail

# Configuration
APP_URL="${APP_URL:-http://localhost:8000}"
TOTAL_REQUESTS=100
SLEEP_INTERVAL=0.03 # 30ms jitter between requests

# ANSI Color codes
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
MAGENTA="\033[0;35m"
NC="\033[0m"

echo -e "${BOLD}${MAGENTA}==================================================================${NC}"
echo -e "${BOLD}${CYAN}  CloudNotes SRE Load Generator: 100 Realistic CRUD Requests     ${NC}"
echo -e "${BOLD}${MAGENTA}==================================================================${NC}"
echo -e "Target Application : ${BOLD}${APP_URL}${NC}"
echo -e "Total Requests     : ${BOLD}${TOTAL_REQUESTS}${NC}"
echo -e "Scrape Target      : ${BOLD}${APP_URL}/metrics${NC}\n"

# 1. Healthcheck probe
echo -e "${YELLOW}[1/3] Probing CloudNotes service healthcheck...${NC}"
if ! curl -s -f -m 3 "${APP_URL}/health" > /dev/null; then
  echo -e "${RED}[ERROR] Unable to reach ${APP_URL}/health!${NC}"
  echo -e "Please ensure the stack is running: ${BOLD}docker compose up -d${NC}"
  exit 1
fi
echo -e "${GREEN}[OK] Service is healthy and Redis connection is active.${NC}\n"

# 2. Realistic test payloads
TITLES=(
  "Azure Container Instances SLA Analysis"
  "Prometheus 5-Second Resolution Metrics"
  "Redis LRU Eviction Under Memory Pressure"
  "Grafana Dashboard Provisioning Best Practices"
  "FastAPI Async Event Loop Latency Profiling"
  "Terraform azurerm v5 Infrastructure as Code"
  "Kubernetes Horizontal Pod Autoscaling Triggers"
  "SRE Error Budget & Burn Rate Calculations"
  "Distributed Tracing with OpenTelemetry Spans"
  "Chaos Engineering: Simulated Redis Failover"
)

CONTENTS=(
  "Evaluating ACI serverless billing model for short-lived batch monitoring workloads."
  "Scraping metrics at 5s intervals enables rapid detection of microsecond latency spikes."
  "Testing Redis maxmemory flag with appendonly persistence enabled in Docker volume."
  "Provisioning dashboard JSON files automatically via Grafana file provider mount."
  "Non-blocking I/O in Uvicorn ASGI workers provides high concurrency per container."
  "Declarative resource groups and container groups deployed in southeastasia region."
  "Scaling pods dynamically using Prometheus custom metrics adapter."
  "Budgeting 99.9% availability gives a 43-minute monthly error window."
  "Propagating W3C tracecontext headers across service boundaries."
  "Validating graceful degradation when cache tier is temporarily partitioned."
)

CREATED_IDS=()
COUNT_POST=0
COUNT_GET=0
COUNT_DELETE=0
COUNT_ERRORS=0

START_TIME=$(date +%s.%N)

echo -e "${YELLOW}[2/3] Firing ${TOTAL_REQUESTS} simulated HTTP requests...${NC}"

for i in $(seq 1 "${TOTAL_REQUESTS}"); do
  MOD=$((i % 5))

  if [ "${MOD}" -eq 1 ] || [ "${MOD}" -eq 2 ]; then
    # POST /api/notes (40% of traffic)
    IDX=$(( (i - 1) % 10 ))
    TITLE="[#${i}] ${TITLES[${IDX}]}"
    BODY="{\"title\":\"${TITLE}\",\"content\":\"${CONTENTS[${IDX}]}\"}"
    
    RESP=$(curl -s -w "\n%{http_code}" -X POST "${APP_URL}/api/notes" \
      -H "Content-Type: application/json" \
      -d "${BODY}")
    
    HTTP_CODE=$(echo "${RESP}" | tail -n1)
    RESP_BODY=$(echo "${RESP}" | head -n-1)

    if [ "${HTTP_CODE}" -eq 201 ]; then
      COUNT_POST=$((COUNT_POST + 1))
      NOTE_ID=$(echo "${RESP_BODY}" | grep -o '"id":"[^"]*' | cut -d'"' -f4 || true)
      if [ -n "${NOTE_ID}" ]; then
        CREATED_IDS+=("${NOTE_ID}")
      fi
    else
      COUNT_ERRORS=$((COUNT_ERRORS + 1))
    fi

  elif [ "${MOD}" -eq 3 ] && [ "${#CREATED_IDS[@]}" -gt 0 ]; then
    # DELETE /api/notes/{id} (20% of traffic)
    DEL_ID="${CREATED_IDS[0]}"
    CREATED_IDS=("${CREATED_IDS[@]:1}") # Shift array
    
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "${APP_URL}/api/notes/${DEL_ID}")
    if [ "${HTTP_CODE}" -eq 200 ]; then
      COUNT_DELETE=$((COUNT_DELETE + 1))
    else
      COUNT_ERRORS=$((COUNT_ERRORS + 1))
    fi

  else
    # GET /api/notes or /health (40% of traffic)
    if [ $((i % 2)) -eq 0 ]; then
      HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${APP_URL}/api/notes")
    else
      HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${APP_URL}/health")
    fi

    if [ "${HTTP_CODE}" -eq 200 ]; then
      COUNT_GET=$((COUNT_GET + 1))
    else
      COUNT_ERRORS=$((COUNT_ERRORS + 1))
    fi
  fi

  # Progress bar display
  PERCENT=$(( (i * 100) / TOTAL_REQUESTS ))
  BAR_WIDTH=30
  FILLED=$(( (i * BAR_WIDTH) / TOTAL_REQUESTS ))
  EMPTY=$(( BAR_WIDTH - FILLED ))
  BAR=$(printf "%0.s#" $(seq 1 ${FILLED}))
  PADDING=$(printf "%0.s-" $(seq 1 ${EMPTY}))

  printf "\r${CYAN}Progress: [${GREEN}%s${YELLOW}%s${CYAN}] %3d%% (%d/%d requests)${NC}" \
    "${BAR}" "${PADDING}" "${PERCENT}" "${i}" "${TOTAL_REQUESTS}"

  sleep "${SLEEP_INTERVAL}"
done

END_TIME=$(date +%s.%N)
DURATION=$(python3 -c "print(f'{float(${END_TIME}) - float(${START_TIME}):.2f}')")
RPS=$(python3 -c "print(f'{${TOTAL_REQUESTS} / float(${DURATION}):.1f}')")

echo -e "\n\n${YELLOW}[3/3] Load Generation Summary${NC}"
echo -e "--------------------------------------------------"
echo -e "Elapsed Time         : ${BOLD}${DURATION} seconds${NC}"
echo -e "Average Throughput   : ${BOLD}${RPS} req/sec${NC}"
echo -e "POST Requests (201)  : ${GREEN}${COUNT_POST}${NC}"
echo -e "GET Requests (200)   : ${GREEN}${COUNT_GET}${NC}"
echo -e "DELETE Requests (200): ${GREEN}${COUNT_DELETE}${NC}"
echo -e "Failed Requests      : ${RED}${COUNT_ERRORS}${NC}"
echo -e "--------------------------------------------------"

echo -e "\n${BOLD}${GREEN}✔ Traffic generation complete! Inspect the live telemetry in your browser:${NC}"
echo -e "  - ${BOLD}Grafana Dashboard:${NC}   ${CYAN}http://localhost:3000${NC} (admin/admin)"
echo -e "  - ${BOLD}Prometheus Graph:${NC}    ${CYAN}http://localhost:9090${NC}"
echo -e "  - ${BOLD}Raw Metrics:${NC}         ${CYAN}http://localhost:8000/metrics${NC}"
echo -e "  - ${BOLD}CloudNotes UI:${NC}       ${CYAN}http://localhost:8000${NC}\n"
