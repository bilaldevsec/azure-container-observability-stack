"""
CloudNotes Microservice
A production-ready Python FastAPI microservice demonstrating cloud-native
observability with Redis caching and native Prometheus instrumentation.
"""

import os
import time
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import redis
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

REDIS_HASH_KEY = "cloudnotes:store"

# Initialize Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True,
    socket_connect_timeout=2.0,
    socket_timeout=2.0,
)

# -----------------------------------------------------------------------------
# Prometheus Metric Definitions
# -----------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "cloudnotes_http_requests_total",
    "Total count of HTTP requests processed by CloudNotes microservice",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "cloudnotes_http_request_duration_seconds",
    "Histogram of HTTP request durations in seconds",
    ["endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0),
)

ACTIVE_NOTES = Gauge(
    "cloudnotes_active_notes",
    "Current total number of active notes stored in Redis cache",
)

REDIS_OPERATIONS = Counter(
    "cloudnotes_redis_operations_total",
    "Total count of Redis cache operations performed",
    ["operation"],
)

# -----------------------------------------------------------------------------
# FastAPI Application & Lifecycle
# -----------------------------------------------------------------------------
app = FastAPI(
    title="CloudNotes Observability Microservice",
    description="Production-style observability microservice with FastAPI, Redis, and Prometheus.",
    version="1.0.0",
)


def refresh_active_notes_gauge() -> int:
    """Synchronizes the Prometheus active notes gauge with the current Redis count."""
    try:
        REDIS_OPERATIONS.labels(operation="hlen").inc()
        count = redis_client.hlen(REDIS_HASH_KEY)
        ACTIVE_NOTES.set(count)
        return count
    except Exception:
        ACTIVE_NOTES.set(0)
        return 0


@app.on_event("startup")
def startup_event():
    """Initializes gauge metric on service boot."""
    refresh_active_notes_gauge()


# -----------------------------------------------------------------------------
# HTTP Metrics Middleware
# -----------------------------------------------------------------------------
@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    """
    Measures latency and request outcomes across all endpoints,
    normalizing paths to avoid high-cardinality metric explosion.
    """
    start_time = time.time()
    raw_path = request.url.path

    # Normalize paths with UUIDs or parameters to keep cardinality low
    if raw_path.startswith("/api/notes/") and len(raw_path.split("/")) == 4:
        normalized_endpoint = "/api/notes/{note_id}"
    else:
        normalized_endpoint = raw_path

    try:
        response = await call_next(request)
        status_code = str(response.status_code)
    except Exception as exc:
        status_code = "500"
        duration = time.time() - start_time
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=normalized_endpoint,
            status=status_code,
        ).inc()
        REQUEST_DURATION.labels(endpoint=normalized_endpoint).observe(duration)
        raise exc

    duration = time.time() - start_time
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=normalized_endpoint,
        status=status_code,
    ).inc()
    REQUEST_DURATION.labels(endpoint=normalized_endpoint).observe(duration)

    return response


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, example="Container Observability")
    content: str = Field(..., min_length=1, max_length=2000, example="Prometheus scrapes metrics every 5s.")


class NoteResponse(BaseModel):
    id: str
    title: str
    content: str
    created_at: str


# -----------------------------------------------------------------------------
# Health & Telemetry Endpoints
# -----------------------------------------------------------------------------
@app.get("/health", summary="Service and Redis Healthcheck")
def healthcheck():
    """Validates connectivity to Redis backing store for Kubernetes/Docker health checks."""
    try:
        REDIS_OPERATIONS.labels(operation="ping").inc()
        is_alive = redis_client.ping()
        if is_alive:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "healthy", "redis": "connected"},
            )
    except Exception as err:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "redis": "disconnected", "error": str(err)},
        )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "unhealthy", "redis": "unknown"},
    )


@app.get("/metrics", summary="Prometheus Metrics Endpoint")
def get_metrics():
    """Exposes real-time Prometheus scrapable metrics in OpenMetrics exposition format."""
    # Refresh gauge right before exposition
    refresh_active_notes_gauge()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# -----------------------------------------------------------------------------
# Note CRUD Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/notes", response_model=List[NoteResponse], summary="List all notes")
def get_notes():
    """Retrieves all notes from the Redis hash store."""
    try:
        REDIS_OPERATIONS.labels(operation="hgetall").inc()
        raw_notes = redis_client.hgetall(REDIS_HASH_KEY)
        notes = []
        for raw in raw_notes.values():
            try:
                notes.append(json.loads(raw))
            except json.JSONDecodeError:
                continue

        # Sort newest first
        notes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
        refresh_active_notes_gauge()
        return notes
    except redis.RedisError as err:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(err)}")


@app.post("/api/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED, summary="Create a note")
def create_note(payload: NoteCreate):
    """Stores a new note inside Redis and updates active notes metric."""
    note_id = uuid.uuid4().hex[:8]
    note = {
        "id": note_id,
        "title": payload.title.strip(),
        "content": payload.content.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        REDIS_OPERATIONS.labels(operation="hset").inc()
        redis_client.hset(REDIS_HASH_KEY, note_id, json.dumps(note))
        refresh_active_notes_gauge()
        return note
    except redis.RedisError as err:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(err)}")


@app.delete("/api/notes/{note_id}", summary="Delete a note by ID")
def delete_note(note_id: str):
    """Deletes a note from Redis and decrements active notes metric."""
    try:
        REDIS_OPERATIONS.labels(operation="hexists").inc()
        if not redis_client.hexists(REDIS_HASH_KEY, note_id):
            raise HTTPException(status_code=404, detail="Note not found")

        REDIS_OPERATIONS.labels(operation="hdel").inc()
        redis_client.hdel(REDIS_HASH_KEY, note_id)
        refresh_active_notes_gauge()
        return {"status": "deleted", "id": note_id}
    except redis.RedisError as err:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(err)}")


# -----------------------------------------------------------------------------
# Frontend Interactive Dark Mode UI
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, summary="CloudNotes Interactive Observability Dashboard UI")
def index():
    """Serves a modern, responsive, dark-mode single-page application."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CloudNotes Observability Demo | SRE Dashboard</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #151d30;
      --card-border: #23304d;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --accent-hover: #0ea5e9;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #f43f5e;
      --purple: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: linear-gradient(180deg, #182239 0%, #0f172a 100%);
      border-bottom: 1px solid var(--card-border);
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .brand-icon {
      background: linear-gradient(135deg, #0284c7, #818cf8);
      width: 40px;
      height: 40px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.25rem;
      font-weight: bold;
    }
    .brand h1 {
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
    }
    .brand p {
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .header-links {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }
    .link-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.4rem 0.8rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      text-decoration: none;
      color: #fff;
      background-color: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--card-border);
      transition: all 0.2s ease;
    }
    .link-badge:hover {
      background-color: rgba(255, 255, 255, 0.16);
      transform: translateY(-1px);
    }
    .link-badge.grafana { border-color: #f97316; color: #fdba74; }
    .link-badge.prom { border-color: #ef4444; color: #fca5a5; }
    .link-badge.metrics { border-color: #10b981; color: #6ee7b7; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.35rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      background-color: rgba(16, 185, 129, 0.15);
      border: 1px solid var(--success);
      color: #34d399;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background-color: var(--success);
      box-shadow: 0 0 8px var(--success);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(0.9); }
    }
    main {
      flex: 1;
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
      padding: 2rem;
      display: grid;
      grid-template-columns: 1fr 1.3fr;
      gap: 2rem;
    }
    @media (max-width: 960px) {
      main { grid-template-columns: 1fr; }
    }
    .card {
      background-color: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    }
    .card-title {
      font-size: 1.1rem;
      font-weight: 600;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    .form-group {
      margin-bottom: 1rem;
    }
    label {
      display: block;
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 0.35rem;
      font-weight: 500;
    }
    input[type="text"], textarea {
      width: 100%;
      background-color: #0d1322;
      border: 1px solid var(--card-border);
      color: #fff;
      border-radius: 8px;
      padding: 0.65rem 0.85rem;
      font-size: 0.95rem;
      transition: border-color 0.2s;
    }
    input[type="text"]:focus, textarea:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
    }
    textarea { resize: vertical; min-height: 80px; }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      font-size: 0.9rem;
      font-weight: 600;
      padding: 0.65rem 1.25rem;
      border-radius: 8px;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
    }
    .btn-primary {
      background-color: var(--accent);
      color: #0b0f19;
    }
    .btn-primary:hover {
      background-color: var(--accent-hover);
    }
    .btn-spike {
      width: 100%;
      padding: 0.85rem 1rem;
      background: linear-gradient(135deg, #f43f5e 0%, #ec4899 50%, #8b5cf6 100%);
      color: #fff;
      font-size: 1rem;
      box-shadow: 0 4px 15px rgba(244, 63, 94, 0.35);
    }
    .btn-spike:hover {
      box-shadow: 0 6px 20px rgba(244, 63, 94, 0.5);
      transform: translateY(-1px);
    }
    .btn-spike:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none;
    }
    .btn-delete {
      background-color: rgba(244, 63, 94, 0.15);
      border: 1px solid rgba(244, 63, 94, 0.3);
      color: #fda4af;
      padding: 0.35rem 0.65rem;
      font-size: 0.8rem;
    }
    .btn-delete:hover {
      background-color: var(--danger);
      color: #fff;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 1rem;
      margin-bottom: 1.5rem;
    }
    .stat-box {
      background-color: #0d1322;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 1rem;
    }
    .stat-label {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }
    .stat-value {
      font-size: 1.5rem;
      font-weight: 700;
      color: #fff;
    }
    .notes-list {
      max-height: 480px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      padding-right: 0.35rem;
    }
    .note-item {
      background-color: #0d1322;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 1rem;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      transition: border-color 0.2s;
    }
    .note-item:hover {
      border-color: #38bdf8;
    }
    .note-content h3 {
      font-size: 1rem;
      font-weight: 600;
      color: #fff;
      margin-bottom: 0.25rem;
    }
    .note-content p {
      font-size: 0.88rem;
      color: #cbd5e1;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .note-content .timestamp {
      font-size: 0.72rem;
      color: var(--text-muted);
      margin-top: 0.5rem;
    }
    .progress-bar-container {
      width: 100%;
      height: 8px;
      background-color: #0d1322;
      border-radius: 4px;
      overflow: hidden;
      margin: 1rem 0;
      display: none;
    }
    .progress-bar {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #38bdf8, #ec4899);
      transition: width 0.1s ease;
    }
    .log-box {
      background-color: #070a12;
      border: 1px solid #1a2234;
      border-radius: 6px;
      padding: 0.75rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.78rem;
      color: #94a3b8;
      height: 140px;
      overflow-y: auto;
      margin-top: 0.75rem;
    }
    .log-entry { margin-bottom: 0.25rem; }
    .log-entry.success { color: #34d399; }
    .log-entry.warn { color: #fbbf24; }
    .log-entry.info { color: #38bdf8; }
    footer {
      text-align: center;
      padding: 1.5rem;
      border-top: 1px solid var(--card-border);
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-top: auto;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-icon">⚡</div>
      <div>
        <h1>CloudNotes Observability Demo</h1>
        <p>Python FastAPI + Redis + Prometheus & Grafana Stack</p>
      </div>
    </div>
    <div class="header-links">
      <span class="status-pill" id="healthPill">
        <span class="status-dot"></span>
        <span id="healthText">Redis: Checking...</span>
      </span>
      <a href="http://localhost:9090" target="_blank" class="link-badge prom">📊 Prometheus :9090</a>
      <a href="http://localhost:3000" target="_blank" class="link-badge grafana">📈 Grafana :3000</a>
      <a href="/metrics" target="_blank" class="link-badge metrics">📉 /metrics</a>
    </div>
  </header>

  <main>
    <!-- Left Column: Controls & Traffic Generator -->
    <div>
      <!-- Traffic Spike Generator Card -->
      <div class="card">
        <div class="card-title">🔥 Live SRE Traffic Simulator</div>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
          Trigger an automated barrage of 50 asynchronous HTTP operations (Create, List, Healthcheck, Delete) to simulate real-world microservice traffic and watch Prometheus metrics spike in real time!
        </p>
        <button id="btnSpike" class="btn btn-spike" onclick="simulateSpike()">
          ⚡ Simulate Traffic Spike (50 Requests)
        </button>
        <div class="progress-bar-container" id="progressContainer">
          <div class="progress-bar" id="progressBar"></div>
        </div>
        <div class="log-box" id="logBox">
          <div class="log-entry info">[System] Ready. Click button above to fire 50 real-time requests.</div>
        </div>
      </div>

      <!-- Create Note Card -->
      <div class="card">
        <div class="card-title">✍️ Create New Note</div>
        <form id="noteForm" onsubmit="handleCreateNote(event)">
          <div class="form-group">
            <label for="title">Note Title</label>
            <input type="text" id="title" placeholder="e.g. Observability Best Practices" required maxlength="100">
          </div>
          <div class="form-group">
            <label for="content">Note Content</label>
            <textarea id="content" placeholder="e.g. Scrape interval set to 5s for rapid telemetry resolution..." required></textarea>
          </div>
          <button type="submit" class="btn btn-primary" id="btnSubmit">💾 Save Note to Redis</button>
        </form>
      </div>
    </div>

    <!-- Right Column: Live Data & Notes Feed -->
    <div>
      <!-- Live Metrics Telemetry Summary -->
      <div class="card">
        <div class="card-title">📊 Live Telemetry Counters</div>
        <div class="stats-grid">
          <div class="stat-box">
            <div class="stat-label">Active Notes (Redis)</div>
            <div class="stat-value" id="statNotesCount" style="color: #38bdf8;">-</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Session Requests Fired</div>
            <div class="stat-value" id="statSessionRequests" style="color: #a855f7;">0</div>
          </div>
        </div>
        <p style="font-size: 0.78rem; color: var(--text-muted);">
          * All operations update Prometheus metrics: <code>cloudnotes_http_requests_total</code>, <code>cloudnotes_http_request_duration_seconds</code>, and <code>cloudnotes_active_notes</code>.
        </p>
      </div>

      <!-- Notes Feed -->
      <div class="card">
        <div class="card-title">
          <span>📝 Notes in Cache</span>
          <span style="font-size: 0.8rem; font-weight: normal; color: var(--text-muted); margin-left: auto;" id="notesHeaderCount">0 stored</span>
        </div>
        <div class="notes-list" id="notesList">
          <div style="text-align: center; color: var(--text-muted); padding: 2rem;">Loading notes from Redis...</div>
        </div>
      </div>
    </div>
  </main>

  <footer>
    Containerized Monitoring &amp; Observability Stack &bull; FastAPI + Redis + Prometheus + Grafana &bull; Azure SRE Architecture
  </footer>

  <script>
    let sessionRequests = 0;
    const logBox = document.getElementById("logBox");

    function log(message, type = 'info') {
      const entry = document.createElement("div");
      entry.className = "log-entry " + type;
      const now = new Date().toLocaleTimeString();
      entry.textContent = `[${now}] ${message}`;
      logBox.appendChild(entry);
      logBox.scrollTop = logBox.scrollHeight;
    }

    async function checkHealth() {
      try {
        const res = await fetch("/health");
        const data = await res.json();
        const pill = document.getElementById("healthPill");
        const text = document.getElementById("healthText");
        if (res.ok && data.status === "healthy") {
          text.textContent = "Redis: Connected";
          pill.style.borderColor = "var(--success)";
          pill.style.color = "#34d399";
        } else {
          text.textContent = "Redis: Degraded";
          pill.style.borderColor = "var(--danger)";
          pill.style.color = "#f43f5e";
        }
      } catch (err) {
        document.getElementById("healthText").textContent = "API: Offline";
      }
    }

    async function fetchNotes() {
      try {
        const res = await fetch("/api/notes");
        const notes = await res.json();
        const listEl = document.getElementById("notesList");
        document.getElementById("statNotesCount").textContent = notes.length;
        document.getElementById("notesHeaderCount").textContent = `${notes.length} stored`;

        if (notes.length === 0) {
          listEl.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 2rem;">No notes in Redis cache yet. Create one or run the spike simulation!</div>';
          return;
        }

        listEl.innerHTML = "";
        notes.forEach(note => {
          const item = document.createElement("div");
          item.className = "note-item";
          const dateStr = note.created_at ? new Date(note.created_at).toLocaleString() : "";
          item.innerHTML = `
            <div class="note-content">
              <h3>${escapeHtml(note.title)}</h3>
              <p>${escapeHtml(note.content)}</p>
              <div class="timestamp">ID: ${note.id} &bull; ${dateStr}</div>
            </div>
            <button class="btn btn-delete" onclick="handleDeleteNote('${note.id}')">Delete</button>
          `;
          listEl.appendChild(item);
        });
      } catch (err) {
        console.error("Failed to fetch notes:", err);
      }
    }

    function escapeHtml(text) {
      if (!text) return "";
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    async function handleCreateNote(event) {
      event.preventDefault();
      const titleInput = document.getElementById("title");
      const contentInput = document.getElementById("content");
      const btn = document.getElementById("btnSubmit");

      btn.disabled = true;
      btn.textContent = "Saving...";

      try {
        const res = await fetch("/api/notes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: titleInput.value,
            content: contentInput.value
          })
        });

        sessionRequests++;
        document.getElementById("statSessionRequests").textContent = sessionRequests;

        if (res.ok) {
          log(`Created note: "${titleInput.value}"`, "success");
          titleInput.value = "";
          contentInput.value = "";
          await fetchNotes();
        } else {
          log(`Failed to create note: HTTP ${res.status}`, "warn");
        }
      } catch (err) {
        log(`Error: ${err.message}`, "warn");
      } finally {
        btn.disabled = false;
        btn.textContent = "💾 Save Note to Redis";
      }
    }

    async function handleDeleteNote(noteId) {
      try {
        const res = await fetch(`/api/notes/${noteId}`, { method: "DELETE" });
        sessionRequests++;
        document.getElementById("statSessionRequests").textContent = sessionRequests;
        if (res.ok) {
          log(`Deleted note: ${noteId}`, "info");
          await fetchNotes();
        }
      } catch (err) {
        log(`Delete error: ${err.message}`, "warn");
      }
    }

    async function simulateSpike() {
      const btn = document.getElementById("btnSpike");
      const progressContainer = document.getElementById("progressContainer");
      const progressBar = document.getElementById("progressBar");

      btn.disabled = true;
      progressContainer.style.display = "block";
      progressBar.style.width = "0%";
      log("⚡ Initiating traffic spike: 50 requests...", "info");

      const topics = [
        "Kubernetes Horizontal Pod Autoscaling",
        "Prometheus TSDB Compaction & Retention",
        "Redis LRU Cache Invalidation Policy",
        "Grafana Alerting & PagerDuty Integration",
        "Azure Container Instances Serverless Scalability",
        "Distributed Tracing with OpenTelemetry",
        "FastAPI Asynchronous Request Pipeline",
        "SRE Error Budget & SLO Calculations"
      ];

      const createdIds = [];
      const total = 50;

      for (let i = 1; i <= total; i++) {
        try {
          const mod = i % 4;
          if (mod === 1 || mod === 2) {
            // POST request
            const topic = topics[Math.floor(Math.random() * topics.length)];
            const res = await fetch("/api/notes", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                title: `[Spike #${i}] ${topic}`,
                content: `Automated load test payload emitted at ${new Date().toISOString()}`
              })
            });
            if (res.ok) {
              const data = await res.json();
              createdIds.push(data.id);
            }
          } else if (mod === 3 && createdIds.length > 0) {
            // DELETE request
            const idToDelete = createdIds.pop();
            await fetch(`/api/notes/${idToDelete}`, { method: "DELETE" });
          } else {
            // GET list or Health
            if (i % 2 === 0) {
              await fetch("/api/notes");
            } else {
              await fetch("/health");
            }
          }
        } catch (e) {
          // Ignore network glitch during spike
        }

        sessionRequests++;
        document.getElementById("statSessionRequests").textContent = sessionRequests;
        progressBar.style.width = `${Math.round((i / total) * 100)}%`;

        if (i % 10 === 0) {
          log(`Completed ${i}/${total} requests...`, "info");
          await fetchNotes();
        }

        // Slight micro-jitter for realistic latency spread
        await new Promise(r => setTimeout(r, 20));
      }

      log("🎉 Spike finished! Check Prometheus (:9090) and Grafana (:3000) for telemetry wave.", "success");
      await fetchNotes();
      btn.disabled = false;
      setTimeout(() => {
        progressContainer.style.display = "none";
      }, 3000);
    }

    // Auto-refresh loops
    checkHealth();
    fetchNotes();
    setInterval(checkHealth, 5000);
    setInterval(fetchNotes, 8000);
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content, status_code=200)
