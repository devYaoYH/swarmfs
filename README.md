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
and 79 offline tests. The expanded three-condition pilot is reported below.

The [three-condition experiment](docs/three-arm-experiment.md) adds a single agent
implementing both features, alongside shared control and shared trails. Use
[`bench/configs/openrouter-solo.toml`](bench/configs/openrouter-solo.toml) to extend
saved team runs, or [`bench/configs/openrouter-three-arm.toml`](bench/configs/openrouter-three-arm.toml)
to run all three conditions afresh.

## Preliminary benchmark results

DeepSeek V4.1 Flash 1017, pinned Relace FP4 route, five feature pairs across three
Jinja task families. Each pair now has the three requested conditions. Team agents
start with one feature each and can message; solo receives both requests.

| Condition | Joint completion | Input + output tokens | Settled conservative cost |
| --- | --- | --- | --- |
| Shared filesystem, no visible trails | 3/5 (60%) | 5,791,180 | $0.0762 |
| Shared filesystem, visible trails | 3/5 (60%) | 6,789,566 | $0.0835 |
| Single agent, both features | 4/5 (80%) | 3,475,856 | $0.0441 |

Each condition gets $1 and 200 SDK iterations per pair: teams split these across two
agents; solo pools them. All use a 900-second wall limit and the same feature tests.
Teams can work in parallel. Responses have no fixed short length cap.

Solo passed the searchpath-priority pair that both teams missed. Its translation
attempt hit three provider 429 errors, then a budget cutoff caused by retained
reservations. That interrupted attempt stays in the primary table; a separately
labelled infrastructure retry also hit three 429s and passed one of two features.
It is excluded from primary scores and tokens. Token totals
include all failed and stopped attempts. These are preliminary results from one
attempt per condition; solo was added after the saved team runs.

The five primary solo attempts cost $0.0409 provider-reported ($0.0441 settled
conservatively). Unsettled reservations of $0.9864 for solo and $0.4721 for shared
trails are excluded from the table and are not confirmed spend. The ten completed
team attempts were reused. All ten solo reference/negative controls and a real
one-agent SDK check passed without model access before paid calls.

[Three-condition results and per-pair outcomes](docs/results/deepseek-three-arm-pilot-2026-11-10.md) ·
[Machine-readable results and audit](docs/results/deepseek-three-arm-pilot-2026-11-10.json) ·
[Experiment and reproduction](docs/three-arm-experiment.md)

Earlier isolated runs completed 2/5 pairs in each arm, compared with 3/5 in each
shared arm. The historical comparison also changes prompts, SDK-state placement and
integration policy, so it does not establish a causal filesystem effect.
[Shared versus isolated results](docs/results/deepseek-shared-pilot-2026-11-09.md) ·
[Isolated pilot](docs/results/deepseek-pilot-2026-11-09.md) ·
[Luna pilot](docs/results/pilot-2026-11-08.md)

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
