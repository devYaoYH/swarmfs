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

For paid runs, add `OPENAI_API_KEY` to the ignored root `.env` file, using
[`.env.example`](../.env.example) as a template. Keep an existing `.env` intact.

```sh
uv run swarm-trails prepare
uv run swarm-trails verify
uv run swarm-trails pilot
uv run swarm-trails report
```

Completed attempts are resumed by `experiment_id`; change that value for a fresh
experiment. The shared spending ledger remains cumulative across experiment IDs.
Keep settings fixed within an experiment ID. `prepare` writes generated task files,
`verify` writes `artifacts/validation.json`, and `pilot` writes its per-attempt
records, logs and ledgers under `artifacts/pilot/`. `report` produces `summary.json`
and `report.md` there. Raw local artifacts are not included in Git.

Published pilot: [results](results/pilot-2026-11-08.md) and
[machine-readable summary with pinned inputs](results/pilot-2026-11-08.json).

`verify` uses Docker, without a model: the combined reference must pass both feature
checks and untouched source must fail. `pilot` refuses to run without those results.
The pilot executes generated Harbor task sidecars directly with local Docker Compose,
instead of requiring a Modal account or the Harbor orchestration package. It retains
the pinned Harbor verifier, including its ordinary/union Git merge policy.

The current pilot uses two Jinja feature pairs, one repetition and two arms:
capture-only baseline versus visible decaying trails. Messaging, prompts, model,
tools, initial source and verifier are held constant. Each pair gets an isolated
trail namespace and two separate workspaces. This is one task family, not a held-out
evaluation. Both instructions already name a target file, limiting navigation claims.

Primary result: joint completion success and the difference in **percentage points**.
Secondary: input/output tokens and token savings. The paper's published baseline is
context; only our matched control is used to calculate the treatment delta.

## Model and spending

Put `OPENAI_API_KEY` in the ignored `.env`. The host-only gateway sends requests to
OpenAI using exactly `gpt-6-luna`; agents receive disposable gateway tokens, not the key.
Both arms use `reasoning_effort=none`: the endpoint rejected the SDK's combination
of Chat Completions function tools and `reasoning_effort=low`. The initial rejected
requests are preserved as calibration attempts and remain in the budget ledger.
Every request reserves a conservative amount in a shared SQLite ledger before it is
forwarded. Limits are **$4 total** and **$0.20 per agent**. Unknown request outcomes
keep their reservation. No upstream retries or hosted tools are enabled.

Rates are conservatively $0.20/M input and $0.75/M output, with no cache discount,
using [OpenAI's long-context pricing](https://developers.openai.com/api/docs/pricing).
Reported spending is an upper estimate, not the provider's billing statement.
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
