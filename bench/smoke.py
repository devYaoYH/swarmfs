"""Two tiny paid SDK calls to check function calling, without Docker or a benchmark."""

import json
import uuid

from bench.budget import Budget
from bench.llm import MODEL_ALIAS
from bench.pilot import ARTIFACTS, model_client


def smoke(cfg):
    client = model_client(cfg)
    directory = ARTIFACTS / "pilot"
    directory.mkdir(parents=True, exist_ok=True)
    budget = Budget(
        str(directory / "budget.db"),
        model=client.config.model,
        input_usd_per_million=client.config.input_usd_per_million,
        output_usd_per_million=client.config.output_usd_per_million,
        total=cfg["budget_usd"],
        per_agent=min(0.01, cfg["per_agent_budget_usd"]),
    )
    actor = "smoke-" + uuid.uuid4().hex
    tools = [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo a value",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]
    messages = [{"role": "user", "content": "Call echo with value ok, then reply ok."}]

    def call(choice=None):
        body = {
            "model": MODEL_ALIAS,
            "messages": messages,
            "max_tokens": 128,
        }
        if choice is not None:
            body.update(tools=tools, tool_choice=choice)
        payload = client.prepare(body)
        identity = budget.reserve(actor, payload)
        try:
            response = client.complete(payload)
        except Exception as exc:
            message = str(exc).replace(client.key, "[redacted]")[:500]
            (directory / f"{actor}.json").write_text(
                json.dumps(
                    {
                        "model": client.config.model,
                        "error": message,
                        "usage": next(
                            a for a in budget.snapshot()["agents"] if a["actor"] == actor
                        ),
                    },
                    indent=2,
                )
            )
            raise RuntimeError(
                f"SDK smoke request failed ({type(exc).__name__}): {message}; "
                "spending reservation retained"
            ) from None
        budget.settle(identity, response)
        return response["choices"][0]["message"]

    first = call("auto")
    calls = first.get("tool_calls", [])
    if len(calls) != 1 or calls[0]["function"]["name"] != "echo":
        raise RuntimeError("model did not return the requested function call")
    if json.loads(calls[0]["function"]["arguments"]) != {"value": "ok"}:
        raise RuntimeError("model returned unexpected function arguments")
    messages.extend(
        [
            {"role": "assistant", "content": first.get("content"), "tool_calls": calls},
            {"role": "tool", "tool_call_id": calls[0]["id"], "content": "ok"},
        ]
    )
    final = call()
    if not final.get("content") or final.get("tool_calls"):
        raise RuntimeError("model did not complete the function-call round trip")
    usage = next(a for a in budget.snapshot()["agents"] if a["actor"] == actor)
    result = {
        "model": client.config.model,
        "provider": client.config.openrouter_provider,
        "tool_roundtrip": True,
        "usage": usage,
    }
    (directory / f"{actor}.json").write_text(json.dumps(result, indent=2))
    return result
