"""Inference admission must reflect actual workers, including cancellation."""

from threading import Event, Lock

import anyio
import pytest

from core.config import Settings
from src.api.schemas.questions import QuestionRequest
from src.api.services.rag_service import RAGService, ServiceBusyError


@pytest.mark.anyio
async def test_cancelled_caller_keeps_slot_until_synchronous_worker_finishes(runtime, settings):
    entered, release = Event(), Event()
    finished = anyio.Event()
    scopes = []
    result = runtime.pipeline.run_with_trace.return_value

    def blocking_pipeline(question):
        entered.set()
        assert release.wait(10)
        return result

    runtime.pipeline.run_with_trace.side_effect = blocking_pipeline
    service = RAGService(runtime, settings)
    question = QuestionRequest(query="Câu hỏi")

    async def first_caller():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            await service.ask(question, request_id="first")
        finished.set()

    with anyio.fail_after(10):
        async with anyio.create_task_group() as group:
            group.start_soon(first_caller)
            try:
                assert await anyio.to_thread.run_sync(entered.wait, 5)
                scopes[0].cancel()
                await anyio.sleep(0)
                with pytest.raises(ServiceBusyError):
                    await service.ask(question, request_id="second")
                assert runtime.pipeline.run_with_trace.call_count == 1
            finally:
                release.set()
            await finished.wait()
        assert (await service.ask(question, request_id="after-finish")).status == "completed"


@pytest.mark.anyio
async def test_configured_capacity_allows_two_workers_and_rejects_third(runtime, settings):
    data = settings.model_dump()
    data["api"]["max_concurrent_requests"] = 2
    service = RAGService(runtime, Settings.model_validate(data))
    entered, release, lock = Event(), Event(), Lock()
    count = 0
    results = []
    result = runtime.pipeline.run_with_trace.return_value

    def blocking_pipeline(question):
        nonlocal count
        with lock:
            count += 1
            if count == 2:
                entered.set()
        assert release.wait(10)
        return result

    runtime.pipeline.run_with_trace.side_effect = blocking_pipeline

    async def ask(index):
        response = await service.ask(QuestionRequest(query=f"Câu hỏi {index}"), request_id=str(index))
        results.append(response)

    with anyio.fail_after(10):
        async with anyio.create_task_group() as group:
            group.start_soon(ask, 1)
            group.start_soon(ask, 2)
            try:
                assert await anyio.to_thread.run_sync(entered.wait, 5)
                with pytest.raises(ServiceBusyError):
                    await ask(3)
            finally:
                release.set()
        assert sorted(response.request_id for response in results) == ["1", "2"]
