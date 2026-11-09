# Documentation

- [Install and use SwarmFS](../README.md): landing page and core example.
- [Implemented design](design.md): event capture, decay, ranking and boundaries.
- [Run CooperBench locally](benchmark.md): setup, controls, model and spending.
- [Model and provider configuration](models.md): LiteLLM SDK, OpenRouter and smoke checks.
- [Expanded DeepSeek pilot](results/deepseek-pilot-2026-11-09.md): five pairs,
  completion, token usage and trail coverage.
- [DeepSeek results, manifest and audit as JSON](results/deepseek-pilot-2026-11-09.json).
- [Earlier Luna pilot](results/pilot-2026-11-08.md) and its
  [pinned manifest](results/pilot-2026-11-08.json).
- [Earlier experiment proposal](activity-trail-proposal.md): broader hypotheses
  and possible future arms; this is not a description of implemented capabilities.

Core code lives in `src/swarmfs/`. Benchmark machinery and its tests live in `bench/`.
