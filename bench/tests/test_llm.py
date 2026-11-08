import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bench.llm import MODEL_ALIAS, ModelClient, ModelConfig


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
@pytest.mark.parametrize("status", [200, 503])
def test_real_sdk_wire_format_tools_usage_and_no_retries(provider, status):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            assert self.headers["Authorization"] == "Bearer fake-key-never-live"
            response = (
                {
                    "id": "mock",
                    "object": "chat.completion",
                    "created": 1,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_mock",
                                        "type": "function",
                                        "function": {"name": "echo", "arguments": '{"value":"ok"}'},
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 4,
                        "total_tokens": 16,
                        "cost": 0.000002,
                    },
                }
                if status == 200
                else {"error": {"message": "mock unavailable", "type": "server_error"}}
            )
            encoded = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    model = (
        "openai/gpt-6-luna"
        if provider == "openai"
        else "openrouter/deepseek/deepseek-v4.1-flash-1017"
    )
    settings = ModelConfig(
        model,
        "FAKE_KEY",
        0.2,
        0.75,
        reasoning_effort="none",
        api_base=f"http://127.0.0.1:{server.server_port}/v1",
        openrouter_provider="relace/fp4" if provider == "openrouter" else None,
    )
    client = ModelClient(settings, "fake-key-never-live")
    request = client.prepare(
        {
            "model": MODEL_ALIAS,
            "messages": [{"role": "user", "content": "hi"}],
            "max_completion_tokens": 64,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        }
    )
    try:
        if status != 200:
            from litellm import ServiceUnavailableError

            with pytest.raises(ServiceUnavailableError):
                client.complete(request)
        else:
            result = client.complete(request)
            assert result["usage"]["prompt_tokens"] == 12
            assert result["usage"]["cost"] == 0.000002
            assert result["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "echo"
        assert len(seen) == 1  # Includes the underlying provider SDK's retry behaviour.
        assert seen[0]["model"] == model.split("/", 1)[1]
        assert seen[0].get("max_completion_tokens", seen[0].get("max_tokens")) == 64
        assert seen[0].get("reasoning_effort") == "none" or seen[0].get("reasoning") in (
            {"effort": "none"},
            {"enabled": False},
        )
        if provider == "openrouter":
            assert seen[0]["provider"]["only"] == ["relace/fp4"]
            assert seen[0]["provider"]["allow_fallbacks"] is False
            assert seen[0]["provider"]["max_price"] == {"prompt": 0.2, "completion": 0.75}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    "override",
    [
        {"api_base": "https://example.invalid"},
        {"api_key": "injected"},
        {"extra_body": {"provider": {"only": ["other"]}}},
        {"model": "other"},
        {"n": 2},
        {"max_tokens": 999},
    ],
)
def test_actor_cannot_override_provider_or_spending_controls(luna_config, override):
    client = ModelClient(luna_config, "fake")
    with pytest.raises(ValueError):
        client.prepare(
            {"model": MODEL_ALIAS, "messages": [], "max_completion_tokens": 64, **override}
        )


def test_explicit_rates_and_openrouter_provider_required(luna_config):
    with pytest.raises(ValueError):
        replace(luna_config, input_usd_per_million=float("nan"))
    with pytest.raises(ValueError):
        replace(luna_config, model="openrouter/deepseek/test")
