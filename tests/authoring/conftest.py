"""Shared fixtures for the authoring tests.

``backend/`` is put on the import path so ``app.features.authoring`` resolves the
same way it will under the platform's FastAPI entry point.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

BACKENDS = ["memory"]


@pytest.fixture(params=BACKENDS)
def world(request):
    """The same scenarios run against every adapter."""
    import support

    return getattr(support, f"{request.param}_world")()
