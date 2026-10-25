"""Automated checks never load local credentials or spend inference credits."""
import pytest
from causaltrace import nemotron_client


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    monkeypatch.setattr(nemotron_client, 'load_dotenv', lambda *args, **kwargs: False)
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    monkeypatch.setenv('NEBIUS_MODEL', nemotron_client.DEFAULT_MODEL)
