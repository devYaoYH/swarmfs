# Benchmark tooling

Local CooperBench execution, OpenHands event capture, prompt presentation, model
gateway, spending controls and reporting live here, alongside their offline tests.
The core algorithm remains in [`src/swarmfs/`](../src/swarmfs/).

- [Setup and run the benchmark](../docs/benchmark.md)
- [Configure model providers through LiteLLM SDK](../docs/models.md)
- [Preliminary pilot results](../docs/results/pilot-2026-11-08.md)
- [Local store timings](micro.py): `uv run python -m bench.micro`

Run commands from the repository root. Generated tasks, logs and ledgers go into
the ignored `artifacts/` directory. Curated results are published under `docs/results/`.
