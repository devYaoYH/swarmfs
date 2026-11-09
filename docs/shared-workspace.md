# Shared-workspace CooperBench experiment

Both OpenHands agents edit **one live Git checkout**. They keep separate processes,
SDK conversations, output volumes, actor identities and dollar allowances. Native
messaging remains available. This is a CooperBench-derived workspace condition;
the published isolated-workspace pilot remains a separate result.

## Run

Use the same install, pinned dataset and cached task image as
[the existing benchmark](benchmark.md). The new profile selects the same five
feature pairs, DeepSeek route and limits: 100 SDK iterations, 900 seconds and $0.50
per agent. The cumulative $4 ledger still spans experiments.

```sh
uv run swarm-trails prepare --config bench/configs/openrouter-shared.toml
uv run swarm-trails shared-check --config bench/configs/openrouter-shared.toml
uv run swarm-trails verify --config bench/configs/openrouter-shared.toml
```

These commands make no provider calls. `shared-check` starts both real SDK sidecars
and serves eight scripted replies locally. Agent 1 creates a file, agent 2 reads
and extends it, and agent 1 reads the result. The check also asserts that SDK state
is private, per-agent patches are absent, the shared collaboration prompt is used,
and one final source patch contains both edits without conversation logs. Its mock
ledger is separate from the paid-run ledger. Logs stay in `artifacts/shared-check/`.

`verify` runs all five combined-reference positive controls and all five untouched
negative controls through shared-volume initialization, snapshotting and the original
feature test runners. Each reference must pass **both** feature suites; each
untouched control must fail joint completion. Validation hashes include generated
agent scripts, instructions, test inputs, base metadata and the shared lifecycle
implementation. Paid runs refuse missing or stale validation.

Run Docker checks sequentially: the current local setup uses one fixed subnet.

After those checks, the paid paired experiment and report commands are:

```sh
uv run swarm-trails pilot --config bench/configs/openrouter-shared.toml
uv run swarm-trails report --config bench/configs/openrouter-shared.toml
```

Shared tasks live in `artifacts/tasks/shared/`, validation in
`artifacts/validation-shared.json`, and model runs in
`artifacts/pilot/intent-deepseek-shared-v1/`. Existing isolated task and experiment
directories are retained. Profiles without `workspace_mode` default to `isolated`.
Changing modes requires a fresh experiment ID, preparation and validation.

## Workspace lifecycle

1. A one-shot initializer clones the image's repository into a fresh named volume
   and checks out the task's pinned base. It refuses a nonempty volume. Both agents
   wait for successful initialization; neither performs a startup checkout.
2. Both containers mount that volume at `/workspace/repo`. SDK conversations and
   shell-event files go under their own `/agent_output/sdk/`, outside the shared tree.
   Both system and task instructions describe immediate visibility and no later
   patch merge. Trail headers identify a shared working tree.
3. Agent exit preserves logs and signals completion without staging or extracting
   a patch. The host waits for **both containers to stop**, including on SDK stops,
   before asking the verifier to capture source.
4. The verifier mounts the live tree read-only at `/shared-workspace`. Its private
   repository and temporary index capture final files against the pinned base,
   including staged, unstaged and committed changes, deleted files, new non-ignored
   files, symlinks, file modes and binary changes. Agent Git indexes are untouched.
5. `final.patch` records that snapshot. `implementation.patch` applies the pinned
   Harbor test-file filter. Each feature's original runner gets the same
   implementation patch in a reset private verifier checkout. No patch union or
   merge resolver runs. Empty snapshots test untouched source without attempting
   to apply an empty patch. Artifacts include both patch hashes and feature exits.
6. Only this run's containers, network and volumes are removed.

Code lives in `bench/shared.py` and the existing Compose generator in `bench/pilot.py`.
`bench/shared_check.py` supplies the model-free SDK integration check. The core
`src/swarmfs/` algorithm is unchanged.

## Experiment and interpretation

Compare **shared + capture-only** against **shared + visible trails**, counterbalancing
arm order across the same five feature pairs. Both arms declare and record file
intent. Only the latter receives peer trail blocks. Messaging, model, task inputs,
runtime, budgets and verification are matched within this condition.

The primary metric remains joint feature completion and its percentage-point delta.
Input/output tokens and token savings are secondary; read them alongside errors,
timeouts, iteration stops and stuck detection. Inspect file-intent exposure and
message timing when diagnosing failures. Reporting rejects a treatment comparison
that mixes shared and isolated modes. Earlier isolated results provide context;
one run per pair cannot establish a workspace-mode or trail effect reliably.

The hypothesis is that visible intent helps agents avoid interfering with live peer
edits and negotiate overlapping work. Removing union merging should eliminate that
specific source of syntactic corruption. It does not imply higher success: stale
reads, overlapping replacements and independent coding bugs can still fail tasks.

No locks, write reservations, automatic retries or merge assistance are added in this
condition. Native editor undo histories remain per process, tests agents run during
development observe a moving tree, and agents share `.git` along with source.
Instructions discourage destructive repository-wide commands, but do not enforce
that restriction. Terminal-based file access still bypasses structured file trails.
Trail ranking, 300-byte blocks, every-third-request cadence and the 1,800-byte session
allowance are retained; source marks can still be crowded out by newer test/doc marks.
This condition tests shared files without also changing the trail-selection policy.

Offline controls establish harness correctness, not completion performance. The
[first paid pilot](results/deepseek-shared-pilot-2026-11-09.md) completed all ten
attempts: 3/5 joint successes in each shared arm, versus 2/5 in each earlier isolated
arm. Groupby accounts for the additional completed pair. Trails used 17.2% more
tokens overall; excluding the failed translation pair as a post-hoc diagnostic,
they used 24.9% fewer. The report retains SDK stops, a recovered provider rate limit,
its held reservation and the limits of the historical comparison.

## Validation on 2026-11-09

All 76 offline tests and Ruff checks passed. The real two-agent SDK check passed
with eight scripted replies, eight captured lifecycle events and two delivered
shared-workspace trail blocks. All five reference controls passed both features;
all five untouched controls failed both feature suites. No provider calls were made.
The [validation manifest](results/shared-workspace-validation-2026-11-09.json)
records the profile, implementation hash and per-task results.
