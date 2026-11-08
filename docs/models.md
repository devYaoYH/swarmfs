# Model providers through LiteLLM SDK

SwarmFS uses `litellm.completion()` inside the existing host process. No LiteLLM
server, proxy deployment or container is needed. Docker is used for CooperBench
environments; the model smoke check runs without it.

Install benchmark dependencies with `uv sync --group benchmark`. Keys belong in
the ignored root `.env`; the profile names the key's environment variable.

| Profile | LiteLLM model | Key variable | Per-agent limit |
| --- | --- | --- | --- |
| `pilot.toml` | `openai/gpt-6-luna` | `OPENAI_API_KEY` | $0.20 |
| `bench/configs/openrouter.toml` | `openrouter/deepseek/deepseek-v4.1-flash-1017` | `OPENROUTER_API_KEY` | $0.05 |

## Use OpenRouter

```sh
uv run swarm-trails smoke --config bench/configs/openrouter.toml
```

`smoke` checks a function call and its follow-up response in two small paid calls.
It uses the shared ledger and a one-cent allowance per invocation. It writes a
sanitized result under `artifacts/pilot/smoke-*.json` and starts no Docker services.
The [checked SDK round trip](results/openrouter-sdk-smoke-2026-11-08.json) used
334 input and 39 output tokens, with a reported cost of $0.000021504. This checks
provider compatibility, separately from CooperBench completion results.

To run the same model on CooperBench after [task setup](benchmark.md):

```sh
uv run swarm-trails prepare --config bench/configs/openrouter.toml
uv run swarm-trails verify --config bench/configs/openrouter.toml
uv run swarm-trails pilot --config bench/configs/openrouter.toml
uv run swarm-trails report --config bench/configs/openrouter.toml
```

The OpenRouter profile pins the October 17 model snapshot and Relace's `fp4`
endpoint. This is a quantized, low-cost route, distinct from DeepSeek's first-party
endpoint. The observed listing on 2026-11-08 was $0.006/M input and $0.50/M output;
those are also the request price ceilings. If that route is unavailable or exceeds
the ceiling, the request fails rather than falling back to another endpoint.
[Live model/provider catalog](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash-1017/endpoints).
During setup, this route rejected explicit `tool_choice="none"`. The smoke check
uses automatic tool selection, then omits tools for the final response.

## Configure another model

Copy a TOML profile, choose a fresh `experiment_id`, then edit its `[llm]` table:

```toml
[llm]
model = "openrouter/deepseek/deepseek-v4.1-flash-1017"
api_key_env = "OPENROUTER_API_KEY"
reasoning_effort = "none"
openrouter_provider = "relace/fp4"
input_usd_per_million = 0.006
output_usd_per_million = 0.50
```

Use LiteLLM's provider-prefixed model names. `api_base` is optional for custom
endpoints. Omit `reasoning_effort` when the provider should use its default;
unsupported explicit parameters fail instead of being silently dropped. The agent
interface uses Chat Completions with function tools and non-streaming responses.

For OpenRouter, a provider pin is required. To select the first-party endpoint,
use `openrouter_provider = "deepseek"` and suitable price ceilings; the current
catalog includes time-dependent rates up to $0.30/M input and $1.20/M output.
Hold model, provider, reasoning and limits constant across both experiment arms.

LiteLLM owns request/response translation. SwarmFS retains the atomic spending
reservations, explicit pricing ceilings and trail injection. SDK pricing estimates
are not used to authorize spending. SDK retries and provider fallbacks are disabled;
unknown outcomes retain their reservation. The shared $4 ledger remains cumulative
across profiles, including earlier OpenAI calls. Provider-reported costs, where
available, are separate fields in the ledger snapshot and report JSON.

[LiteLLM SDK provider documentation](https://docs.litellm.ai/docs/providers/openrouter).
