# Preliminary three-condition DeepSeek pilot — 2026-11-10

The same five feature pairs now have shared control, shared trails and a single
agent implementing both features. The ten completed shared attempts were retained;
five new solo attempts were added using the same pinned model, runtime and tests.

| Condition | Joint completion | Input + output tokens | Settled conservative USD |
| --- | --- | --- | --- |
| Shared control | 3/5 (60%) | 5,791,180 | $0.0762 |
| Shared trails | 3/5 (60%) | 6,789,566 | $0.0835 |
| Single agent, both features | 4/5 (80%) | 3,475,856 | $0.0441 |

The initial solo translation attempt hit three upstream 429 errors. Retained
reservations then exhausted its $1 task allowance after only about $0.014 in
settled charges. It remains a failed first attempt in the table, but is not a
clean negative model-capability result. First-attempt scores are not replaced.

One separately recorded infrastructure retry failed joint completion
(feature results: [True, False]) after 3 upstream 429 errors.
This also leaves translation capability inconclusive under the pinned route.
Its additional provider-reported cost was $0.0137.
Its ledger upper bound, including retained reservations, was $1.0000;
retained reservations are not confirmed spend.
The retry used the same model, task, $1/200-iteration allowance and 900-second
limit after cooldown; it is excluded from all primary scores and token totals.


| Task / feature IDs | Shared control | Shared trails | Solo, both features |
| --- | --- | --- | --- |
| cb-jinja-t1621-f1-6 | Pass | Pass | Pass |
| cb-jinja-t1621-f2-9 | Pass | Pass | Pass |
| cb-jinja-t1621-f4-7 | Fail (1/2 features) | Fail (1/2 features) | Pass |
| cb-jinja-t1465-f1-3 | Pass | Pass | Pass |
| cb-jinja-t1559-f1-3 | Fail (1/2 features) | Fail (1/2 features) | Fail (0/2 features) |

## Allocation and interpretation

Each condition gets $1 and 200 SDK iterations per feature pair. Teams split this
as $0.50 and 100 iterations per agent; solo pools it in one conversation. All retain
the 900-second wall limit. Teams can run in parallel, so aggregate agent-seconds
are not equal. Responses have no fixed short output cap. The global $4 cap remains.

Solo receives both original requests and has no collaboration tools, Redis service
or peer trail blocks. It retains the same editor and produces one final snapshot
for the same two private feature suites. The recorded user messages were checked
for both requests; native traces contain no messaging tool calls.

The solo arm asks whether the model can solve both features when it holds the full
specification and implementation context. The team-versus-solo comparison includes
the effects of splitting information and effort, communication and parallelism.
One attempt per condition does not isolate these mechanisms. Solo passed the
searchpath-priority pair that both teams missed. Its observed completion rate
was 20 percentage points higher; this is preliminary and the translation
interruption prevents a clean five-pair capability comparison.

## Tokens, stops and cost

- Shared control: 0 budget, 0 iteration and 1 stuck stops; 0 attempt/endpoint errors.
- Shared trails: 0 budget, 1 iteration and 1 stuck stops; 1 attempt/endpoint errors.
- Single agent, both features: 1 budget, 0 iteration and 0 stuck stops; 1 attempt/endpoint errors.

The five new solo attempts cost $0.0409
provider-reported ($0.0441 conservatively for settled calls).
Solo has $0.9864 in retained reservations.
The old shared trail run still has its $0.4721 reservation for a recovered 429;
that hold is excluded from the settled-cost table. Existing attempts were not paid
for again. Token totals include all failed/stopped attempts and must be interpreted
alongside completion. The earlier shared trail translation loop dominates its total.

All 79 offline tests and ten solo reference/negative controls passed before model calls.
The real one-agent SDK check passed with four scripted replies and no provider key.
4/5 solo SDK runs returned normally;
0/5 emitted a finish tool action. Maximum solo native
actions: 40; largest response: 2,832 tokens.
Snapshot hashes, absence of peer delivery and private SDK state were verified.

[Machine-readable results and audit](deepseek-three-arm-pilot-2026-11-10.json) ·
[Reproduce or run all three conditions afresh](../three-arm-experiment.md) ·
[Earlier shared comparison](deepseek-shared-pilot-2026-11-09.md)
