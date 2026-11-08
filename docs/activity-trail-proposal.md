# SwarmFS Activity Trail: Design and Experiment Plan

Version 0.2 · 2026-11-08 · Historical proposal, written before implementation.

The narrower MVP and initial pilot are now implemented. Read the [current design](design.md),
[benchmark instructions](benchmark.md) and [measured results](results/pilot-2026-11-08.md)
for the actual system. The additional fields, arms and studies below remain proposals.

## 1. Decision this experiment should enable

Determine whether automatically captured, decaying traces of agent activity help another agent find relevant code and complete correct work at lower total cost.

The initial product is a small harness integration and a shared trail store. It supplies a few observed activity records alongside existing tool results. It generates no summaries, asks agents to write no notes, and makes no additional model calls.

The central hypothesis is that knowing where another agent recently worked can improve navigation even without knowing what that agent concluded. This is a narrower claim than the original SwarmFS proposal's claim about generated directory gists.

Establish the benchmark and baseline before implementing ranking or tuning decay. Use CooperBench's two-agent feature pairs to test live activity sharing, preserving its source isolation and evaluator. Fixed historical trails are an optional follow-up for studying age and distraction under controlled conditions. Keep a null result actionable: it should tell us whether trails lack signal, the display fails to convey it, or an apparent gain is too expensive.

## 2. Scope and boundaries

In scope:

- One local machine, one controllable agent harness, isolated ordinary repository checkouts.
- Automatic capture of structured file reads, file edits, and explicit search targets when the harness already exposes them.
- A small shared SQLite-backed sidecar service, scoped to one experiment episode.
- File and directory activity, recency, distinct actors, and evidence links.
- Lazy decay, bounded injection, and records of exactly what was shown.
- Reproducible evaluation, including capture overhead and negative results.

Deferred: FUSE; semantic extents; merging and commit validation; writable shared trunks; generated gists; embeddings; knowledge graphs; agent-authored handoffs; task planning; access across organizations; human-priority reconciliation. Public test outcomes and successful-work reinforcement are possible later extensions, outside the initial activity-only experiment.

Existing tools and Git continue to own file contents and history. Trails are advisory observations. An omitted event does not invalidate a run unless the evaluation's measurement contract requires that event. A trail cannot establish that a file is correct, important, or safe to change.

## 3. Hypotheses and what would count as evidence

| Hypothesis | Comparison | Supporting evidence | Evidence against or limiting the claim |
| --- | --- | --- | --- |
| H1: activity carries useful navigation information | Relevant recent trails versus no visible trails | Lower navigation effort with preserved task correctness and lower total cost | No material improvement despite adequate exposure; or faster navigation followed by worse solutions |
| H2: decay improves the usefulness of activity | Decayed versus non-decayed activity under the same initial conditions | Better pair success/cost when sufficiently old activity competes with new work | Similar results with narrow uncertainty; or useful work is suppressed. Short cold-start episodes may not test decay meaningfully |
| H3: the mechanism is cheap enough to justify itself | Capture-only versus instrumentation baseline; visible trail versus capture-only | Small measured capture overhead and net task savings after all trail costs | Hook delays, context growth, or replayed input costs consume the benefit |
| H4: live trails reduce duplicated investigation | Entire live-sharing groups versus entire no-sharing groups | Lower avoidable duplication and improved correctly completed work per group budget | Herding, unnecessary avoidance, or coordination delays offset savings |

H1, H3 and H4 are tested in the first live CooperBench experiment. H2 is secondary: CooperBench uses a fixed initial source revision and does not intrinsically test historical repository churn. Do not infer cross-session memory or adaptation to source changes from live pair results.

## 4. Minimal design

### Capture observations already available

An event contains:

```text
event_id, episode_id, repository_id, source_snapshot, workspace_id,
session_id, task_id, path, kind, observed_at, evidence_ref
```

Initial kinds are `read`, `edit`, and `search_target`. `search_target` identifies an explicit file or directory searched; it does not claim every file beneath it was read. A successful structured edit produces an `edit` event. Failed tool attempts are retained in measurement logs but do not produce successful-access events.

Use normalized repository-relative paths and experiment-issued identities. The snapshot identifies a base revision plus a workspace state identifier when needed. An edit record means an edit happened in the named workspace; it never implies that edit exists in the consumer's checkout.

The adapter reports only paths it can identify reliably. Arbitrary shell commands remain opaque unless their instrumentation supplies structured access information. Do not add recursive scanning, command guessing, or source instrumentation to achieve complete coverage. Record unsupported operations so the measured coverage is explicit.

Deduplicate retries using stable tool-call/event identities. Cap repeated activity by the same actor on the same path and kind. Exclude dependency trees, build outputs, caches, benchmark internals, and trail-service paths.

### Keep capture outside the tool's critical work

The hook enqueues small events; the sidecar batches persistence. A bounded queue prevents unbounded overhead. Dropped events and queue lag are measured. The agent's original command and output remain intact.

A local HTTP service owns SQLite so containers do not share a database file over an unreliable filesystem. Its namespace is unique to one pair attempt and shared only by that pair's two agents. Connectivity from both agent containers must be checked explicitly. The service is proposed work, separate from CooperBench's messaging infrastructure.

### Rank with little machinery

For each actor/path/kind aggregate, maintain bounded activity strength and its last update. At lookup, apply:

```text
decayed_strength = stored_strength × 2 ** (-elapsed / half_life)
```

Decay needs no periodic rewrite. Apply episode, repository, and path eligibility filters first; then rank by decayed strength, with a deterministic path tie-break. Roll up a bounded number of file records into directory activity. Retain event types and distinct-actor counts rather than presenting an unexplained heat number.

Initial development candidates: a 5-minute or 30-minute half-life, chosen after measuring baseline episode duration; one contribution per actor/path/kind per minute; no consumer's own activity in its recommendations. These are starting parameters, not evidence-backed constants. Freeze one half-life before held-out evaluation. Use a separate hard retention window shared across decay and no-decay arms. Record displayed event ages so an apparent null decay result can be distinguished from insufficient opportunity for decay to matter.

For the first comparison, kinds receive equal weight and the same eligibility rules in every trail arm. Avoid task-semantic matching, centrality, and learned ranking. A baseline with no decay still aggregates activity and caps repeated actors; it simply sets the decay factor to one. This makes the decay comparison identifiable.

Do not reinforce activity merely because a recommendation was displayed. In live runs, actual visits can deposit activity, but actor caps and logged exposure allow feedback loops to be diagnosed. A read is an attention signal, not evidence of a successful route.

### Show a bounded trail at a predictable point

Each primary pair starts with an empty trail, so there is normally nothing to show at session start. After tool calls, query for unseen peer activity in the current directory and a bounded repository-wide fallback. Deliver at most one three-record block per three tool calls, only if eligible peer activity changed. Deduplicate by session and record version. Refreshing an already visited directory matters because the peer may arrive later. Do not require an extra agent turn to query memory.

```text
[Recent activity; observations from other workspaces]
- src/billing/invoice.py — edited by a17, task T42, 4m ago
- tests/billing/ — searched by 2 agents, most recent 7m ago
```

Render fixed templates containing paths, event kinds, ages and opaque identity/task IDs. Do not attach raw commands, task prompts, arbitrary agent prose, or test logs. Evidence links can expose the underlying observed event if queried, with that retrieval cost counted. Private verifier material is never eligible evidence.

Target at most 100 tokens per block and 600 newly inserted trail tokens per session. These caps are development proposals. Also measure cumulative billed input attributable to repeated context: 600 inserted tokens can be billed across many subsequent requests. If the integration cannot enforce a model-token cap precisely, record the estimation method and actual observed tokens.

Display historical activity even when content has changed, but label the source snapshot and current/changed/unknown relationship. Historical activity stays historical. Every arm uses the same snapshot-labeling rule. No claim about current behavior follows from a timestamp or a hash match.

Store query candidates, ranking scores, selected events, delivery time, and injection acknowledgment. Selection is not exposure: count a block as exposed only when the harness actually includes it in a model request.

## 5. Selected benchmark and execution path

Use [CooperBench](https://github.com/cooperbench/CooperBench) with its native `--backend docker` runner. Its tasks, feature descriptions, test patches, setup recipes and reference implementations are public in the [dataset tree](https://github.com/cooperbench/CooperBench/tree/main/dataset); a [Hugging Face mirror](https://huggingface.co/datasets/CooperBench/cooperbench-dataset) is also available. The published suite comprises 652 feature pairs from 30 original task pools across 12 repositories. Public `flash` and `lite` subsets contain 50 and 100 pairs respectively. These are documented counts, to verify against the pinned revision before use.

The native CLI supports local Docker for generation and evaluation, plus Redis messaging. Use Python 3.12 as the conservative environment choice recommended by the README. Pin the actual package/repository revision: the README and current CLI source differ on defaults, so explicitly set backend, agent, model, concurrency, setting and messaging. The current CLI names its default agent `mini_swe_agent_v2`. [Native CLI source](https://github.com/cooperbench/CooperBench/blob/main/src/cooperbench/cli.py).

Start with that local-compatible adapter for baseline reproduction, subject to a capture/injection spike before freezing B1. Shell-only tools may expose few trustworthy path events. If so, select another Docker-compatible adapter or explicitly narrow capture to supported observations; establish its own baseline before comparing arms. Do not silently swap harnesses between control and treatment. Do not assume every advertised agent supports local execution: the current evaluator specifically requires Modal for the `openhands_sdk` adapter. [Evaluator source](https://github.com/cooperbench/CooperBench/blob/main/src/cooperbench/eval/evaluate.py).

Retain two agents, one assigned feature each, separate working copies, native patch collection, and native final evaluation. Keep Git collaboration disabled in the initial experiment. Keep ordinary direct messaging enabled in every primary arm, so A2 tests the incremental value of trails over existing coordination. A separate messaging ablation is defined below. A trail adds path/activity observations; it does not share peer source bytes, gold patches, hidden tests, or a writable workspace.

The native evaluator merges submitted agent patches and checks the feature outcomes. Preserve its merge and testing policy and pin its revision. Record merge status and each feature's result, not just an aggregate success label. The repository documents `combined.patch` as its reference for the jointly implemented work; separately carved feature gold patches are not intended to be merged as the oracle. Validate the combined reference and untouched base on selected tasks during B0.

There is already a [CooperBench-to-Harbor adapter](https://github.com/harbor-framework/harbor/tree/main/adapters/cooperbench). Its documented path runs two agent sidecars and Redis, uses Harbor's `nop` coordinator slot, and provides trajectories and oracle checks. Its main examples target Modal with Docker-in-Docker. Native Docker is the smaller local starting point; Harbor remains optional after baseline parity is established. Using Harbor would not remove the need for the trail adapter.

Local execution here means task containers and evaluation run on the host. Model calls can still use a paid remote endpoint. Fully offline inference depends on the chosen agent/provider integration and is not a requirement of this plan. No package installation, download, service launch or model run is authorized merely by these proposed steps.

## 6. Establish the benchmark before the feature

### Select pairs and prevent family leakage

Begin with 2–3 explicitly named feature pairs from `flash` for environment and adapter smoke checks, one pair at a time. Use a small development subset for tuning, then a frozen held-out manifest spanning multiple repositories. Reuse the existing tasks and tests; building a new benchmark is unnecessary for the first experiment.

Define a family as `(repository, original task_id)`. All feature pairs from the same family belong to one split. `flash` is sampled from `lite`, so `flash` development versus unfiltered `lite` evaluation is not a valid held-out split. Remove all development families from evaluation, not merely identical pairs. If wider evaluation requires reserving families outside `flash`, choose a smaller development slice before running it. Freeze any exceptions and narrow the generalization claim accordingly. Use repository holdouts for a later stronger transfer test.

Stratify selected pairs by predeclared overlap of the reference change locations (high, moderate, low) where feasible, and by repository. Reference locations are evaluator-only annotations and never enter the recommendation index. Report all-pair results and overlap strata: heat may be helpful around shared code but distracting for largely independent features. Do not select only pairs on which the treatment appears to work.

Primary runs start cold with no cross-run memory. Pair attempts, repetitions and arms have separate trail namespaces. Increasing benchmark concurrency runs more independent pairs; it does not increase a pair's team size beyond two.

### Validate tasks and verifiers first

For every task, record the source revision, public instruction, environment, timeout/budget, permitted tools and hidden acceptance checks. Demonstrate that the intended buggy state fails and at least one reviewed valid solution passes; include regression checks where possible. Run repeated no-change checks to identify flaky environments before using paid agent runs.

The hidden verifier establishes the experiment's operational definition of a correct completion, with a small blinded patch review for weak tests or suspicious results. Passing tests is evidence under that verifier, not proof of arbitrary semantic correctness.

Use the native evaluator and its clean test environment. Never expose hidden tests, reference solutions, acceptance labels or future task information through the trail service. Verify that agents cannot reach the host dataset's evaluator-only files even though those files are publicly downloadable.

Before viewing treatment results, annotate a reasonable set of relevant implementation and test locations for navigation measurements. Allow alternative valid locations through blinded review; this annotation must not become the agent's retrieval index.

### Optional fixed-history diagnostic after the live pilot

Generate donor trajectories from separate related tasks using the same harness, without trail assistance. Keep all donor attempts, including unproductive ones; filtering for success would make the history artificially helpful. Extract only eligible activity events, not patches, conclusions, hidden verdicts or transcripts.

Consumers must not repeat the donor's identical feature problem. Donors stay inside their consumer's assigned family split; do not import development traces into held-out families. Include a disclosure audit so task names and evidence references do not reveal target fixes. All arms receive identical public consumer instructions and source bytes. This is a separately labeled historical-reuse experiment, not the primary live CooperBench result.

Freeze each history fixture before consumer runs. Reset the trail namespace and repository for every run. Express donor ages relative to consumer start so paired runs begin with identical age distributions. Record elapsed time and every query afterward. For a fixed-history isolation test, disable new visible peer deposits in every compared arm. Synthetic ages alone cannot establish adaptation to actual repository churn.

Measure donor generation costs once. Report the primary consumer result as reuse of already existing work, plus an end-to-end sensitivity analysis charging donor cost over different reuse counts. Do not assume free history when making a total-system cost claim.

## 7. Sequencing and exit gates

| Phase | Work to do | Evidence required before progressing |
| --- | --- | --- |
| B0: benchmark contract | Pin CooperBench/data/images; select 2–3 smoke pairs and family-disjoint manifests; check untouched and combined-reference outcomes | Native local evaluation works and the split has no family leakage; no ranking implementation yet |
| B1: baseline | Run native two-agent development pairs with fixed messaging/model/budgets and low outer concurrency | Reproducible pair scores, merge/test results, timings and cost; no dominant infrastructure failures |
| B2: shadow capture | Integrate event capture and a pair-scoped service without visible trails | Supported accesses produce expected records; explicit coverage; both containers connect; no hidden-data leakage |
| B3: minimal display | Implement fixed-template injection and deterministic ranking; run development arms | Confirmed model exposure, bounded tokens, measured overhead, inspectable decisions |
| B4: frozen evaluation | Freeze suite, arms, parameters, practical margins and analysis; run held-out comparisons | Results with uncertainty, quality guardrails, failures and cost accounting |
| B5: targeted extensions | If live trails help, test messaging substitution, fixed histories, or Harbor parity separately | Claims isolated by extension; no change to official pair size or source isolation |

If B1 is at floor or ceiling, adjust the development suite before looking at held-out treatment effects. If B2/B3 cannot establish capture and delivery, fix the integration before drawing conclusions about the idea. Stop expanding the system when B4 rules out a useful benefit under the tested conditions.

## 8. Experiment arms

Use the same harness binary, ordinary tools, public task instructions, budgets and framing wherever applicable. The installed plugin is not itself an instruction to search differently. All arms receive the same short explanation that activity metadata, when present, is advisory.

| Arm | Capture | Visible information | Purpose |
| --- | --- | --- | --- |
| A0: instrumentation baseline | Standard benchmark logging only | No trail | Measure the starting behavior and cost |
| A1: shadow | Capture, persist and query candidates; no model injection | No trail | Isolate capture/service overhead; primary no-trail control |
| A2: decayed activity | Same as A1 | Live peer activity, ranked with frozen half-life | Test the minimal intervention on the same two-agent problem |
| A3: activity without decay | Same as A1 | Live peer activity with the same capture/caps, without age discount | Isolate decay's contribution; trajectories naturally diverge after intervention |
| A4: unrelated-history diagnostic | Same as A1 | Frozen unrelated activity from the same repository, without visible live peer deposits | Diagnose generic path suggestions; use only if clean within-split donor fixtures exist |

A4 must use real paths and real activity from frozen unrelated donors, with truthful ages and snapshot labels. Match display opportunities, record types and approximate token volume to A2 as far as possible. It is a diagnostic comparison, not a perfect placebo. Do not invent agent activity or randomly point to nonexistent paths.

Start on development pairs with A0/A1/A2. Add A3 when capture and exposure work. A4 is optional and secondary because its frozen history differs from the live treatment. The primary held-out comparison is A2 versus A1 with messaging enabled in both. H2 uses A2 versus A3; inadequate age variation makes H2 untested rather than false.

Do not add prose handoffs or test-outcome reinforcement to an activity arm. Those require separately named later experiments.

Assign the treatment to the entire two-agent pair. Keep feature assignments, initial source, model, budgets and messaging fixed. Never put control and treatment agents in the same pair or share a trail across simultaneous benchmark pairs. Preserve the native evaluator so actual merge outcomes can be measured, while avoiding any claim that trails themselves guarantee merge safety.

After the primary comparison, a 2×2 messaging/trail ablation can compare messaging on/off crossed with visible activity on/off, keeping capture on. This distinguishes incremental benefit from possible substitution for expensive direct messages. `solo` is an optional workload-efficiency reference with both features and a matched total budget; changing the number of agents is not a clean control for the trail effect. Defer `team` mode, which adds roles, task lists and scratchpads.

## 9. Metrics and accounting

Co-primary outcomes are joint pair success rate and total cost per correct pair. Success requires the pinned evaluator's integration policy and both feature checks to succeed. Charge both agents, messaging, failed attempts, timeouts, capture, storage/query work, and all model input/output usage. Also report cost per attempted pair: a ratio per success becomes unstable when success is rare. If an arm has zero successes, report cost per success as undefined, alongside its zero success rate and total spend.

Keep separate counts for failed patch application, merge conflicts, each feature's tests, missing patches, agent errors and evaluator errors. The native evaluator's summary currently calculates pass rate over passed plus failed evaluations, excluding errors. Preserve that official metric for comparability, but also report all-launched-pair success so integration failures cannot disappear from the experiment's denominator. [Evaluator implementation](https://github.com/cooperbench/CooperBench/blob/main/src/cooperbench/eval/evaluate.py).

| Metric | Definition and use |
| --- | --- |
| Pair correctness | Both features pass under the pinned native integration policy; report per-feature results and patch-review disagreements separately |
| Integration outcomes | Patch-application failures, merge-conflict frequency, and merged-tree test failures; do not use clean merges as a substitute for working features |
| Cost per correct pair | Total arm cost divided by correct pairs; show both agents' model, environment, messaging and trail components; donor costs apply only to the historical extension |
| Completion time | Time from pair launch until both agents terminate, plus separate evaluation/provisioning time; report failures/timeouts and an all-attempt capped summary |
| Navigation effort | Tool calls, input tokens and elapsed time before first useful implementation/test location is returned to the model; unsuccessful discovery is censored at the task limit |
| Reading effort | Total context from repository tools, distinct paths inspected, and repeated inspection; distinguish file bytes fetched from content actually delivered |
| Trail overhead | Capture/query/format latency p50/p95/p99, queue lag/drops, DB growth, CPU/memory, and A1–A0 task-level differences |
| Context overhead | Newly inserted trail tokens, later requests carrying them, cache accounting, and total billed input; no extra model-call count should be introduced |
| Exposure | Queries, candidates, blocks selected, blocks actually delivered, records suppressed by cap, and trials with no eligible trail |
| Uptake | Referenced paths subsequently accessed within a predeclared three-tool-call window; report as correlation, not proof of causal reliance |
| Misleading-activity effect | Wrong-directory exploration, avoidable delay, excessive convergence on peer paths, and correctness/cost differences by overlap stratum; stale-history diagnostics belong to the extension |
| Live duplication | Cross-agent repeated exploratory accesses to the same path/task area, with a reviewed sample distinguishing necessary shared context from avoidable repetition |
| Pair productivity | Correct joint completions per fixed pair time/cost budget; benchmark outer concurrency is held constant across arms |

Keep time spent provisioning, executing the agent, running verification, and collecting artifacts separate. End-to-end time includes all components; navigation timing starts at agent launch. Pin resource allocations and record model rate limiting so infrastructure contention is not mistaken for a coordination effect.

Native usage data is preferred for billing. Record missing usage, cache semantics and pricing assumptions rather than manufacturing complete token totals. ATIF alone does not guarantee every integration records every required metric.

For discovery failures, show the fraction that never reached a useful location and time-to-discovery with censoring. Do not average discovery time only over successful navigators. A first useful edit is an optional diagnostic, not the main target: premature edits can look fast.

## 10. Run design, sample size and decision rules

Use a small development pilot to estimate variance and practical run cost. First establish the 2–3-pair smoke path, then begin with 3 repetitions per development pair for A0/A1/A2, staged in small batches. Use one pair at a time initially: two agents remain concurrent inside that pair. Set generation and evaluation concurrency explicitly, along with per-agent and total pair token/cost/time budgets. This is an initial budget envelope, not a powered confirmatory experiment.

For the held-out suite, choose repetition count from pilot variability and a predeclared minimum useful effect. A planning target is 24 pairs across 12 untouched original task families, if the pinned catalog permits that family-disjoint allocation. At 3 repetitions across A1/A2/A3 this is 216 pair attempts, or 432 agent sessions, plus development runs. A0 can stay in development; A4 and solo/messaging ablations have separate budgets. Freeze the actual manifest, run count and spending ceiling before evaluation. Do not repeatedly peek and add samples until significance appears. If the budget cannot resolve the chosen margin, label the result exploratory.

Pair arms by repository, original task ID, feature pair and repetition block. Reset both workspaces and the pair's trail namespace between attempts. Randomize arm order within blocks to reduce provider-time drift. A repeated seed does not make external model behavior deterministic. Live event histories will diverge after treatment; this is part of the intervention, not an identical-history replay.

Bootstrap paired differences at the original task-family level, preserving pairs and repetitions within families, and report 95% intervals. With a target of only 12 evaluation families, intervals can be wide; more overlapping pairs cannot substitute for independent families. A hierarchical model is an optional secondary analysis. Report effect sizes and raw denominators, including by repository and overlap stratum.

Provisional practical margins, to finalize using development data and the cost budget before evaluation:

- A useful intervention should reduce total cost per correct completion by at least 10%.
- Joint pair success should not fall by more than 5 percentage points; this is a proposed guardrail, not an already justified tolerance.
- A navigation reduction of at least 15% is an informative mechanism signal, but does not by itself justify adoption.
- Capture-only median task-time overhead should stay below 2%, with p95 added hook processing below 10 ms on the selected local setup. These are engineering targets to measure, not promised performance.

For a strong go decision, require uncertainty to support both the cost improvement and correctness guardrail: the paired interval for relative cost improvement should clear the 10% margin, and the lower bound for success-rate difference should exceed −5 percentage points. A favorable point estimate with broad intervals is a reason to gather more independent evidence, not to declare the guardrail satisfied. If those thresholds are too costly to establish, narrow the claim or change the decision budget before running.

Predeclare one primary comparison, A2–A1. Treat other arm/condition comparisons as secondary or diagnostic; report the multiplicity rather than selecting the best result as the headline.

Keep model/task timeouts and integration failures caused by the trail system in treatment outcomes. For demonstrably external infrastructure failures, retain the original record and rerun the entire affected paired block under a frozen policy. Show both all-launched and infrastructure-adjusted summaries. No silent retrying until a task passes.

## 11. How to interpret results

| Observed result | Interpretation | Next decision |
| --- | --- | --- |
| A2 improves cost and preserves joint pair success with useful precision | Activity trails add value over native messaging in the tested local CooperBench setup | Broaden untouched families, then try another harness or Harbor parity |
| Navigation improves but total cost does not | A real routing signal may exist, but context or integration overhead consumes it | Reduce frequency/token volume; test the revised policy on fresh held-out cases |
| Faster discovery accompanies lower correctness | Agents may anchor on others' activity or skip necessary exploration | Reject the current policy; inspect misleading cases before changing ranking |
| A2 and A3 both beat A1, with no material difference | Sharing activity helps; decay has no demonstrated incremental value | Prefer the simpler policy unless changing-history evidence warrants decay |
| A2 and A3 are similar, and nearly every displayed event is much younger than the half-life | The live run offered little opportunity to test decay | Mark H2 inconclusive; consider the separately budgeted historical diagnostic |
| Decay helps only in a later changed-history extension | Decay may be useful specifically under churn | Limit that claim to the extension and verify on real chronological changes |
| A2 and A4 perform similarly | Generic path suggestions or context priming may explain the gain; specific pheromone information is unproven | Compare with a static repository path map before claiming collective memory |
| A1 is materially worse than A0 | Capture/service overhead is already too expensive | Fix or simplify capture before scaling model runs |
| Almost no useful trails are delivered | The experiment did not provide sufficient exposure to test the mechanism | Diagnose capture, trigger and eligibility on development data; do not call H1 false |
| Trails are delivered but rarely followed | Display timing/relevance or agent behavior limits uptake | Inspect trajectories; a policy change needs a new evaluation |
| A2 has no useful effect with intervals excluding the practical gain | Activity-only trails lack enough value under these tested conditions | Stop this direction for that workload; do not automatically build gists |
| A2 has no clear effect with wide intervals | The result is inconclusive | Add independent families/repetitions within a new declared budget, or stop without a benefit claim |
| Trails reduce conflicts but neither feature success nor joint success improves | Coordination changed, but useful output did not improve | Inspect behavioral failures; do not claim productivity from conflict counts alone |
| Benefit appears only when ordinary messaging is disabled | Trails may substitute for communication rather than improve the normal cooperative setting | Report the 2×2 interaction and total messaging/trail costs |
| Benefit exists only with curated successful donors in an extension | Evidence applies to curated memory rather than natural activity | State the restriction and include curation costs; rerun on unfiltered donors |

Never infer reduced merge conflicts from navigation gains, or safe knowledge reuse from activity metadata. A null decay result does not refute activity sharing. A positive two-agent benchmark result does not establish benefits at 128 agents or on a writable shared trunk.

## 12. Artifacts and the first concrete milestone

The eventual experiment should produce a pinned CooperBench/data/image manifest; original task-family split; feature-pair lists; protected verifier/reference materials; pinned harness/model/environment versions; frozen messaging, Git, budget and decay settings; both agents' trajectories and patches; native merge/test outputs; trail/query/exposure logs; actual usage/cost; errors and exclusions; and a report with uncertainty and reviewed examples. Optional historical runs additionally require donor histories and extraction rules.

The first milestone is B0/B1: 2–3 selected CooperBench pairs pass environment/reference checks and produce reproducible native baseline artifacts. The next milestone is a shadow adapter with an explicit coverage contract. Ranking and visible trails come after both. No filesystem work or replacement benchmark is required to answer the initial question.

## References and prior-art boundary

- [Hermes Agent FHS proposal, issue 81038](https://github.com/NousResearch/hermes-agent/issues/81038): proposes hook-generated file markers and decaying trails; the author reports a prototype. The issue is not evidence of merged Hermes support or measured effectiveness.
- [Stigmem](https://github.com/Eidetic-Labs/stigmem) and its [limitations](https://github.com/Eidetic-Labs/stigmem/blob/main/LIMITATIONS.md): an implemented alpha for attributable, expiring facts, with a substantially broader scope. Adoption and effectiveness are not established by implementation alone.
- [CooperBench repository](https://github.com/cooperbench/CooperBench), [dataset](https://github.com/cooperbench/CooperBench/tree/main/dataset) and [Hugging Face mirror](https://huggingface.co/datasets/CooperBench/cooperbench-dataset): selected task source and native local execution path. Current checkout behavior must be verified before runs.
- [Harbor CooperBench adapter](https://github.com/harbor-framework/harbor/tree/main/adapters/cooperbench): existing alternative execution integration; defer migrating until native baselines work.
- [MAC-Bench code](https://github.com/rzchen777-wq/MAC_Bench) and [public task packages](https://huggingface.co/datasets/sihuichuibuqi/MAC-Bench): evaluated as an alternative. Its documented environments run on Modal while the evaluator runs locally; it is not the selected local benchmark.

Public documentation was consulted on 2026-11-08. Capability claims describe that documentation; integration behavior and performance still need the B1–B3 checks. This plan is separate from the original SwarmFS FUSE design and does not revise its scope or claims.
