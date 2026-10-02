"""Run blocking capture calls without depending on cross-thread event-loop wakeups."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from threading import Thread
from typing import Any, Callable, TypeVar

T = TypeVar("T")


async def run_blocking(fn: Callable[..., T], /, **kwargs: Any) -> T:
    result: Future[T] = Future()

    def worker() -> None:
        try:
            result.set_result(fn(**kwargs))
        except Exception as exc:
            result.set_exception(exc)

    Thread(target=worker, name="smartcopy-capture-io", daemon=True).start()
    # A short timer also works where thread-to-loop self-pipe wakeups are unavailable.
    while not result.done():
        await asyncio.sleep(0.05)
    return result.result()
