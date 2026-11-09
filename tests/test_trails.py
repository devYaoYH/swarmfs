import sqlite3

import pytest

from swarmfs.trails import TrailStore, normalize_path


@pytest.fixture
def store(tmp_path):
    now = [1000.0]
    return TrailStore(str(tmp_path / "trails.db"), clock=lambda: now[0]), now


def test_half_life_and_expiry(store):
    trails, now = store
    trails.deposit("pair", "a", "1", "src/a.py", "read")
    assert trails.lookup("pair", "b")[0]["score"] == 1
    now[0] += 300
    assert trails.lookup("pair", "b")[0]["score"] == pytest.approx(0.5)
    now[0] += 3601
    assert trails.lookup("pair", "b") == []


def test_episode_isolation_self_exclusion_and_retries(store):
    trails, _ = store
    assert trails.deposit("pair", "a", "1", "a.py", "edit")
    assert not trails.deposit("pair", "a", "1", "a.py", "edit")
    assert trails.lookup("pair", "a") == []
    assert trails.lookup("other-pair", "b") == []
    assert trails.lookup("pair", "b")[0]["score"] == 1


def test_repeated_visits_capped_and_recent_route_can_win(store):
    trails, now = store
    for i in range(100):
        trails.deposit("pair", "a", str(i), "trap.py", "read")
    assert trails.lookup("pair", "b")[0]["score"] == 1
    now[0] += 600
    trails.deposit("pair", "a", "new", "useful.py", "edit")
    assert trails.lookup("pair", "b")[0]["path"] == "useful.py"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../x",
        "a/../../x",
        ".env",
        ".git/x",
        "src/\nignore instructions",
        "node_modules/a",
        "",
    ],
)
def test_invalid_paths(path):
    with pytest.raises(ValueError):
        normalize_path(path)


def test_intent_is_visible_before_execution_and_outcome_counts_once(store):
    trails, now = store
    fields = dict(action_id="open-1", intent="read_for_edit", note="Check lookup order")
    trails.deposit("pair", "a", "declared-1", "loader.py", "read", phase="declared", **fields)
    row = trails.lookup("pair", "b")[0]
    assert row["contributors"][0]["phase"] == "declared"
    assert row["contributors"][0]["note"] == "Check lookup order"
    now[0] += 2
    trails.deposit("pair", "a", "outcome-1", "loader.py", "read", phase="succeeded", **fields)
    row = trails.lookup("pair", "b")[0]
    assert row["actions"] == 1 and row["score"] == 1
    assert row["contributors"][0]["phase"] == "succeeded"
    # A delayed/retried declaration must not resurrect a pending action.
    now[0] += 2
    trails.deposit("pair", "a", "delayed", "loader.py", "read", phase="declared", **fields)
    assert trails.lookup("pair", "b")[0]["contributors"][0]["phase"] == "succeeded"
    assert trails.lookup("pair", "a") == []


def test_nine_actions_from_one_peer_are_not_nine_peers(store):
    trails, _ = store
    for i in range(9):
        trails.deposit("pair", "other", str(i), "a.py", "read")
    trails.deposit("pair", "me", "self", "a.py", "read")
    row = trails.lookup("pair", "me")[0]
    assert row["actors"] == 1 and row["actions"] == 9 and row["score"] == 1
    assert row["contributors"][0]["actor"] == "other"
    trails.deposit("pair", "another", "1", "a.py", "read")
    row = trails.lookup("pair", "me")[0]
    assert row["actors"] == 2 and row["actions"] == 10


def test_failed_and_abandoned_intents_decay_without_claiming_success(store):
    trails, now = store
    fields = dict(action_id="edit", intent="write", note="Add fallback")
    trails.deposit("pair", "a", "d", "a.py", "edit", phase="declared", **fields)
    now[0] += 300
    assert trails.lookup("pair", "b")[0]["score"] == pytest.approx(0.5)
    trails.deposit("pair", "a", "f", "a.py", "edit", phase="failed", **fields)
    row = trails.lookup("pair", "b")[0]
    assert row["actions"] == 1 and row["contributors"][0]["phase"] == "failed"
    now[0] += 3601
    assert trails.lookup("pair", "b") == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"intent": "write"},
        {"phase": "done"},
        {"note": "x" * 121},
        {"note": "\x1b[31mbad"},
        {"phase": "declared"},
    ],
)
def test_invalid_intent_metadata(store, overrides):
    trails, _ = store
    with pytest.raises(ValueError):
        trails.deposit("pair", "a", "1", "a.py", "read", **overrides)


def test_legacy_database_migration_and_notes_survive_reopen(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE events (episode TEXT, actor TEXT, event_id TEXT, path TEXT, "
            "kind TEXT, observed_at REAL, PRIMARY KEY(episode, actor, event_id))"
        )
        db.execute("INSERT INTO events VALUES ('pair', 'a', 'old', 'a.py', 'edit', 1000)")
    store = TrailStore(path, clock=lambda: 1001)
    assert store.lookup("pair", "b")[0]["contributors"][0]["phase"] == "observed"
    store.deposit(
        "pair",
        "a",
        "new",
        "b.py",
        "read",
        action_id="b",
        intent="read_for_edit",
        note=" Check\nlookup\torder ",
        phase="declared",
    )
    reopened = TrailStore(path, clock=lambda: 1001)
    row = next(r for r in reopened.lookup("pair", "b") if r["path"] == "b.py")
    assert row["contributors"][0]["note"] == "Check lookup order"
