import asyncio
from datetime import datetime, timezone

from app.core.config import settings
from app.models.schemas import RCAIn, RCARecord, SignalIn, SignalRecord, WorkItem, WorkItemState
from app.services.alerting import AlertingStrategyFactory
from app.services.workflow import WorkItemStateMachine
from app.storage.repositories import AggregationSink, DashboardCache, RawSignalLake, WorkItemRepository


class IngestionBackpressureError(RuntimeError):
    pass


class IncidentNotFoundError(LookupError):
    pass


class IncidentEngine:
    def __init__(
        self,
        raw_signal_lake: RawSignalLake,
        work_items: WorkItemRepository,
        dashboard_cache: DashboardCache,
        aggregations: AggregationSink,
        queue_size: int = settings.queue_max_size,
    ) -> None:
        self.raw_signal_lake = raw_signal_lake
        self.work_items = work_items
        self.dashboard_cache = dashboard_cache
        self.aggregations = aggregations
        self.queue: asyncio.Queue[SignalRecord] = asyncio.Queue(maxsize=queue_size)
        self.alerting = AlertingStrategyFactory()
        self.workflow = WorkItemStateMachine()
        self._workers: list[asyncio.Task] = []
        self._metrics_task: asyncio.Task | None = None
        self._processed_since_tick = 0
        self._component_locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        self._workers = [asyncio.create_task(self._worker(index)) for index in range(4)]
        self._metrics_task = asyncio.create_task(self._metrics_loop())

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        if self._metrics_task:
            self._metrics_task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        if self._metrics_task:
            await asyncio.gather(self._metrics_task, return_exceptions=True)

    async def submit(self, signal: SignalIn) -> SignalRecord:
        record = SignalRecord(**signal.model_dump())
        try:
            self.queue.put_nowait(record)
        except asyncio.QueueFull as exc:
            raise IngestionBackpressureError("Ingestion queue is full; retry with backoff") from exc
        return record

    async def _worker(self, index: int) -> None:
        while True:
            signal = await self.queue.get()
            try:
                await self._process(signal)
                self._processed_since_tick += 1
            finally:
                self.queue.task_done()

    async def _process(self, signal: SignalRecord) -> None:
        lock = self._component_locks.setdefault(signal.component_id, asyncio.Lock())
        async with lock:
            item = await self._find_debounce_candidate(signal)
            if item is None:
                severity, channel = self.alerting.for_component(signal.component_type).classify(signal.component_id)
                item = WorkItem(
                    component_id=signal.component_id,
                    component_type=signal.component_type,
                    severity=severity,
                    first_signal_at=signal.observed_at,
                    last_signal_at=signal.observed_at,
                    signal_count=0,
                    alert_channel=channel,
                )

            signal.work_item_id = item.id
            item.signal_ids.append(signal.id)
            item.signal_count += 1
            item.last_signal_at = max(item.last_signal_at, signal.observed_at)
            await self.raw_signal_lake.append(signal)
            await self.work_items.upsert(item)
            self.aggregations.record(signal.observed_at)

    async def _find_debounce_candidate(self, signal: SignalRecord) -> WorkItem | None:
        items = await self.work_items.list()
        for item in sorted(items, key=lambda candidate: candidate.created_at, reverse=True):
            age = (signal.observed_at - item.first_signal_at).total_seconds()
            if (
                item.component_id == signal.component_id
                and item.status != WorkItemState.CLOSED
                and 0 <= age <= settings.debounce_window_seconds
            ):
                return item
        return None

    async def dashboard(self):
        return await self.dashboard_cache.build(await self.work_items.list())

    async def list_work_items(self) -> list[WorkItem]:
        return await self.work_items.list()

    async def detail(self, item_id: str) -> tuple[WorkItem, list[SignalRecord]]:
        item = await self.work_items.get(item_id)
        if item is None:
            raise IncidentNotFoundError(item_id)
        return item, await self.raw_signal_lake.by_work_item(item_id)

    async def transition(self, item_id: str, status: WorkItemState) -> WorkItem:
        item = await self.work_items.get(item_id)
        if item is None:
            raise IncidentNotFoundError(item_id)
        updated = self.workflow.transition(item, status)
        return await self.work_items.upsert(updated)

    async def submit_rca(self, item_id: str, rca: RCAIn) -> WorkItem:
        item = await self.work_items.get(item_id)
        if item is None:
            raise IncidentNotFoundError(item_id)
        mttr = (rca.incident_end - item.first_signal_at).total_seconds()
        record = RCARecord(**rca.model_dump(), mttr_seconds=max(mttr, 0))
        item.rca = record
        if item.status == WorkItemState.RESOLVED:
            item = self.workflow.transition(item, WorkItemState.CLOSED, record)
        return await self.work_items.upsert(item)

    async def _metrics_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            throughput = self._processed_since_tick / 5
            self.dashboard_cache.set_throughput(throughput)
            print(
                f"[ims] throughput={throughput:.2f} signals/sec queue_depth={self.queue.qsize()} "
                f"timestamp={datetime.now(timezone.utc).isoformat()}",
                flush=True,
            )
            self._processed_since_tick = 0
