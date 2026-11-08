"""LiteLLM SDK integration; provider credentials stay in this host process."""

import math
import os
import re
from dataclasses import asdict, dataclass

MODEL_ALIAS = "swarmfs-bench"
CHAT_FIELDS = {
    "messages",
    "tools",
    "tool_choice",
    "temperature",
    "top_p",
    "stop",
    "seed",
    "parallel_tool_calls",
    "response_format",
    "frequency_penalty",
    "presence_penalty",
}
CLIENT_FIELDS = CHAT_FIELDS | {
    "model",
    "stream",
    "max_tokens",
    "max_completion_tokens",
    "max_output_tokens",
    "reasoning_effort",
    "n",
}


@dataclass(frozen=True)
class ModelConfig:
    model: str
    api_key_env: str
    input_usd_per_million: float
    output_usd_per_million: float
    reasoning_effort: str | None = None
    api_base: str | None = None
    openrouter_provider: str | None = None

    def __post_init__(self):
        if "/" not in self.model or not self.model.strip():
            raise ValueError("model must include a LiteLLM provider prefix")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.api_key_env):
            raise ValueError("api_key_env must name an environment variable")
        for rate in (self.input_usd_per_million, self.output_usd_per_million):
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError("explicit positive finite spending rates required")
        if self.model.startswith("openrouter/") and not self.openrouter_provider:
            raise ValueError("pin openrouter_provider for reproducible benchmark runs")

    def manifest(self):
        return asdict(self)


class ModelClient:
    def __init__(self, config: ModelConfig, key: str, *, completion=None):
        self.config, self.key = config, key
        self._completion = completion

    def prepare(self, payload: dict) -> dict:
        if payload.get("model", "").removeprefix("openai/") != MODEL_ALIAS:
            raise ValueError("only the configured benchmark model is permitted")
        if payload.get("stream") or payload.get("n", 1) != 1:
            raise ValueError("one non-streaming generation per reservation required")
        if set(payload) - CLIENT_FIELDS:
            raise ValueError("unsupported client fields; routing is controlled by the host")
        limits = [
            payload[k]
            for k in ("max_tokens", "max_completion_tokens", "max_output_tokens")
            if k in payload
        ]
        if not limits or any(limit != limits[0] for limit in limits):
            raise ValueError("one consistent output limit required")
        request = {k: payload[k] for k in CHAT_FIELDS if k in payload}
        request.update(
            model=self.config.model,
            max_tokens=limits[0],
            stream=False,
        )
        if self.config.reasoning_effort is not None:
            request["reasoning_effort"] = self.config.reasoning_effort
        if self.config.openrouter_provider:
            request["extra_body"] = {
                "provider": {
                    "only": [self.config.openrouter_provider],
                    "allow_fallbacks": False,
                    "require_parameters": True,
                    "max_price": {
                        "prompt": self.config.input_usd_per_million,
                        "completion": self.config.output_usd_per_million,
                    },
                }
            }
        return request

    def complete(self, request: dict) -> dict:
        if self._completion is None:
            os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
            import litellm

            litellm.telemetry = False
            litellm.suppress_debug_info = True
            self._completion = litellm.completion
        response = self._completion(
            **request,
            api_key=self.key,
            api_base=self.config.api_base,
            num_retries=0,
            max_retries=0,
            timeout=180,
            drop_params=False,
        )
        return response.model_dump(mode="json", exclude_none=True)
