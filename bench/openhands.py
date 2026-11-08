"""OpenHands event callback; also works offline against recorded SDK events."""

import json
import os
import urllib.error
import urllib.request

from swarmfs.trails import normalize_path


class ActivityHook:
    def __init__(self, url=None, token=None, post=None):
        self.url = url or os.environ.get("TRAIL_GATEWAY", "")
        self.token = token or os.environ.get("LLM_API_KEY", "")
        self.pending = {}
        self.counts = {"actions": 0, "observations": 0, "deposits": 0, "errors": 0}
        self.post = post or self._post

    def _post(self, event):
        request = urllib.request.Request(
            self.url + "/events",
            data=json.dumps(event).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()

    def on_event(self, event):
        if event.get("kind") == "ActionEvent":
            self.counts["actions"] += 1
            self.pending[event["id"]] = event.get("action", {})
        elif event.get("kind") == "ObservationEvent":
            self.counts["observations"] += 1
            action = self.pending.pop(event.get("action_id"), {})
            observed = file_observation(action, event.get("observation", {}))
            if observed:
                path, kind = observed
                try:
                    self.post({"event_id": event["id"], "path": path, "kind": kind})
                    self.counts["deposits"] += 1
                except (OSError, urllib.error.URLError):
                    self.counts["errors"] += 1


def file_observation(action: dict, observation: dict) -> tuple[str, str] | None:
    """Accept only completed, successful structured file-editor operations."""
    if observation.get("is_error") or observation.get("error"):
        return None
    if "fileeditor" not in str(action.get("kind", "")).lower().replace("_", ""):
        return None
    command = action.get("command")
    if command not in {"view", "create", "str_replace", "insert", "undo_edit"}:
        return None
    try:
        raw_path = action.get("path", "")
        path = normalize_path(raw_path.removeprefix("/workspace/repo/"))
    except (ValueError, TypeError):
        return None
    return path, "read" if command == "view" else "edit"
