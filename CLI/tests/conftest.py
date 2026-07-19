from urllib import request

import pytest


@pytest.fixture(autouse=True)
def forbid_unmocked_network(monkeypatch):
    """Unit tests must replace the transport explicitly before crossing process boundaries."""

    def blocked_urlopen(*args, **kwargs):
        raise AssertionError("Unit test attempted unmocked network access")

    monkeypatch.setattr(request, "urlopen", blocked_urlopen)
