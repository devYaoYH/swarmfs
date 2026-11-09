# Implemented activity-trail design

The core is [`src/swarmfs/trails.py`](../src/swarmfs/trails.py). It stores metadata
and ranks recent file activity. It makes no model calls and generates no summaries;
short intent notes are authored by the acting agent in its file-tool arguments.

## Capture and storage

The OpenHands `trail_file_editor` tool extends the native editor with two required
arguments: `intent` and `intent_note` (one line, up to 120 characters).

| Intent | Permitted operation |
| --- | --- |
| `read` | `view`, for inspection without a planned change |
| `read_for_edit` | `view`, in preparation for a change |
| `write` | `create`, `str_replace`, `insert`, `undo_edit` |

The executor synchronously posts a `declared` event before running the native file
operation, then posts `succeeded` or `failed`. Both events share an `action_id` and
retain the declared intent and note. Exceptions record failure and propagate normally.
There is no extra model call or separate note tool: the overhead is tool-argument
tokens, two small local HTTP posts, storage, and any displayed peer context.
An unavailable trail service does not block file work; capture is best effort with
a three-second timeout per post. A crash can leave an uncompleted declaration.

Legacy callbacks still accept successful native editor observations; they ignore
the intent-aware tool to avoid double capture. Shell commands and searches are not
interpreted as read sets. Excluded paths use the native editor without a trail.

Each SQLite event contains an episode, actor, event ID, repository-relative path,
action kind (`read`/`edit`), host receipt time, action ID, intent, note and phase.
Existing SQLite databases migrate automatically; historical events remain
`observed`, without fabricated notes or inferred read-for-edit intent.
The episode scopes a benchmark pair; actors have separate workspaces.
`(episode, actor, event_id)` makes retries idempotent. Paths cannot escape the
repository, contain control characters, or reference excluded locations such as
`.git`, `.env`, caches or dependencies.

The host maps disposable authentication tokens to episode-local actor IDs. Event
payloads cannot override the author. Queries exclude self by that identity and
retain individual peer IDs and distinct author counts. Persistent agent registration
and identity resumption are outside this version.

## Ranking and decay

A lookup excludes the querying actor and other episodes, and considers activity
from the last hour. First, declaration and outcome collapse to one file action;
outcomes take precedence over delayed declarations. Failed attempts are visible as
`failed`, not successful edits. Pending declarations decay normally, without a lock
or reservation. For each actor/path/activity/minute bucket, only the newest action
contributes. Its weight is:

```text
weight = 2 ** (-age_seconds / half_life_seconds)
```

Weights are summed per actor/path/activity, capped at 3 per actor, then summed across
actors. Results are sorted by score with deterministic path/activity ties. The default
half-life is 300 seconds and the default result limit is three. The one-hour horizon
excludes old events from queries; old database rows are not physically deleted.

## Benchmark presentation

[`bench/`](../bench/) owns the OpenHands adapter, prompt presentation, model gateway,
cost controls and reporting. The core does not import those components.

The trail arm can receive a block every third model request. Each block is limited
to 300 UTF-8 bytes, with 1,800 bytes per agent session and deduplication of unchanged
selections. Each displayed author gets their own line, naming the path, peer, latest
intent, phase, age, distinct peer count, action count and quoted intent note. Notes
may be shortened to fit the byte cap. For example:

```text
loader.py | peer agent2 | read_for_edit/succeeded, 8s ago | 1 peer, 9 actions: "Check lookup order"
```

Counts cover the same path/activity within the one-hour query window, exclude self,
and count each action once, not both lifecycle events. Multiple authors' notes are
never blended. The header identifies separate workspaces and untrusted notes.
Blocks are inserted transiently at the API boundary without replacing native tool output.

Both arms use the same intent-aware tool and capture events. Only the treatment sees
peer trails. Selection claims and blocks included in successful API requests are
logged separately. Native SDK trajectories omit this injected context; the trail
SQLite log records delivery. New manifests record protocol `intent-v1`; older pilot
results describe observation-only trails and are not mixed into new comparisons.

## Boundaries

Declared intent may change or be abandoned; even a successful edit may be reverted
or incomplete. Activity does not establish correctness, ownership, importance or
merge safety. The MVP has no FUSE layer, directory gists, embeddings, shared file
contents or success-based reinforcement.

Offline tests cover decay, expiry, lifecycle deduplication, attribution, caps,
isolation, migration and integration contracts. A network-disabled check runs real
file operations in the pinned SDK image. The observation-only
[preliminary pilot](results/pilot-2026-11-08.md) checks the earlier execution path;
usefulness and the contribution of decay need further experiments.
