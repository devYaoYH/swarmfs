from bench.openhands import ActivityHook, file_observation


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
