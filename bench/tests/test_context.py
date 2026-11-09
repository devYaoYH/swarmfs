from concurrent.futures import ThreadPoolExecutor

import pytest

from bench.context import TrailPresenter
from swarmfs import TrailStore


@pytest.fixture
def store(tmp_path):
    now = [1000.0]
    return TrailStore(str(tmp_path / "trails.db"), clock=lambda: now[0]), now


def test_display_dedup_and_total_byte_budget(store):
    trails, now = store
    presenter = TrailPresenter(trails)
    trails.deposit("pair", "a", "1", "src/a.py", "edit")
    block = presenter.block("pair", "b", session_bytes=300)
    assert "src/a.py" in block and len(block.encode()) <= 300
    assert presenter.block("pair", "b", session_bytes=len(block.encode())) == ""
    now[0] += 60
    trails.deposit("pair", "a", "2", "src/a.py", "edit")
    assert presenter.block("pair", "b", session_bytes=len(block.encode())) == ""


def test_only_one_concurrent_delivery(store):
    trails, _ = store
    presenter = TrailPresenter(trails)
    trails.deposit("pair", "a", "1", "a.py", "read")
    with ThreadPoolExecutor(max_workers=8) as pool:
        blocks = list(pool.map(lambda _: presenter.block("pair", "b"), range(16)))
    assert sum(bool(b) for b in blocks) == 1


def test_attributed_notes_actions_and_self_exclusion_with_utf8_budget(store):
    trails, _ = store
    presenter = TrailPresenter(trails)
    for i in range(9):
        trails.deposit(
            "pair",
            "pair:agent2",
            str(i),
            "loader.py",
            "read",
            intent="read_for_edit",
            note="確認 lookup order " + "界" * 60,
        )
    trails.deposit("pair", "pair:agent1", "mine", "private.py", "edit", note="My own mark")
    block = presenter.block("pair", "pair:agent1")
    assert "peer agent2" in block and "1 peer, 9 actions" in block
    assert "read_for_edit/observed" in block and "確認" in block
    assert "private.py" not in block and "My own mark" not in block
    assert len(block.encode()) <= 300


def test_outcome_updates_display_without_counting_another_action(store):
    trails, now = store
    presenter = TrailPresenter(trails)
    fields = dict(action_id="a", intent="write", note="Add fallback")
    trails.deposit("pair", "peer", "d", "a.py", "edit", phase="declared", **fields)
    assert "write/declared" in presenter.block("pair", "self")
    now[0] += 1
    trails.deposit("pair", "peer", "f", "a.py", "edit", phase="failed", **fields)
    block = presenter.block("pair", "self")
    assert "write/failed" in block and "1 action" in block
