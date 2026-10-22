"""Adaptador de almacenamiento local: objetos como ficheros bajo un directorio raíz."""

from __future__ import annotations

import shutil
from pathlib import Path

from manual_taller_rag.storage.base import StoragePort


class LocalStorage(StoragePort):
    """Implementación local: cada ``key`` es una ruta relativa bajo ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        """Resuelve ``key`` dentro de ``root`` (rechaza path traversal)."""
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"key fuera del directorio raíz: {key!r}")
        return path

    def put_file(self, key: str, source: Path) -> None:
        destino = self._path(key)
        origen = Path(source).resolve()
        if origen == destino:
            if not destino.is_file():
                raise FileNotFoundError(f"fichero de origen inexistente: {source}")
            return
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)

    def get_file(self, key: str, destination: Path) -> Path:
        origen = self._path(key)
        if not origen.is_file():
            raise FileNotFoundError(f"key inexistente: {key!r}")
        destino = Path(destination)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)
        return destino

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        claves = [
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file()
        ]
        return sorted(clave for clave in claves if clave.startswith(prefix))

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
