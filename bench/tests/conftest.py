import socket

import pytest


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    """No test may accidentally consume model credits or contact external hosts."""
    original = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError("external network is disabled in offline tests")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")


@pytest.fixture
def luna_config():
    from bench.llm import ModelConfig

    return ModelConfig("openai/gpt-6-luna", "OPENAI_API_KEY", 0.20, 0.75, reasoning_effort="none")


@pytest.fixture
def make_budget(tmp_path, luna_config):
    from bench.budget import Budget

    def create(path=None, **overrides):
        settings = {
            "model": luna_config.model,
            "input_usd_per_million": luna_config.input_usd_per_million,
            "output_usd_per_million": luna_config.output_usd_per_million,
            **overrides,
        }
        return Budget(str(path or tmp_path / "budget.db"), **settings)

    return create
