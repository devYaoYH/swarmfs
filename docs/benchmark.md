# Local CooperBench pilot

Run these commands from the repository root. Python packages use `uv`; Docker
Compose provides the benchmark environments and their pinned OpenHands SDK.
Fetch the public adapter and dataset once:

```sh
mkdir -p .cache/upstream
git clone https://github.com/harbor-framework/harbor.git .cache/upstream/harbor
git -C .cache/upstream/harbor checkout 9c7a39b991d7e2205019f6be0598cbd22d84bfc3
git clone https://github.com/cooperbench/CooperBench.git .cache/upstream/CooperBench
git -C .cache/upstream/CooperBench checkout 63b9d44d9f39a02fccf5bf0052db48a917a011fd
uv sync --group benchmark
```

Revisions and the task-image digest are recorded in [`pilot.toml`](../pilot.toml).
Docker must be running with the Compose plugin available. The pinned image uses
`linux/amd64`; an ARM host needs amd64 emulation enabled.

For paid runs, add the selected key to the ignored root `.env`, using
[`.env.example`](../.env.example) as a template. Keep an existing `.env` intact.
The default profile uses `OPENAI_API_KEY`; the OpenRouter profile uses
`OPENROUTER_API_KEY`. See [model configuration](models.md).

```sh
uv run swarm-trails prepare
uv run swarm-trails verify
uv run swarm-trails pilot
uv run swarm-trails report
```

Completed attempts are resumed by `experiment_id`; change that value for a fresh
experiment. The shared spending ledger remains cumulative across experiment IDs.
The runner freezes configuration, the LiteLLM version and the trail protocol,
refusing changed settings
under an existing ID. `prepare` writes generated task files,
`verify` writes `artifacts/validation.json`, and `pilot` writes its per-attempt
records, logs and trail database under `artifacts/pilot/<experiment_id>/`.
`report` produces `summary.json` and `report.md` there. The shared cost ledger is
`artifacts/pilot/budget.db`. Original pilot artifacts predate this per-experiment
layout and remain at `artifacts/pilot/`. Raw local artifacts are not included in Git.

Published pilot: [results](results/pilot-2026-11-08.md) and
[machine-readable summary with pinned inputs](results/pilot-2026-11-08.json).

`verify` uses Docker, without a model: the combined reference must pass both feature
checks and untouched source must fail. `pilot` refuses to run without those results.
The pilot executes generated Harbor task sidecars directly with local Docker Compose,
instead of requiring a Modal account or the Harbor orchestration package. It retains
the pinned Harbor verifier, including its ordinary/union Git merge policy, in
the default isolated mode. The optional [shared-workspace mode](shared-workspace.md)
evaluates one final source snapshot with the same feature runners instead.

The default Luna profile uses two Jinja feature pairs, one repetition and two arms:
capture-only baseline versus visible decaying trails. Messaging, prompts, model,
tools, initial source and verifier are held constant. Each pair gets an isolated
trail namespace and two separate workspaces. This is one task family, not a held-out
evaluation. Both instructions already name a target file, limiting navigation claims.
Both arms now use an intent-aware file tool with a required short note. The published
Luna results used the earlier observation-only protocol. Current profiles use fresh
`intent-…-v1` experiment IDs; the expanded DeepSeek run uses its own manifest and result directory.
The [expanded DeepSeek results](results/deepseek-pilot-2026-11-09.md) cover five pairs
across three task families; that profile and task set are described below.

Primary result: joint completion success and the difference in **percentage points**.
Secondary: input/output tokens and token savings. The paper's published baseline is
context; only our matched control is used to calculate the treatment delta.

## Model and spending

The host-only gateway calls LiteLLM's Python SDK for the model selected in `[llm]`.
LiteLLM handles provider API translation; OpenHands continues to supply the agent
tools and collaboration loop. Provider keys stay on the host. Both supplied profiles
use `reasoning_effort=none`. The original Luna pilot's rejected setup requests remain
in the cumulative ledger.
Every request reserves a conservative amount in a shared SQLite ledger before it is
forwarded. Limits are **$4 total**, **$0.20 per Luna agent** and **$0.50 per OpenRouter
agent**. Unknown request outcomes keep their reservation. SDK/provider retries,
fallbacks and hosted tools are disabled.

Each profile freezes token price ceilings; each reservation records its model and
rates. The Luna profile retains conservative $0.20/M input and $0.75/M output rates,
with no cache discount. OpenRouter also receives a provider pin and matching price
ceilings. Provider-reported usage costs are recorded separately where available;
they can raise the ledger charge above its token estimate, never lower it.
The ledger is an upper estimate, not the provider's billing statement.
The cap applies to this gateway's traffic, not concurrent use of the key elsewhere.

The gateway inserts transient trail blocks at the API request boundary, at most once
per three model requests. Original SDK tool outputs are preserved. Selected blocks
and blocks sent in successful API requests are logged separately. Native trajectories
do not contain these additional blocks; use the trail SQLite log to audit exposure.
Rendering caps are UTF-8 byte limits (300/block, 1,800/session), not measured token caps.

The pinned OpenHands image requires amd64 emulation on this Mac. The pilot uses the
explicit, checked Docker subnet `10.254.254.0/28` because the host's automatic address
pools were full. Change it in the runner if that subnet is already allocated elsewhere.
Only this pilot's containers, network and named volumes are removed after each attempt.

## Offline SDK check

The normal `uv run pytest -q` suite uses no model endpoint. To also test required
intent fields, SDK serialization, and real file operations in the pinned runtime:

```sh
docker run --rm --network none --platform linux/amd64 \
  -e PYTHONPATH=/opt/swarmfs/src:/opt/swarmfs \
  -e LITELLM_LOCAL_MODEL_COST_MAP=True \
  -e LITELLM_TELEMETRY=False \
  -v "$PWD/src:/opt/swarmfs/src:ro" \
  -v "$PWD/bench:/opt/swarmfs/bench:ro" \
  --entrypoint /opt/agent-server-venv/bin/python \
  akhatua/cooperbench-pallets-jinja@sha256:afffe5e618b0c1aea743ec08f938e286d093ffc1d90c4e6651ae21c3e46a3ce9 \
  -m bench.sdk_check
```

The image must already be cached for an entirely offline run. No provider keys are
passed. Checks write temporary files inside the disposable container; source mounts
are read-only. The tool posts a declaration before touching the file, records the
linked outcome, and leaves native editor output intact. The check also verifies
self-exclusion and that declaration/outcome pairs count as one action.

## Expanded DeepSeek task set

Run the same four commands with `--config bench/configs/openrouter.toml`.
The profile selects exactly these tasks; unrelated generated tasks are ignored.

| Task | Features | Work |
| --- | --- | --- |
| Jinja 1621 | 1 + 6 | Fallback search paths + path transformation (original pair) |
| Jinja 1621 | 2 + 9 | Path normalization + cache invalidation monitoring (original pair) |
| Jinja 1621 | 4 + 7 | Search-path priorities + environment/home expansion |
| Jinja 1465 | 1 + 3 | Case-sensitive groupby + custom field separators |
| Jinja 1559 | 1 + 3 | Translation context + priority-based fallback |

Each task pins its original repository commit and uses its own public runner and
test patches. The cached image supplies the SDK, dependencies and repository
history; both agents and the verifier check out that task's base before starting.
Private test runners are mounted only in the verifier. Reference and untouched
controls cover every selected pair; hashes bind validation to the exact inputs.
Arm order alternates across pairs. There is one repetition, so results remain
preliminary and features from one family are correlated.

The [CooperBench paper](https://arxiv.org/html/2601.13295v2) specifies 100 actions;
the pinned OpenHands adapter implements its step setting as 100 SDK iterations.
An SDK iteration can emit multiple tool actions, so we record actual actions in
traces and do not equate the two counters. We keep asynchronous messaging,
isolated workspaces, task inputs and the pinned Harbor verifier. The paper also
uses a learned conflict resolver after ordinary/union merge attempts; this local
Harbor verifier uses ordinary/union merging without that extra model. These are
local adaptation results, not an exact reproduction of the paper's baseline.
The retained 900-second timeout and $0.50 allowance per agent are our experiment's
additional limits. Model response length has no fixed pilot cap; remaining dollar
allowance and the provider's native capacity determine the request bound.
