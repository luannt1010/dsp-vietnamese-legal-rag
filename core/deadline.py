"""Request-local time budget for synchronous pipeline components and adapters."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic


_deadline: ContextVar[float | None] = ContextVar("rag_deadline", default=None)


@contextmanager
def request_deadline(timeout_s: float) -> Iterator[None]:
    """Install a shared deadline; a nested scope cannot extend its parent."""
    deadline = monotonic() + timeout_s
    parent = _deadline.get()
    token = _deadline.set(min(parent, deadline) if parent is not None else deadline)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining_timeout(limit_s: float | None = None) -> float | None:
    """Bound an adapter's call/retry timeout by the request's remaining budget.

    Outside a pipeline, return the adapter's own limit. This does not interrupt
    a running call; the adapter must enforce the returned timeout in its client.
    """
    deadline = _deadline.get()
    if deadline is None:
        return limit_s
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("RAG request deadline exceeded")
    return min(limit_s, remaining) if limit_s is not None else remaining
