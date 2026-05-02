from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter

from app.models.schemas import DashboardState, SignalRecord, WorkItem, WorkItemState
from app.storage.json_store import JsonListStore


class RawSignalLake:
    def __init__(self, data_dir: Path) -> None:
        self.store = JsonListStore(data_dir / "raw_signals.json", TypeAdapter(list[SignalRecord]))

    async def append(self, signal: SignalRecord) -> None:
        await self.store.append(signal)

    async def by_work_item(self, work_item_id: str) -> list[SignalRecord]:
        return [signal for signal in await self.store.load() if signal.work_item_id == work_item_id]


class WorkItemRepository:
    def __init__(self, data_dir: Path) -> None:
        self.store = JsonListStore(data_dir / "work_items.json", TypeAdapter(list[WorkItem]))

    async def list(self) -> list[WorkItem]:
        return await self.store.load()

    async def get(self, item_id: str) -> WorkItem | None:
        return next((item for item in await self.store.load() if item.id == item_id), None)

    async def upsert(self, item: WorkItem) -> WorkItem:
        item.updated_at = datetime.now(timezone.utc)

        def mutate(items: list[WorkItem]) -> list[WorkItem]:
            for index, existing in enumerate(items):
                if existing.id == item.id:
                    items[index] = item
                    return items
            items.append(item)
            return items

        await self.store.update_all(mutate)
        return item


class DashboardCache:
    def __init__(self) -> None:
        self._signals_per_second = 0.0

    def set_throughput(self, value: float) -> None:
        self._signals_per_second = value

    async def build(self, items: list[WorkItem]) -> DashboardState:
        active = [item for item in items if item.status != WorkItemState.CLOSED]
        severity_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        active.sort(key=lambda item: (severity_rank[item.severity.value], item.first_signal_at))
        totals = Counter(item.severity.value for item in active)
        return DashboardState(
            active=active,
            totals_by_severity=dict(totals),
            signals_per_second=self._signals_per_second,
        )


class AggregationSink:
    def __init__(self) -> None:
        self._by_minute: dict[str, int] = defaultdict(int)

    def record(self, observed_at: datetime) -> None:
        minute = observed_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        self._by_minute[minute] += 1

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self._by_minute.items()))
