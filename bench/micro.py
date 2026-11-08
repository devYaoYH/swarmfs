"""Model-free local store timings; excludes HTTP, SDK and model latency."""

import json
import statistics
import tempfile
import time
from pathlib import Path

from swarmfs import TrailStore


def measure(events=300, paths=20):
    with tempfile.TemporaryDirectory() as folder:
        store = TrailStore(str(Path(folder) / "trails.db"))
        samples = {"deposit": [], "lookup": []}
        for i in range(events):
            started = time.perf_counter()
            store.deposit("micro", "a", str(i), f"src/file{i % paths}.py", "edit")
            samples["deposit"].append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            store.lookup("micro", "b")
            samples["lookup"].append((time.perf_counter() - started) * 1000)
        return {
            "events": events,
            "paths": paths,
            "scope": "Sequential local SQLite calls; excludes HTTP, SDK and model latency.",
            "milliseconds": {
                operation: {
                    "p50": round(statistics.median(values), 3),
                    "p95": round(sorted(values)[int(len(values) * 0.95) - 1], 3),
                }
                for operation, values in samples.items()
            },
            "database_bytes_including_wal": sum(
                path.stat().st_size for path in Path(folder).glob("trails.db*")
            ),
        }


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
