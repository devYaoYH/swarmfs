# SwarmFS

A small activity-trail experiment for collaborating coding agents: observe where
an agent successfully reads or edits a file, let that signal decay, and show a
bounded amount of recent peer activity to another agent. The core uses Python's
standard library and SQLite. The current implementation is a harness integration;
FUSE, generated summaries and shared source files are outside its scope.

**Status:** early MVP, with a preliminary CooperBench pilot using OpenHands SDK.

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
trails.deposit("demo", "agent-a", "event-1", "src/example.py", "edit")
print(trails.lookup("demo", "agent-b", half_life=300))
PY
```

Lookups return up to three ranked path/action records, exclude the querying agent,
and stay within an episode. Repeated events are deduplicated; scores decay with
a configurable half-life. A trail records an observation, not a claim that the
peer's edit exists in the reader's workspace. [Core design](docs/design.md).

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

## Preliminary benchmark results

Original GPT-6 Luna pilot: four pair attempts, with two Jinja feature pairs and
one attempt per pair in each arm.
Both arms retain native messaging; the baseline captures activity without showing it.

| Arm | Joint completion | Total input + output tokens | Conservative cost |
| --- | --- | --- | --- |
| Baseline | 0/2 (0%) | 2,055,294 | $0.4165 |
| Visible decaying trails | 0/2 (0%) | 1,618,965 | $0.3290 |

The observed completion delta was 0 percentage points and the trail arm used
21.2% fewer tokens. Conservative total spending, including rejected setup requests,
was $0.7902; this is an upper estimate, not a provider billing statement.

This is an integration smoke pilot, not a powered comparison. The small sample,
single task family and spending/iteration cutoffs limit interpretation. Eight trail
blocks were delivered, with a median observation age of 4 seconds against a
300-second half-life. Further runs are needed to assess usefulness and decay.

[Full results and limitations](docs/results/pilot-2026-11-08.md) ·
[Machine-readable results and manifest](docs/results/pilot-2026-11-08.json)

## Check without model access

```sh
uv sync --group benchmark
uv run ruff check src tests bench
uv run ruff format --check src tests bench
uv run pytest -q
uv run python -m bench.micro
```

All 27 offline tests passed for the initial pilot. Benchmark tests block external
socket connections and mock model responses. The microbenchmark measures local
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
