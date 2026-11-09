# SwarmFS

A small activity-trail experiment for collaborating coding agents: declare why
an agent is opening or changing a file, record the outcome, let that signal decay,
and show a bounded amount of attributed peer activity. The core uses Python's
standard library and SQLite. The current implementation is a harness integration;
FUSE and generated summaries are outside its scope. The benchmark supports separate
checkouts or one shared source tree.

**Status:** early MVP, with preliminary CooperBench pilots using OpenHands SDK.

## Install

Requires Python 3.12+ and `uv`. Docker Compose is needed only for CooperBench runs.

```sh
git clone https://github.com/devYaoYH/swarmfs.git
cd swarmfs
uv sync
```

This installs the project and development tools. Benchmark dependencies are separate:

```sh
uv sync --group benchmark
```

## Use the trail store

No model access is needed for the core:

```sh
uv run python - <<'PY'
from pathlib import Path
from swarmfs import TrailStore

Path(".cache").mkdir(exist_ok=True)
trails = TrailStore(".cache/trails.db")
fields = dict(action_id="open-1", intent="read_for_edit", note="Check lookup order")
trails.deposit("demo", "agent-a", "intent-1", "src/example.py", "read",
               phase="declared", **fields)
# Execute the file operation, then record succeeded or failed with the same action_id.
trails.deposit("demo", "agent-a", "outcome-1", "src/example.py", "read",
               phase="succeeded", **fields)
print(trails.lookup("demo", "agent-b", half_life=300))
PY
```

Lookups return up to three ranked path/activity records with authors, distinct peer
and action counts, and each author's latest intent, note and outcome. They exclude
the querying agent and stay within an episode. An intent and its outcome count as
one action. Repeated activity is capped; scores decay with a configurable half-life.
Intent is advisory; workspace sharing is a benchmark setting. [Core design](docs/design.md).

OpenHands' file tool requires `intent=read|read_for_edit|write` and a one-line
`intent_note` of up to 120 characters. Its wrapper records intent before executing,
then records success or failure. No extra model turn is needed. Host-assigned actor
identities distinguish self from peers; identity resumption is outside this MVP.

## Run the benchmark

Follow [benchmark setup](docs/benchmark.md) to fetch the pinned public task inputs
and configure the selected provider's key in the ignored `.env` file. Then run:

```sh
uv run swarm-trails prepare
uv run swarm-trails verify   # Docker reference/negative controls; no model calls
uv run swarm-trails pilot    # Paid model calls with persistent spending limits
uv run swarm-trails report
```

Provider calls use the **LiteLLM Python SDK in the host process**. The default
[profile](pilot.toml) selects GPT-6 Luna; an [OpenRouter profile](bench/configs/openrouter.toml)
selects DeepSeek V4.1 Flash. Both use OpenHands SDK as the agent harness.

With `OPENROUTER_API_KEY` set, check function calling without Docker:

```sh
uv run swarm-trails smoke --config bench/configs/openrouter.toml
```

This makes two tiny paid calls with a one-cent allowance. The same `--config` option
works with `prepare`, `verify`, `pilot` and `report`. [Model configuration](docs/models.md).
The shared spending ledger is capped at $4, with smaller per-agent profile limits.
Provider keys stay on the host; agents receive disposable gateway credentials.
Generated logs and ledgers stay in the ignored `artifacts/` directory.

For both agents to edit **one live checkout**, use
[`bench/configs/openrouter-shared.toml`](bench/configs/openrouter-shared.toml).
The [shared-workspace guide](docs/shared-workspace.md) explains setup, a model-free
two-agent SDK check, controls and paired runs. Both agents share source while SDK
conversations remain private; verification uses one final snapshot, without merging
separate patches. The original profiles retain isolated workspaces.
Offline validation passed the two-agent SDK check, all ten feature-pair controls
and 76 tests. Shared-workspace completion results are pending a paid pilot.

## Preliminary benchmark results

Latest isolated-workspace pilot: DeepSeek V4.1 Flash 1017, pinned Relace FP4 route, five feature pairs
across three Jinja task families, one attempt per arm. Both arms use the intent-aware
file tool and native messaging. Only treatment sees peer trails.

| Arm | Joint completion | Input + output tokens | Conservative cost |
| --- | --- | --- | --- |
| Capture-only | 2/5 (40%) | 6,659,447 | $0.0827 |
| Visible intent trails | 2/5 (40%) | 4,592,455 | $0.0602 |

The trail arm used 31.0% fewer tokens. Most of that difference came from the failing
translation pair, where agents encountered different SDK stops; it is a preliminary
observation. Across the other four pairs, the post-hoc reduction was 4.7%.
The new run cost approximately $0.143 conservatively ($0.132 provider-reported).

Limits were 100 SDK iterations, 900 seconds and $0.50 per agent, with no fixed
response-length ceiling beyond provider capacity and remaining dollars. All ten
reference/negative controls passed. No budget or wall-clock cutoff occurred.
Captured 143 file actions and delivered 21 blocks to all ten treatment agents.
Read-for-edit was used once in capture-only and never shown to peers, so its benefit
remains untested in this run.

[Latest results and limitations](docs/results/deepseek-pilot-2026-11-09.md) ·
[Machine-readable results](docs/results/deepseek-pilot-2026-11-09.json) ·
[Earlier Luna pilot](docs/results/pilot-2026-11-08.md)

## Check without model access

```sh
uv sync --group benchmark
uv run ruff check src tests bench
uv run ruff format --check src tests bench
uv run pytest -q
uv run python -m bench.micro
```

Benchmark tests block external socket connections and mock model responses.
The pinned SDK file-tool check also runs with Docker networking disabled; see
[benchmark instructions](docs/benchmark.md#offline-sdk-check).
The microbenchmark measures local
SQLite deposit/lookup latency; it excludes HTTP, SDK and model latency.

## Repository layout

```text
src/swarmfs/     Core trail storage and decay/ranking algorithm
tests/           Core tests
bench/           Harness integration, cost controls, reporting and benchmark tests
docs/            Design, benchmark instructions and published results
pilot.toml       Pinned inputs, model and pilot limits
artifacts/       Ignored local tasks, logs, ledgers and generated reports
```

See the [documentation index](docs/README.md) for the current design and the
earlier, broader experiment proposal.
