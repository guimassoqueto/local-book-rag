"""Talks to the running interface, the way a browser does."""

import pytest
from gradio_client import Client

pytestmark = pytest.mark.integration

ADDRESS = "http://localhost:7860"


@pytest.fixture(scope="module")
def client():
    return Client(ADDRESS, verbose=False)


def test_the_interface_reports_on_the_system(client):
    gpu, checks = client.predict(api_name="/system_status")

    assert "RTX" in gpu
    rows = {row[0]: row[1] for row in checks["data"]}
    assert rows["ollama"] == rows["chromadb"] == "yes"


def test_destructive_actions_are_refused_without_their_confirmation(client):
    with pytest.raises(Exception, match="exact confirmation"):
        client.predict("yes", api_name="/reset_everything")
