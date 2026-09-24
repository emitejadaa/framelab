"""The compute lane: one worker thread per session, jobs run in submission order."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any


class ComputeLane:
    def __init__(self, name: str = "framelab-compute") -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)

    def submit(self, fn: Callable[..., Any], *args: Any) -> Future:
        return self._pool.submit(fn, *args)

    def shutdown(self, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=True)
