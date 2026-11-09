# Preliminary DeepSeek shared-workspace pilot — 2026-11-09

Five feature pairs, one attempt per arm, using the same DeepSeek V4.1 Flash 1017
Relace FP4 route, task bases, OpenHands SDK, tools, messaging and spending limits
as the earlier isolated pilot. Only treatment receives peer trail blocks.

| Workspace | Arm | Joint completion | Input + output tokens | Settled conservative USD* |
| --- | --- | --- | --- | --- |
| Isolated (earlier) | Capture-only | 2/5 (40%) | 6,659,447 | $0.0827 |
| Isolated (earlier) | Visible trails | 2/5 (40%) | 4,592,455 | $0.0602 |
| Shared | Capture-only | 3/5 (60%) | 5,791,180 | $0.0762 |
| Shared | Visible trails | 3/5 (60%) | 6,789,566 | $0.0835 |

*Excludes $0.4721 held in the shared trail ledger
for a recovered provider error without usage. Rates omit cache discounts;
provider-reported spending is listed below.

## A. Trails when files are shared

Both shared arms completed 3/5 pairs; this preliminary
run shows a 0-percentage-point completion difference. The trail arm used
17.2% more total tokens, driven by the failed translation run
and its iteration limit. Excluding translation as a post-hoc diagnostic, trails
used 24.9% fewer tokens across the other four pairs. These are observations,
not established efficiency gains.

## B. Shared versus earlier isolated architecture

- Capture-only: +20 percentage points in joint completion; 13.0% fewer tokens with shared files.
- Visible trails: +20 percentage points in joint completion; 47.8% more tokens with shared files.

This is a descriptive historical comparison. The workspace condition also changes
coordination instructions, private SDK-state placement and integration from an
ordinary/union merge to a single final snapshot. One attempt per cell and five
correlated pairs do not establish a causal filesystem or trail effect.

| Task / features | Isolated control | Isolated trails | Shared control | Shared trails |
| --- | --- | --- | --- | --- |
| Loaders 1621: fallback + transform (1, 6) | Pass | Pass | Pass | Pass |
| Loaders 1621: normalization + monitoring (2, 9) | Pass | Pass | Pass | Pass |
| Loaders 1621: priorities + expansion (4, 7) | Fail (1/2 features) | Fail (0/2 features) | Fail (1/2 features) | Fail (1/2 features) |
| Groupby 1465: case sensitivity + separators (1, 3) | Fail (0/2 features) | Fail (1/2 features) | Pass | Pass |
| Translation 1559: context + priority fallback (1, 3) | Fail (1/2 features) | Fail (0/2 features) | Fail (1/2 features) | Fail (1/2 features) |

Both shared arms passed 8/10 individual features (earlier isolated: 6/10 control,
5/10 trails). Joint pair completion remains the primary metric. Remaining failures:

- Both loader-priority attempts fail one invalid-tuple test; path expansion passes.
- Translation control passes context and 66/67 priority tests, failing priority=0
  calling gettext once. Translation trails pass context and 51/67 priority tests;
  the implementation sends `priority` to callbacks that do not accept it.

## Limits, cost and trace coverage

Limits remained 100 SDK iterations, 900 seconds and $0.50 per agent, with the
existing cumulative $4 ledger. Responses had no fixed short output cap; native
provider capacity and remaining dollars bound each request. All ten model-free
reference/untouched controls passed before the paid run.

- Capture-only: 0 budget, 0 iteration and 1 stuck-loop stops; 0 attempt/endpoint errors; 0 unknown request outcomes.
- Visible trails: 0 budget, 1 iteration and 1 stuck-loop stops; 1 attempt/endpoint errors; 1 unknown request outcomes.

Settled calls cost **$0.1597 conservatively**
($0.1480 provider-reported). With retained reservations,
the new run's ledger amount is $0.6318; the cumulative
gateway ledger is $1.5651.

Captured 147 file actions as 293 lifecycle
events. Delivered 21 trail blocks to 9/10
treatment agents; no self marks or control-arm exposures were observed.
Unique action intents: {"read": 2, "read_for_edit": 2, "write": 143}.
Displayed intents: {"read_for_edit": 1, "write": 22};
displayed phases: {"declared": 1, "failed": 3, "succeeded": 19}.
Displayed age: median 3 seconds, maximum
47 seconds, versus a 300-second half-life.

16/20 agents emitted a finish action.
1 additional SDK run returned normally without a finish tool action.
Largest actual completion: 1,730 tokens; maximum
native tool actions per agent: 98.
Each attempt was evaluated from one shared snapshot, with no separate-patch merge.

Trail ranking, byte budgets and every-third-request delivery were retained. Terminal
file access is not captured structurally, and notes describe intent rather than
correctness or enforced ownership. This experiment does not isolate decay from
visibility, note content or instruction effects.

[Machine-readable results and comparison](deepseek-shared-pilot-2026-11-09.json) ·
[Earlier isolated results](deepseek-pilot-2026-11-09.md) ·
[Shared-workspace reproduction](../shared-workspace.md)

## Groupby integration example

In the shared trail run, agent 1 initially dropped `separator` from the output
lookup while adding case sensitivity. Native test output shows the teammate’s
`test_groupby_separator` regression before agent 1 repaired the argument in both
sync and async code and finished. The final private suites passed 167 and 168
tests. The earlier isolated trail run also had both standalone features working,
but union integration duplicated the lookup and overwrote correct separator keys.
This illustrates live integration catching a cross-feature regression; it does not
establish that the trail block caused the repair.

## Provider errors

Recorded 1 provider error(s). Affected attempts are
retained in the primary metrics; the harness was resumed only for the remaining
attempts, on the same pinned provider. The normalization/monitoring trail run
recorded a transient Relace 429; both agents still emitted finish actions and
both feature suites passed. The pilot runner paused after that attempt because
its gateway log contained an endpoint error.

The conservative amount includes $0.4721 in
retained reservations for requests without usage. This is an upper accounting
bound, not confirmed provider spending. Settled requests were charged
$0.1597 conservatively; provider-reported cost
is listed separately above.
