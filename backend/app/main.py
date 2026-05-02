from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models.schemas import (
    DashboardState,
    IngestionAccepted,
    RCAIn,
    SignalIn,
    SignalRecord,
    TransitionRequest,
    WorkItem,
)
from app.services.incident_engine import IncidentEngine, IncidentNotFoundError, IngestionBackpressureError
from app.services.rate_limiter import SlidingWindowRateLimiter
from app.services.workflow import WorkflowError
from app.storage.repositories import AggregationSink, DashboardCache, RawSignalLake, WorkItemRepository


data_dir = Path(settings.data_dir)
engine = IncidentEngine(
    raw_signal_lake=RawSignalLake(data_dir),
    work_items=WorkItemRepository(data_dir),
    dashboard_cache=DashboardCache(),
    aggregations=AggregationSink(),
)
rate_limiter = SlidingWindowRateLimiter(settings.ingestion_rate_per_minute)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.start()
    yield
    await engine.stop()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "queue_depth": engine.queue.qsize()}


@app.post("/signals", response_model=IngestionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def ingest_signal(signal: SignalIn, request: Request):
    client = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Ingestion rate limit exceeded")
    try:
        await engine.submit(signal)
    except IngestionBackpressureError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return IngestionAccepted(accepted=1, queued=engine.queue.qsize())


@app.post("/signals/bulk", response_model=IngestionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def ingest_bulk(signals: list[SignalIn], request: Request):
    client = request.client.host if request.client else "unknown"
    accepted = 0
    for signal in signals:
        if not rate_limiter.allow(client):
            return IngestionAccepted(accepted=accepted, queued=engine.queue.qsize(), rejected=len(signals) - accepted)
        try:
            await engine.submit(signal)
            accepted += 1
        except IngestionBackpressureError:
            return IngestionAccepted(accepted=accepted, queued=engine.queue.qsize(), rejected=len(signals) - accepted)
    return IngestionAccepted(accepted=accepted, queued=engine.queue.qsize())


@app.get("/dashboard", response_model=DashboardState)
async def dashboard():
    return await engine.dashboard()


@app.get("/work-items", response_model=list[WorkItem])
async def work_items():
    return await engine.list_work_items()


@app.get("/work-items/{item_id}")
async def work_item_detail(item_id: str):
    try:
        item, signals = await engine.detail(item_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Work item not found") from exc
    return {"work_item": item, "signals": signals}


@app.patch("/work-items/{item_id}/status", response_model=WorkItem)
async def transition(item_id: str, request: TransitionRequest):
    try:
        return await engine.transition(item_id, request.status)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Work item not found") from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/work-items/{item_id}/rca", response_model=WorkItem)
async def submit_rca(item_id: str, rca: RCAIn):
    try:
        return await engine.submit_rca(item_id, rca)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Work item not found") from exc


@app.get("/aggregations")
async def aggregations():
    return engine.aggregations.snapshot()
