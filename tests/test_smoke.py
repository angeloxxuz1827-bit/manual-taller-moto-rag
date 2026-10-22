"""Smoke test: el paquete principal es importable."""

import manual_taller_rag


def test_version_definida() -> None:
    assert manual_taller_rag.__version__ == "0.1.0"
