# Three-condition CooperBench pilot

Each feature pair has three conditions. All use the same pinned DeepSeek route,
task base, feature requests, intent-aware editor and private feature test suites.

| Condition | Agents | Requests seen initially | Visible peer trails | Task dollars | SDK iterations | Wall limit |
| --- | --- | --- | --- | --- | --- | --- |
| Shared control | 2 | One feature each | No | $1 total ($0.50 each) | 200 total (100 each) | 900 seconds |
| Shared trails | 2 | One feature each | Yes | $1 total ($0.50 each) | 200 total (100 each) | 900 seconds |
| Solo | 1 | Both features | No | $1 pooled | 200 | 900 seconds |

The solo agent has no messaging tools, Redis service or collaborator prompt. It
keeps the same editor, terminal and task tracker. Activity can still be captured
for audit, but no peer context is delivered. Its final checkout is evaluated by the
same snapshot verifier against both feature suites; joint completion is the primary
metric. Tokens sum across every agent in each condition, including failed attempts.

Dollars and iteration allowances match at the task level. Wall time is also held
constant, so two-agent conditions can use twice the aggregate agent-seconds through
parallelism. Solo can allocate its pooled allowance freely between the two features.
Response length remains bounded by provider capacity and remaining dollars.
The cumulative $4 gateway cap is unchanged.

## Preliminary results

The [first three-condition pilot](results/deepseek-three-arm-pilot-2026-11-10.md)
retains the ten completed shared attempts and adds five solo attempts. Shared control
and shared trails each completed 3/5 pairs; solo completed 4/5. The original solo
translation attempt was interrupted by provider 429s and a reservation-driven budget
cutoff. A separate diagnostic retry is excluded from the primary comparison. See the
report for per-pair results, tokens, costs and interpretation limits.

## Extend the saved pilot

The two shared conditions are already saved under `intent-deepseek-shared-v1`.
Run only the additional solo attempts and combine their records without rerunning
or changing those completed attempts:

```sh
uv run swarm-trails prepare --config bench/configs/openrouter-solo.toml
uv run swarm-trails shared-check --config bench/configs/openrouter-solo.toml
uv run swarm-trails verify --config bench/configs/openrouter-solo.toml
uv run swarm-trails pilot --config bench/configs/openrouter-solo.toml
uv run swarm-trails compare --config bench/configs/openrouter-solo.toml \
  --team artifacts/pilot/intent-deepseek-shared-v1 \
  --output artifacts/pilot/intent-deepseek-three-arm-comparison-v1
```

The first three commands make no provider calls. The SDK check uses four scripted
replies to exercise one real agent, both original feature requests, private SDK
storage, absent collaboration tools and final snapshot capture. Run Docker checks
sequentially because the local setup uses a fixed subnet.

Solo artifacts use `artifacts/tasks/solo/`, `artifacts/validation-solo.json` and
`artifacts/pilot/intent-deepseek-solo-v1/`. The comparison checks evaluation input
hashes, model/client settings and aggregate task allowances. It keeps source run
directories intact and links their logs. Solo was added after the saved team runs;
this is a historical extension, not a concurrently randomized three-arm trial.

## Run all three conditions afresh

Use `bench/configs/openrouter-three-arm.toml` with `prepare`, `verify`, `pilot` and
`report`. That profile rotates the order of the three conditions across feature
pairs. Use a new `experiment_id` for new repetitions; frozen manifests and the
cumulative spending ledger continue to apply.

The main comparisons are shared trails versus shared control, and each team
condition versus solo. If solo succeeds where both teams fail, coordination or
splitting the feature information may be costly. If all conditions fail the same
checks, inspect model implementation errors and task difficulty. If teams outperform
solo, inspect whether parallel work or coordination explains the difference.
One attempt per condition cannot establish those mechanisms; traces supply evidence
for follow-up experiments. Token differences must be read alongside completion and
SDK stops.
