import json

import httpx
import pytest
from pydantic import SecretStr

from app.agents.config import Settings
from app.agents.contracts import ReconciliationAcknowledgement, ReportNarrative, SupervisorDecision
from app.agents.errors import AgentError, ModelOutputError, RequestBudgetExceeded
from app.agents.runner import MiMoRunner, RequestBudget

from .test_workflow import IDENTITY


def response(text):
    return httpx.Response(
        200,
        json={
            "id": "test-completion",
            "object": "chat.completion",
            "created": 1,
            "model": "mimo-v2.6-pro",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        },
    )


VALID = '{"next_action":"extract","explanation":"提取票据"}'


def make_runner(handler):
    return MiMoRunner(Settings(api_key=SecretStr("test-secret")), transport=httpx.MockTransport(handler))


async def test_framework_client_uses_configured_endpoint_and_json(backend):
    captured = []

    def handler(request):
        captured.append(request)
        return response(VALID)

    result = await make_runner(handler).generate(
        "supervisor", "检查", SupervisorDecision, RequestBudget(backend, IDENTITY)
    )
    assert result.next_action == "extract"
    assert str(captured[0].url) == "https://api.xiaomimimo.com/v1/chat/completions"
    assert captured[0].headers["api-key"] == "test-secret"
    assert json.loads(captured[0].content)["model"] == "mimo-v2.6-pro"
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] == 1
    assert "test-secret" not in repr(make_runner(handler).settings)


async def test_native_schema_fallback_is_counted(backend):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "response_format json_schema not supported",
                        "type": "invalid_request_error",
                    }
                },
            )
        assert "response_format" not in json.loads(request.content)
        return response(VALID)

    runner = make_runner(handler)
    await runner.generate("supervisor", "检查", SupervisorDecision, RequestBudget(backend, IDENTITY))
    assert count == 2
    assert runner.schema_supported is False


async def test_invalid_json_has_finite_corrections(backend):
    with pytest.raises(ModelOutputError):
        await make_runner(lambda _: response("not JSON")).generate(
            "supervisor",
            "检查",
            SupervisorDecision,
            RequestBudget(backend, IDENTITY),
        )
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] == 3


async def test_retry_cannot_escape_budget(backend):
    runner = make_runner(lambda _: httpx.Response(429, json={"error": {"message": "rate limited"}}))
    with pytest.raises(RequestBudgetExceeded):
        await runner.generate("supervisor", "检查", SupervisorDecision, RequestBudget(backend, IDENTITY, 1))
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] == 1


async def test_auth_failure_is_safe_and_not_retried(backend):
    runner = make_runner(
        lambda _: httpx.Response(401, json={"error": {"message": "test-secret unauthorized"}})
    )
    with pytest.raises(AgentError) as error:
        await runner.generate("supervisor", "检查", SupervisorDecision, RequestBudget(backend, IDENTITY))
    assert "test-secret" not in str(error.value)
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] == 1


def test_report_prose_cannot_invent_numeric_facts():
    with pytest.raises(ValueError):
        ReportNarrative(summary="本次已核实 999 元", next_steps=[], evidence_notes=[])


@pytest.mark.parametrize("preface", [None, "我先读取后台核对依据。"])
async def test_required_tool_executes_and_then_allows_final_output(backend, preface):
    requests = []
    called = []

    async def reconcile_transactions() -> str:
        """Return the backend reconciliation result."""
        called.append(True)
        return '{"matched_count":4}'

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            assert payload["tool_choice"] == "required"
            return httpx.Response(
                200,
                json={
                    "id": "tool-response",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "mimo-v2.6-pro",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": preface,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {"name": "reconcile_transactions", "arguments": "{}"},
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                },
            )
        assert payload.get("tool_choice") != "required"
        return response('{"summary":"已调用后端核对工具"}')

    result = await make_runner(handler).generate(
        "reconciliation",
        "核对",
        ReconciliationAcknowledgement,
        RequestBudget(backend, IDENTITY),
        tools=[reconcile_transactions],
    )
    assert result.summary
    assert called == [True]
    assert len(requests) == 2
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] == 2


async def test_timeouts_retry_twice_then_fail(backend, monkeypatch):
    async def no_wait(_seconds):
        pass

    monkeypatch.setattr("app.agents.runner.asyncio.sleep", no_wait)

    def timeout(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(AgentError):
        await make_runner(timeout).generate(
            "supervisor", "检查", SupervisorDecision, RequestBudget(backend, IDENTITY)
        )
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] == 3


async def test_http_deadline_bounds_streaming_body():
    import asyncio

    from app.agents.runner import LimitedTransport

    class StalledBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"partial response"
            await asyncio.Event().wait()

    inner = httpx.MockTransport(lambda request: httpx.Response(200, stream=StalledBody()))
    transport = LimitedTransport(inner, timeout_seconds=0.01)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.ReadTimeout, match="wall-clock"):
            await client.get("https://example.invalid/completion")


async def test_intake_tool_turn_can_continue_without_claiming_final_completion(backend):
    from app.intake.contracts import PrecheckNarrative

    calls = []

    async def read_material() -> str:
        """Read one test material and return a real tool receipt."""
        calls.append(True)
        return '{"rows":1}'

    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            result = response(None).json()
            result["choices"][0]["message"]["tool_calls"] = [
                {"id": "read-1", "type": "function", "function": {"name": "read_material", "arguments": "{}"}}
            ]
            result["choices"][0]["finish_reason"] = "tool_calls"
            return httpx.Response(200, json=result)
        return response("已读取一份材料，接下来继续剩余待办。")

    result = await make_runner(handler).generate(
        "customer_service",
        "读取后继续待办",
        PrecheckNarrative,
        RequestBudget(backend, IDENTITY),
        tools=[read_material],
    )
    assert calls == [True]
    assert result.summary == "工具回合已结束，继续未完成待办。"
    assert len(requests) == 2
