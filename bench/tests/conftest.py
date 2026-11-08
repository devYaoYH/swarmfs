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
