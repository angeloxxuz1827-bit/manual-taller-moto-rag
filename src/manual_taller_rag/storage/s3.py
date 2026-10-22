"""Adaptador de almacenamiento S3 (boto3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from manual_taller_rag.storage.base import StoragePort

_CODIGOS_NO_ENCONTRADO = {"404", "NoSuchKey", "NotFound"}


def _es_no_encontrado(exc: ClientError) -> bool:
    codigo = str(exc.response.get("Error", {}).get("Code", ""))
    return codigo in _CODIGOS_NO_ENCONTRADO


class S3Storage(StoragePort):
    """Implementación S3: ``bucket`` + cliente boto3 (inyectable para tests)."""

    def __init__(
        self,
        bucket: str,
        region: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("S3_BUCKET no puede estar vacío")
        self.bucket = bucket
        self.client = client if client is not None else boto3.client("s3", region_name=region)

    def put_file(self, key: str, source: Path) -> None:
        self.client.upload_file(str(source), self.bucket, key)

    def get_file(self, key: str, destination: Path) -> Path:
        destino = Path(destination)
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.client.download_file(self.bucket, key, str(destino))
        except ClientError as exc:
            if _es_no_encontrado(exc):
                raise FileNotFoundError(f"key inexistente: {key!r}") from exc
            raise
        return destino

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _es_no_encontrado(exc):
                return False
            raise
        return True

    def list(self, prefix: str = "") -> list[str]:
        claves: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for pagina in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            claves.extend(objeto["Key"] for objeto in pagina.get("Contents", []))
        return sorted(claves)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
