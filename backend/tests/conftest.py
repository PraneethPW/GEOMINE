"""Unit/integration tests never use a real managed identity project."""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def isolated_identity_configuration(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "")
    settings.cache_clear()
    yield
    settings.cache_clear()
