import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter

T = TypeVar("T", bound=BaseModel)


class JsonListStore:
    def __init__(self, path: Path, adapter: TypeAdapter[list[T]]) -> None:
        self.path = path
        self.adapter = adapter
        self._lock = asyncio.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def load(self) -> list[T]:
        async with self._lock:
            return self._load_unlocked()

    async def append(self, item: T) -> None:
        async with self._lock:
            items = self._load_unlocked()
            items.append(item)
            await self._write_with_retry(items)

    async def update_all(self, mutator: Callable[[list[T]], list[T]]) -> list[T]:
        async with self._lock:
            items = mutator(self._load_unlocked())
            await self._write_with_retry(items)
            return items

    def _load_unlocked(self) -> list[T]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return self.adapter.validate_python(raw)

    async def _write_with_retry(self, items: list[T], attempts: int = 3) -> None:
        last_error: OSError | None = None
        for attempt in range(attempts):
            try:
                payload = [json.loads(item.model_dump_json()) for item in items]
                self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                return
            except OSError as exc:
                last_error = exc
                await asyncio.sleep(0.05 * (attempt + 1))
        if last_error:
            raise last_error
