"""Puerto de almacenamiento: interfaz común a los adaptadores (local, S3).

Las ``key`` usan ``/`` como separador, p. ej. ``manual/manual.pdf``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StoragePort(ABC):
    """Almacenamiento de objetos identificados por ``key`` (estilo S3)."""

    @abstractmethod
    def put_file(self, key: str, source: Path) -> None:
        """Copia el fichero ``source`` al almacén bajo ``key``.

        Si ``source`` no existe lanza :class:`FileNotFoundError`.
        """

    @abstractmethod
    def get_file(self, key: str, destination: Path) -> Path:
        """Descarga ``key`` a ``destination`` y devuelve la ruta.

        Si ``key`` no existe lanza :class:`FileNotFoundError`.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Indica si ``key`` existe como objeto."""

    @abstractmethod
    def list(self, prefix: str = "") -> list[str]:
        """Lista las ``key`` que empiezan por ``prefix``, en orden alfabético."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Elimina ``key``. Si no existe, no hace nada (idempotente)."""
