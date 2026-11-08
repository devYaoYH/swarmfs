# Implemented activity-trail design

The core is [`src/swarmfs/trails.py`](../src/swarmfs/trails.py). It stores metadata
and ranks recent observed activity. It makes no model calls and generates no summaries.

## Capture and storage

The OpenHands callback matches an action with its successful observation. Supported
structured file-editor operations produce `read` or `edit` events. Failed operations
do not deposit a trail. Shell commands and searches are not interpreted as read sets.

Each SQLite event contains an episode, actor, event ID, repository-relative path,
action kind and host observation time. The episode scopes a benchmark pair; actors
have separate workspaces. `(episode, actor, event_id)` makes retries idempotent.
Paths cannot escape the repository, contain control characters, or reference excluded
locations such as `.git`, `.env`, caches or dependencies.

## Ranking and decay

A lookup excludes the querying actor and other episodes, and considers observations
from the last hour. For each actor/path/action/minute bucket, only the newest event
contributes. Its weight is:

```text
weight = 2 ** (-age_seconds / half_life_seconds)
```

Weights are summed per actor/path/action, capped at 3 per actor, then summed across
actors. Results are sorted by score with deterministic path/action ties. The default
half-life is 300 seconds and the default result limit is three. The one-hour horizon
excludes old events from queries; old database rows are not physically deleted.

## Benchmark presentation

[`bench/`](../bench/) owns the OpenHands adapter, prompt presentation, model gateway,
cost controls and reporting. The core does not import those components.

The trail arm can receive a block every third model request. Each block is limited
to 300 UTF-8 bytes, with 1,800 bytes per agent session and deduplication of unchanged
selections. A block names the path, action and age, and says peer bytes are not shared.
It is inserted transiently at the API boundary without replacing native tool output.

Both arms capture events. Only the treatment sees them. Selection claims and blocks
included in successful API requests are logged separately. Native SDK trajectories
omit this injected context; the trail SQLite log records delivery.

## Boundaries

An observed edit can be reverted or incomplete. Activity does not establish
correctness, ownership, importance or merge safety. The MVP has no FUSE layer,
directory gists, embeddings, shared file contents or success-based reinforcement.

Offline tests cover decay, expiry, deduplication, caps, isolation and integration
contracts. The [preliminary pilot](results/pilot-2026-11-08.md) checks the execution
path; larger histories, concurrent-load scaling, usefulness and the contribution
of decay need further experiments.
