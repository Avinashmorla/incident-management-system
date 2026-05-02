# Implementation Plan

## Scope

Build a repository with `backend` and `frontend` folders for a mission-critical Incident Management System assignment.

## Backend

- FastAPI async API for ingestion, dashboard, incident detail, state transitions, RCA, health, and aggregations.
- Bounded in-memory `asyncio.Queue` to absorb bursts and apply backpressure when persistence is slower than ingestion.
- Four async workers process queued signals.
- Debounce by component ID inside a ten-second window so repeated signals link to one work item.
- Strategy pattern for alerting severity/channel selection.
- State pattern via a state machine for `OPEN -> INVESTIGATING -> RESOLVED -> CLOSED`.
- RCA validation prevents closure without complete root-cause details.

## Frontend

- React dashboard with severity metrics, live active incident feed, incident detail, raw signals, status actions, and RCA form.
- Polls the dashboard endpoint every three seconds for a simple live-feed behavior.

## Persistence Simulation

- Raw signal lake: `data/raw_signals.json`.
- Source of truth: `data/work_items.json`.
- Hot dashboard cache: in-memory `DashboardCache`.
- Aggregations: in-memory minute buckets exposed by `/aggregations`.

## Verification

- Unit tests cover RCA validation and debounce behavior.
- Sample replay script simulates an RDBMS outage followed by MCP and cache failures.
