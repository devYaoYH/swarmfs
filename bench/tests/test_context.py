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
