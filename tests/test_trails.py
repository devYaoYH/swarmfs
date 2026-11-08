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
