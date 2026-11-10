# Documentation

- [Install and use SwarmFS](../README.md): landing page and core example.
- [Implemented design](design.md): event capture, decay, ranking and boundaries.
- [Run CooperBench locally](benchmark.md): setup, controls, model and spending.
- [Shared-workspace experiment](shared-workspace.md): one live checkout, private
  conversations, model-free SDK checks and snapshot verification.
- [Three-condition experiment](three-arm-experiment.md): shared control, shared trails
  and one agent implementing both features with equal task-level allowances.
- [Three-condition preliminary results](results/deepseek-three-arm-pilot-2026-11-10.md):
  five pairs with shared control, shared trails and a solo combined-feature baseline.
- [Three-condition results and audit as JSON](results/deepseek-three-arm-pilot-2026-11-10.json).
- [Shared-workspace offline validation](results/shared-workspace-validation-2026-11-09.json).
- [Model and provider configuration](models.md): LiteLLM SDK, OpenRouter and smoke checks.
- [Shared DeepSeek pilot and historical comparison](results/deepseek-shared-pilot-2026-11-09.md):
  the same five pairs in one live checkout, completion, tokens and integration evidence.
- [Shared results, manifest and trace audit as JSON](results/deepseek-shared-pilot-2026-11-09.json).
- [Earlier isolated DeepSeek pilot](results/deepseek-pilot-2026-11-09.md): five pairs,
  completion, token usage and trail coverage.
- [DeepSeek results, manifest and audit as JSON](results/deepseek-pilot-2026-11-09.json).
- [Earlier Luna pilot](results/pilot-2026-11-08.md) and its
  [pinned manifest](results/pilot-2026-11-08.json).
- [Earlier experiment proposal](activity-trail-proposal.md): broader hypotheses
  and possible future arms; this is not a description of implemented capabilities.

Core code lives in `src/swarmfs/`. Benchmark machinery and its tests live in `bench/`.
