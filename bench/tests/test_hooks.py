from types import SimpleNamespace

import pytest

from bench.openhands import ActivityHook, FileActivity, TrailClient, file_observation


def test_actual_openhands_event_pair_and_failed_operation():
    sent = []
    hook = ActivityHook(post=sent.append)
    action = {
        "id": "action-id",
        "kind": "ActionEvent",
        "tool_name": "file_editor",
        "action": {
            "kind": "FileEditorAction",
            "command": "view",
            "path": "/workspace/repo/src/a.py",
        },
    }
    hook.on_event(action)
    assert sent == []
    hook.on_event(
        {
            "id": "obs-id",
            "kind": "ObservationEvent",
            "action_id": "action-id",
            "observation": {"kind": "FileEditorObservation", "is_error": False},
        }
    )
    assert sent == [{"event_id": "obs-id", "path": "src/a.py", "kind": "read"}]
    hook.on_event(action)
    hook.on_event(
        {
            "id": "failed",
            "kind": "ObservationEvent",
            "action_id": "action-id",
            "observation": {"is_error": True},
        }
    )
    assert len(sent) == 1


def test_capture_failure_does_not_break_agent():
    def broken(_):
        raise OSError("unavailable")

    hook = ActivityHook(post=broken)
    hook.on_event(
        {
            "id": "a",
            "kind": "ActionEvent",
            "action": {"kind": "FileEditorAction", "command": "create", "path": "a.py"},
        }
    )
    hook.on_event({"id": "o", "kind": "ObservationEvent", "action_id": "a", "observation": {}})
    assert hook.counts["errors"] == 1


def test_only_confirmed_structured_file_actions():
    action = {"kind": "FileEditorAction", "command": "view", "path": "/workspace/repo/a.py"}
    assert file_observation(action, {}) == ("a.py", "read")
    assert file_observation(action, {"is_error": True}) is None
    assert file_observation({"kind": "TerminalAction", "command": "cat a.py"}, {}) is None
    action["command"] = "str_replace"
    assert file_observation(action, {}) == ("a.py", "edit")


@pytest.mark.parametrize("failure", [False, True, "exception"])
def test_intent_is_posted_before_file_execution_and_linked_to_outcome(failure):
    events = []
    action = {
        "command": "view",
        "path": "/workspace/repo/a.py",
        "intent": "read_for_edit",
        "intent_note": "Check lookup order",
    }
    activity = FileActivity(TrailClient(post=events.append))
    result = SimpleNamespace(is_error=bool(failure))

    def execute():
        assert [e["phase"] for e in events] == ["declared"]
        if failure == "exception":
            raise RuntimeError("file error")
        return result

    if failure == "exception":
        with pytest.raises(RuntimeError, match="file error"):
            activity.run(action, execute)
    else:
        assert activity.run(action, execute) is result
    assert [e["phase"] for e in events] == ["declared", "failed" if failure else "succeeded"]
    assert events[0]["action_id"] == events[1]["action_id"]
    assert events[0]["event_id"] != events[1]["event_id"]
    assert all(e["intent"] == "read_for_edit" and e["path"] == "a.py" for e in events)


def test_intent_capture_unavailable_does_not_block_file_access():
    def broken(_):
        raise OSError("unavailable")

    client = TrailClient(post=broken)
    action = {"command": "view", "path": "a.py", "intent": "read", "intent_note": "Inspect"}
    result = SimpleNamespace(is_error=False)
    assert FileActivity(client).run(action, lambda: result) is result
    assert client.counts["errors"] == 2


def test_callback_does_not_double_capture_intent_tool():
    sent = []
    hook = ActivityHook(post=sent.append)
    hook.on_event(
        {
            "id": "a",
            "kind": "ActionEvent",
            "action": {"kind": "TrailFileEditorAction", "command": "view", "path": "a.py"},
        }
    )
    hook.on_event({"id": "o", "kind": "ObservationEvent", "action_id": "a", "observation": {}})
    assert sent == []
