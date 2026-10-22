"""Tests del puerto de storage: el mismo round-trip para local y S3 (RNF-01).

El test S3 toca la nube real y sólo se ejecuta con ``RUN_S3_TESTS=1``:

    $env:RUN_S3_TESTS="1"; python -m pytest tests/test_storage.py -q
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import pytest

from manual_taller_rag.config import Settings, get_storage
from manual_taller_rag.storage.base import StoragePort
from manual_taller_rag.storage.local import LocalStorage


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _round_trip(storage: StoragePort, tmp_path: Path, key: str) -> None:
    """Comportamiento mínimo exigible a cualquier adaptador de storage."""
    origen = tmp_path / "origen.bin"
    origen.write_bytes(os.urandom(2048))

    # Subida + presencia + listado por prefijo
    storage.put_file(key, origen)
    assert storage.exists(key)
    assert key in storage.list(key.split("/", 1)[0] + "/")

    # Descarga con hash idéntico (criterio de aceptación de la Fase 1)
    destino = tmp_path / "recuperado.bin"
    storage.get_file(key, destino)
    assert _sha256(origen) == _sha256(destino)

    # Borrado idempotente
    storage.delete(key)
    storage.delete(key)
    assert not storage.exists(key)

    # Errores normalizados en ambos adaptadores
    with pytest.raises(FileNotFoundError):
        storage.get_file(key, destino)
    with pytest.raises(FileNotFoundError):
        storage.put_file(key, tmp_path / "no-existe.bin")


def test_local_round_trip(tmp_path: Path) -> None:
    _round_trip(LocalStorage(tmp_path / "almacen"), tmp_path, "manual/prueba.pdf")


def test_local_rechaza_key_fuera_del_raiz(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "almacen")
    origen = tmp_path / "origen.bin"
    origen.write_bytes(b"contenido")
    with pytest.raises(ValueError, match="fuera del directorio"):
        storage.put_file("../intruso.txt", origen)


def test_get_storage_local(tmp_path: Path) -> None:
    storage = get_storage(Settings(local_data_dir=tmp_path))
    assert isinstance(storage, LocalStorage)


def test_get_storage_driver_desconocido() -> None:
    with pytest.raises(ValueError, match="STORAGE_DRIVER"):
        get_storage(Settings(storage_driver="inventado"))


@pytest.mark.skipif(
    os.getenv("RUN_S3_TESTS") != "1",
    reason="requiere RUN_S3_TESTS=1 (acceso real a S3)",
)
def test_s3_round_trip(tmp_path: Path) -> None:
    settings = Settings(storage_driver="s3")
    storage = get_storage(settings)
    clave = f"tests/{uuid.uuid4().hex}/prueba.bin"
    try:
        _round_trip(storage, tmp_path, clave)
    finally:
        storage.delete(clave)
