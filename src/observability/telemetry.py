"""Monotonic timing without global mutable request state or model payload logging."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from math import isfinite
from time import perf_counter


_recorder = ContextVar("telemetry_recorder", default=None)
_labels = ContextVar("telemetry_labels", default={})


@contextmanager
def capture():
    events = []
    recorder_token = _recorder.set(events)
    labels_token = _labels.set({})
    try:
        yield events
    finally:
        _labels.reset(labels_token)
        _recorder.reset(recorder_token)


def set_round(index: int) -> None:
    if _recorder.get() is not None:
        _labels.set({**_labels.get(), "round_index": index})


@contextmanager
def span(name: str, *, kind: str = "stage", **labels):
    events = _recorder.get()
    if events is None:
        yield {}
        return
    fields = {**_labels.get(), **{key: value for key, value in labels.items() if value is not None}}
    token = _labels.set(fields)
    event = {"name": name, "kind": kind, **fields, "status": "completed"}
    started = perf_counter()
    try:
        yield event
    except BaseException as exc:
        event.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        event["duration_ms"] = (perf_counter() - started) * 1000
        events.append(event)
        _labels.reset(token)


def instrument(name: str, *, kind: str = "stage", role: str | None = None,
               role_from: str | None = None, model_from: str | None = None):
    def decorate(function):
        @wraps(function)
        def measured(self, *args, **kwargs):
            with span(name, kind=kind, role=getattr(self, role_from) if role_from else role,
                      model=getattr(self, model_from) if model_from else None):
                return function(self, *args, **kwargs)
        return measured
    return decorate


def backend_usage(result: dict) -> dict:
    """Ollama durations are nanoseconds; absent/invalid values remain absent."""
    usage = {}
    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        value = result.get(key)
        if type(value) in (int, float) and isfinite(value) and value >= 0:
            usage[key + "_ms"] = value / 1_000_000
    for key in ("prompt_eval_count", "eval_count"):
        value = result.get(key)
        if type(value) is int and value >= 0:
            usage[key] = value
    duration = usage.get("eval_duration_ms", 0)
    if duration > 0 and "eval_count" in usage:
        usage["decode_tokens_per_second"] = usage["eval_count"] * 1000 / duration
    return usage
