import json
import subprocess

import pytest

from bench.shared import git, implementation_patch, initialize, snapshot, verify_snapshot


@pytest.fixture
def repositories(tmp_path):
    source = tmp_path / "image"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "user.name", "Offline test")
    (source / "module.py").write_text("value = 0\n")
    (source / "removed.py").write_text("obsolete\n")
    (source / ".gitignore").write_text("ignored/\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "base")
    base = git(source, "rev-parse", "HEAD").decode().strip()
    live, verifier = tmp_path / "live", tmp_path / "verifier"
    initialize(source, live, base)
    initialize(source, verifier, base)
    return live, verifier, base


def test_initialization_refuses_to_reset_a_live_checkout(repositories):
    live, verifier, base = repositories
    (live / "module.py").write_text("peer edits\n")
    with pytest.raises(ValueError, match="fresh run volume"):
        initialize(verifier, live, base)
    assert (live / "module.py").read_text() == "peer edits\n"


def test_snapshot_uses_final_bytes_and_private_index_including_new_files(repositories):
    live, verifier, base = repositories
    git(live, "config", "user.email", "peer@example.invalid")
    git(live, "config", "user.name", "Peer")
    (live / "module.py").write_text("value = 1\n")
    git(live, "add", ".")
    git(live, "commit", "-m", "agent commit")
    (live / "module.py").write_text("value = 2\n")
    git(live, "add", ".")
    (live / "module.py").write_text("value = 3\n")
    (live / "removed.py").unlink()
    (live / "new.py").write_text("new = True\n")
    (live / "new.py").chmod(0o755)
    (live / "binary.dat").write_bytes(b"\x00\xff\x01")
    (live / "link.py").symlink_to("new.py")
    (live / "ignored").mkdir()
    (live / "ignored/cache").write_text("ignored")
    (live / "tests").mkdir()
    (live / "tests/test_added.py").write_text("assert False\n")
    status_before = git(live, "status", "--porcelain")
    index_before = (live / ".git/index").read_bytes()
    patch = snapshot(live, verifier, base)
    assert snapshot(live, verifier, base) == patch
    assert (live / ".git/index").read_bytes() == index_before
    assert git(live, "status", "--porcelain") == status_before
    assert b"ignored/cache" not in patch
    implementation = implementation_patch(patch)
    assert b"tests/test_added.py" not in implementation
    subprocess.run(["git", "-C", str(verifier), "apply", "-"], input=implementation, check=True)
    assert (verifier / "module.py").read_text() == "value = 3\n"
    assert not (verifier / "removed.py").exists()
    assert (verifier / "binary.dat").read_bytes() == b"\x00\xff\x01"
    assert (verifier / "link.py").is_symlink()
    assert (verifier / "new.py").stat().st_mode & 0o111


@pytest.mark.parametrize("changed", [True, False])
def test_verification_resets_private_tree_between_features_and_keeps_live_tree(
    repositories, changed
):
    live, verifier, base = repositories
    if changed:
        (live / "module.py").write_text("value = 1\n")
    folder = live.parent
    tests, patches, output = [folder / name for name in ("tests", "patches", "output")]
    tests.mkdir()
    for i in (1, 2):
        (tests / f"tests{i}.patch").write_text("fixture")
    # Apply the real snapshot, check the source, leave a file that must be cleaned
    # before the next feature. No model calls or benchmark dependencies needed.
    runner = folder / "runner.sh"
    runner.write_text(
        "set -eu\n"
        "test ! -e previous-feature\n"
        "touch previous-feature\n"
        'if [ "$#" -eq 2 ]; then git apply "' + str(patches) + '/$2"; fi\n'
        'test "$(cat module.py)" = "value = 1"\n'
    )
    before = git(live, "status", "--porcelain")
    reward = verify_snapshot(
        live, verifier, base=base, tests=tests, patches=patches, output=output, runner=runner
    )
    assert reward["reward"] == int(changed)
    assert reward["feature1_passed"] == reward["feature2_passed"] == changed
    assert git(live, "status", "--porcelain") == before
    assert not (live / "previous-feature").exists()
    assert json.loads((output / "reward.json").read_text())["strategy"] == "shared-snapshot"
    assert (output / "final.patch").read_bytes() == snapshot(live, verifier, base)
    with pytest.raises(ValueError, match="separate private checkout"):
        verify_snapshot(live, live, base=base)


def test_implementation_filter_matches_pinned_harbor_policy():
    patch = b"".join(
        f"diff --git a/{path} b/{path}\n+content\n".encode()
        for path in ("src/a.py", "tests/test_a.py", "foo_test.py", "src/b.py")
    )
    filtered = implementation_patch(patch)
    assert b"src/a.py" in filtered and b"src/b.py" in filtered
    assert b"tests/test_a.py" not in filtered and b"foo_test.py" not in filtered
