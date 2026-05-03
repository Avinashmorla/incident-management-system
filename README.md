# Incident Management System (IMS)

A production-inspired Incident Management System for high-volume signal ingestion, debounced incident creation, workflow-driven resolution, and mandatory Root Cause Analysis (RCA).

Modern distributed systems generate large volumes of signals such as errors, latency spikes, and dependency failures. Without aggregation and workflow, this creates alert fatigue and slow recovery. This project ingests those signals asynchronously, links repeated signals to a single work item, tracks the incident lifecycle, and exposes a dashboard for responders.

## Architecture

```mermaid
flowchart LR
  Producer["Signal Producers"] --> API["FastAPI Ingestion API"]
  API --> Limiter["Sliding Window Rate Limiter"]
  Limiter --> Queue["Bounded asyncio Queue"]
  Queue --> Workers["Async Worker Pool"]

  Workers --> Lake["Raw Signal Lake (JSON)"]
  Workers --> Truth["Source of Truth (Incidents + RCA JSON)"]
  Workers --> Agg["Timeseries Aggregations"]

  Truth --> Cache["Hot Cache (Dashboard State)"]
  Cache --> UI["React Dashboard"]

  Lake --> UI
  UI --> Workflow["State Machine + RCA Validation"]
  Workflow --> Truth
```

## Tech Stack

### Backend

- Python + FastAPI for async API endpoints.
- Pydantic for request and response validation.
- `asyncio.Queue` and worker tasks for asynchronous signal processing.

### Frontend

- React + Vite for the incident dashboard.
- `lucide-react` for interface icons.

### Storage Design

| Layer | Current implementation | Production equivalent |
| --- | --- | --- |
| Raw signal lake | JSON list store | S3 / OpenSearch |
| Source of truth | JSON list store | PostgreSQL |
| Hot dashboard cache | In-memory cache | Redis |
| Aggregations | In-memory counters | ClickHouse / Timescale |

The repository uses file-backed adapters to keep the assignment runnable with Docker Compose. The storage boundaries are separated so the JSON adapters can be replaced by PostgreSQL, Redis, S3/OpenSearch, or a time-series store.

## Key Features

### High-Throughput Ingestion

- `/signals` accepts individual failure signals.
- `/signals/bulk` accepts multiple signals in one request.
- Ingestion is async and returns `202 Accepted` after enqueueing the signal.
- Queue size is configurable with `QUEUE_MAX_SIZE`.

### Backpressure Handling

The backend writes accepted signals into a bounded `asyncio.Queue`. If persistence slows down and the queue fills up, the API returns `503` instead of exhausting memory or crashing. Clients can retry with backoff.

### Rate Limiting

A sliding-window rate limiter protects the ingestion API from cascading overload. The limit is configurable with `INGESTION_RATE_PER_MINUTE`.

### Debouncing Logic

Signals are grouped by `component_id` inside a 10-second window.

Example:

```text
100 signals for CACHE_CLUSTER_01 within 10 seconds -> 1 work item
```

All raw signals are retained in the raw signal lake, and every signal is linked to the generated work item.

### Concurrency Model

- FastAPI handles requests asynchronously.
- A bounded queue buffers accepted signals.
- Four async workers process signals concurrently.
- Per-component locks prevent race conditions while updating a work item for the same component.

### Retry Logic

JSON persistence writes use a small retry loop with incremental delay. This simulates the retry behavior expected when a real database write temporarily fails.

### Workflow Engine

The incident lifecycle is enforced through a state-machine style workflow.

```text
OPEN -> INVESTIGATING -> RESOLVED -> CLOSED
RESOLVED -> INVESTIGATING
```

Invalid state transitions are rejected.

### RCA Enforcement and MTTR

A work item cannot move to `CLOSED` unless a complete RCA exists. The RCA includes:

- Incident start and end time.
- Root cause category.
- Fix applied.
- Prevention steps.

MTTR is calculated automatically:

```text
MTTR = RCA incident_end - first_signal_time
```

### Alerting Strategy

The backend uses a strategy factory to classify different component failures:

- RDBMS failures -> P0 / database on-call channel.
- NoSQL, queue, and MCP host failures -> P1 / platform channel.
- Cache failures -> P2 / cache operations channel.
- API failures -> P3 / service owner channel.

### Observability

- `/health` reports service health and queue depth.
- Throughput metrics are printed every five seconds:
  - Signals/sec.
  - Queue depth.
- `/aggregations` exposes minute-level signal counts.

## Frontend Dashboard

The React dashboard provides:

- Live active incident feed sorted by severity.
- Severity totals.
- Signals/sec display.
- Incident detail view.
- Raw linked signal view.
- Status transition actions.
- RCA submission form with date-time inputs, category dropdown, and text areas.

## Run With Docker Compose

```bash
docker compose up --build
```

Open:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Replay Sample Failure

After the stack is running:

```bash
python sample-data/replay_failure.py --repeat 25
```

The sample data simulates:

- RDBMS outage.
- MCP host failure.
- Cache degradation.

## Local Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Local Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
pytest
```

The tests cover:

- Debouncing 100 signals into one work item.
- Rejecting closure without RCA.
- Allowing closure with complete RCA.
- Rejecting invalid state jumps.

## CI

GitHub Actions runs:

- Backend tests with `pytest`.
- Frontend production build with `npm run build`.

Workflow file:

```text
.github/workflows/ci.yml
```

## Assignment Requirement Mapping

| Requirement | Implementation |
| --- | --- |
| Single repository with `/backend` and `/frontend` | Present |
| High-throughput ingestion | Async FastAPI endpoints + bounded queue |
| 10,000 signals/sec burst handling concept | Queue, backpressure, worker pool, rate limiting |
| Debouncing | Component-based 10-second window |
| Raw signal storage | Raw signal JSON lake |
| Work item and RCA source of truth | Separate work item JSON store |
| Hot dashboard state | In-memory dashboard cache |
| Timeseries aggregations | Minute-level aggregation sink |
| Alerting strategy pattern | Component-based alerting strategy factory |
| Work item state pattern | State-machine workflow validation |
| Mandatory RCA | Closure blocked without complete RCA |
| MTTR calculation | Calculated from first signal to RCA end time |
| UI live feed | React dashboard |
| Incident detail and raw signals | React detail panel |
| RCA form | React RCA form |
| Rate limiting | Sliding-window limiter |
| Observability | `/health`, `/aggregations`, throughput logs |
| Retry logic | Persistence retry loop |
| Unit tests | Debounce and RCA workflow tests |
| Docker Compose setup | `docker-compose.yml` |
| Sample failure data | `sample-data/replay_failure.py` and JSON events |
| Prompts/spec/plans | `docs/IMPLEMENTATION_PLAN.md` |

## Future Improvements

- Replace JSON stores with PostgreSQL, Redis, S3/OpenSearch, and ClickHouse/Timescale.
- Add JWT authentication and role-based access.
- Integrate real alerting through email, SMS, Slack, or PagerDuty.
- Move from in-process queue to Kafka, RabbitMQ, or Redis Streams.
- Add load testing and service-level dashboards.

## Repository

GitHub: https://github.com/Avinashmorla/incident-management-system
