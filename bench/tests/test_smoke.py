from types import SimpleNamespace

from bench.llm import ModelClient
from bench.smoke import smoke


def test_smoke_roundtrip_accounts_for_both_calls_without_docker(tmp_path, monkeypatch, luna_config):
    from bench import smoke as module

    seen = []

    def complete(**request):
        seen.append(request)
        if len(seen) == 1:
            assert request["tool_choice"] == "auto"
            message = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_echo",
                        "type": "function",
                        "function": {"name": "echo", "arguments": '{"value":"ok"}'},
                    }
                ],
            }
        else:
            assert "tools" not in request and "tool_choice" not in request
            assert request["messages"][-1]["tool_call_id"] == "call_echo"
            message = {"role": "assistant", "content": "ok"}
        response = {
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "cost": 0.000001},
        }
        return SimpleNamespace(model_dump=lambda **_: response)

    monkeypatch.setattr(module, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        module, "model_client", lambda _: ModelClient(luna_config, "fake-key", completion=complete)
    )
    result = smoke({"budget_usd": 0.01, "per_agent_budget_usd": 0.01})
    assert len(seen) == 2
    assert result["tool_roundtrip"]
    assert result["usage"]["requests"] == 2
    assert result["usage"]["provider_reported_usd"] == 0.000002
    assert result["usage"]["unsettled_requests"] == 0
