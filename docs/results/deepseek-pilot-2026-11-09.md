# Preliminary DeepSeek CooperBench pilot — 2026-11-09

Five feature pairs across three Jinja task families, with one attempt per arm.
DeepSeek V4.1 Flash 1017 via OpenRouter’s pinned Relace FP4 endpoint; OpenHands SDK.
The feature IDs were fixed before paid runs. Both arms used the same intent-aware
file tool and native messaging; only the trail arm received peer marks.

| Arm | Joint completion | Input + output tokens | Conservative cost |
| --- | --- | --- | --- |
| Capture-only | 2/5 (40%) | 6,659,447 | $0.0827 |
| Visible intent trails | 2/5 (40%) | 4,592,455 | $0.0602 |

Completion delta: 0 percentage points. Observed token reduction: 31.0%.
The failed translation pair accounts for 93.1% of that token difference.
Excluding it as a post-hoc diagnostic leaves 4.7% fewer tokens. These are
preliminary observations, not established efficiency gains.

| Task / features | Capture-only | Trails |
| --- | --- | --- |
| Loaders 1621: fallback + transform (1, 6) | Pass | Pass |
| Loaders 1621: normalization + monitoring (2, 9) | Pass | Pass |
| Loaders 1621: priorities + path expansion (4, 7) | Fail | Fail |
| Groupby 1465: case sensitivity + separators (1, 3) | Fail | Fail |
| Translation 1559: context + priority fallback (1, 3) | Fail | Fail |

All five reference controls passed; untouched source failed each pair. All resulting
patches were mergeable, using union fallback in five capture-only and four trail
attempts. The remaining trail attempt merged normally. Per-feature outcomes are
in the JSON; a mergeable patch does not imply both features work.

## Limits and cost

Configured limits: 100 SDK iterations, 900 seconds per agent, $0.50 per agent
assigned to a feature, and the existing cumulative $4 ledger. There was no fixed
4,096-token response cap; output capacity was bounded by native provider capacity
and remaining dollars. Actual responses reached 2,091 tokens; agents took at most
99 tool actions. No budget or wall-clock cutoff occurred.

Capture-only translation had one iteration cutoff and one SDK stuck-loop stop;
visible-trail translation had one stuck-loop stop. These three agents did not
finish normally. There were no endpoint errors or unknown request outcomes.

The experiment cost $0.142923 conservatively; provider-reported usage cost was
$0.132463. The cumulative ledger, including earlier pilots/setup, is
$0.933348. Cache discounts are omitted from conservative estimates.

## Trail audit and interpretation

Captured 143 file actions as 286 linked lifecycle events: 129 writes, 13 inspection
reads and one read-for-edit. Twenty-one blocks reached all ten treatment agents;
no self marks were exposed. Displayed ages had a median of 3 seconds and maximum
of 14 seconds, against a 300-second half-life. All displayed entries were completed
operations; the sole read-for-edit mark belonged to capture-only and was not shown.
Agents made 48 successful send-message calls. Native trajectories exist for all
20 agents; delivery records separately capture injected peer context.

This run exercises attributed activity notes, but barely exercises preparation-to-edit
intent and does not measure the benefit of seeing an operation before execution.
It also does not isolate decay from visibility or note content. The tiny sample,
correlated task families, SDK stops and local merge policy limit generalization.

[Machine-readable results, manifest and audit](deepseek-pilot-2026-11-09.json) ·
[Profile](../../bench/configs/openrouter.toml) · [Reproduction and constraints](../benchmark.md)
