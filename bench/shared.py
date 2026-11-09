"""Shared checkout lifecycle; runs inside benchmark containers with stdlib Python.

Agents share source, while the verifier owns its Git index and object database.
Only invoke snapshot/verification after both agent containers have stopped.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

PROTOCOL = "shared-workspace-v1"
SHARED_SCENARIO = """## Scenario
* You and your teammate implement related features in ONE SHARED working tree.
* File edits are immediately visible to both agents. There is no later patch merge.
* Re-read a file before changing it: your teammate may have edited it since your last read.
* Coordinate overlapping changes and acknowledge handoffs using the messaging tools.
* Avoid repository-wide resets, cleans, checkouts or reverts: they also affect your teammate.
* Before finishing, tell your teammate what changed and what still needs attention.

"""


def checked_base(base):
    if not re.fullmatch("[0-9a-f]{40}", base):
        raise ValueError("invalid pinned base commit")
    return base


def git(repo, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, env=env
    ).stdout


def initialize(source, destination, base, reference=None):
    """Seed a fresh volume once. Never reset or reuse an existing live checkout."""
    checked_base(base)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("shared workspace must be empty; use a fresh run volume")
    git(source, "clone", "--no-hardlinks", "--no-checkout", str(source), str(destination))
    git(destination, "checkout", "--detach", base)
    if reference is not None:
        git(destination, "apply", str(reference))


def snapshot(workspace, verifier, base):
    """Capture actual file bytes using a private Git index, never the agents' index.

    Includes staged/unstaged changes, deletions, new non-ignored files and binaries,
    even if an agent committed. The shared volume can (and should) be read-only here.
    """
    checked_base(base)
    with tempfile.TemporaryDirectory(prefix="swarmfs-index-") as folder:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(folder) / "index")}
        args = [
            "--git-dir=" + str(verifier / ".git"),
            "--work-tree=" + str(workspace),
        ]
        git(workspace, *args, "read-tree", base, env=env)
        git(workspace, *args, "add", "-A", "--", ".", env=env)
        return git(workspace, *args, "diff", "--cached", "--binary", "--no-ext-diff", base, env=env)


def implementation_patch(patch):
    """Retain the pinned Harbor verifier's test-file filtering policy, byte for byte."""
    output = []
    skip = False
    for line in patch.splitlines(keepends=True):
        if line.startswith(b"diff --git"):
            skip = any(
                marker in line
                for marker in (b"/test_", b"/tests/", b"_test.py", b"/test/", b"tests.py")
            )
        if not skip:
            output.append(line)
    result = b"".join(output)
    return result + b"\n" if result and not result.endswith(b"\n") else result


def verify_snapshot(
    workspace=Path("/shared-workspace"),
    verifier=Path("/workspace/repo"),
    *,
    base,
    tests=Path("/tests"),
    patches=Path("/patches"),
    output=Path("/logs/verifier"),
    runner=Path("/usr/local/bin/runner.sh"),
):
    # Guard against accidentally cleaning the agents' checkout in a manual invocation.
    if workspace.resolve() == verifier.resolve():
        raise ValueError("verification requires a separate private checkout")
    patch = snapshot(workspace, verifier, base)
    implementation = implementation_patch(patch)
    output.mkdir(parents=True, exist_ok=True)
    patches.mkdir(parents=True, exist_ok=True)
    (output / "final.patch").write_bytes(patch)
    (output / "implementation.patch").write_bytes(implementation)
    (patches / "merged.patch").write_bytes(implementation)
    exits = []
    for feature in (1, 2):
        name = f"tests{feature}.patch"
        shutil.copyfile(tests / name, patches / name)
        git(verifier, "checkout", "--force", "--detach", base)
        git(verifier, "reset", "--hard", base)
        git(verifier, "clean", "-fdx")
        args = ["bash", str(runner), name]
        # Empty snapshots must exercise untouched source, not fail to apply an empty patch.
        if implementation:
            args.append("merged.patch")
        with (output / f"feature{feature}.log").open("wb") as log:
            result = subprocess.run(args, cwd=verifier, stdout=log, stderr=subprocess.STDOUT)
        exits.append(result.returncode)
    reward = {
        "reward": int(all(code == 0 for code in exits)),
        "feature1_passed": exits[0] == 0,
        "feature2_passed": exits[1] == 0,
        "feature_exit_codes": exits,
        "workspace_mode": "shared",
        "strategy": "shared-snapshot",
        "snapshot_sha256": hashlib.sha256(patch).hexdigest(),
        "implementation_sha256": hashlib.sha256(implementation).hexdigest(),
    }
    (output / "reward.json").write_text(json.dumps(reward, indent=2))
    (output / "reward.txt").write_text(str(reward["reward"]) + "\n")
    return reward


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "verify"))
    parser.add_argument("--base", required=True)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    if args.command == "init":
        initialize(Path("/workspace/repo"), Path("/shared-workspace"), args.base, args.reference)
    else:
        print(json.dumps(verify_snapshot(base=args.base)))


if __name__ == "__main__":
    main()
