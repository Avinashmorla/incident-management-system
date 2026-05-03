import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.schemas import ComponentType, SignalIn, SignalRecord
from app.services.incident_engine import IncidentEngine
from app.storage.repositories import AggregationSink, DashboardCache, RawSignalLake, WorkItemRepository


def test_debounces_signals_for_same_component():
    data_dir = Path(".test-runtime") / str(uuid4())
    data_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(_run_debounce_case(data_dir))


async def _run_debounce_case(data_dir):
    engine = IncidentEngine(
        raw_signal_lake=RawSignalLake(data_dir),
        work_items=WorkItemRepository(data_dir),
        dashboard_cache=DashboardCache(),
        aggregations=AggregationSink(),
        queue_size=10,
    )
    observed_at = datetime.now(timezone.utc)

    for index in range(100):
        await engine._process(
            SignalRecord(
                component_id="CACHE_CLUSTER_01",
                component_type=ComponentType.CACHE,
                message=f"Cache timeout {index}",
                observed_at=observed_at,
                error_code="CACHE_TIMEOUT",
            )
        )

    items = await engine.list_work_items()
    item, signals = await engine.detail(items[0].id)

    assert len(items) == 1
    assert item.signal_count == 100
    assert len(signals) == 100
