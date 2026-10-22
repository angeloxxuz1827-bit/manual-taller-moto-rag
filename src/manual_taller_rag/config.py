"""Configuración del proyecto: lectura de ``.env`` y fábrica de adaptadores.

Todos los valores provienen de variables de entorno (ver ``.env.example``);
los paths relativos se resuelven contra la raíz del proyecto, nunca contra
el directorio de trabajo actual (RNF-04).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from manual_taller_rag.storage.base import StoragePort
from manual_taller_rag.storage.local import LocalStorage
from manual_taller_rag.storage.s3 import S3Storage

#: Raíz del repo: ``src/manual_taller_rag/config.py`` → sube 3 niveles.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _resolve(path_str: str) -> Path:
    """Resuelve un path relativo contra la raíz del proyecto."""
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


@dataclass(frozen=True)
class Settings:
    """Ajustes vigentes. Los defaults coinciden con ``.env.example``."""

    # AWS / Bedrock
    aws_region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-2"))
    bedrock_chat_model_id: str = field(
        default_factory=lambda: _env(
            "BEDROCK_CHAT_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0"
        )
    )
    bedrock_embed_model_id: str = field(
        default_factory=lambda: _env("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
    )
    embeddings_dimensions: int = field(
        default_factory=lambda: _env_int("EMBEDDINGS_DIMENSIONS", 1024)
    )

    # Storage (Fase 1)
    storage_driver: str = field(default_factory=lambda: _env("STORAGE_DRIVER", "local"))
    s3_bucket: str = field(
        default_factory=lambda: _env("S3_BUCKET", "manual-taller-moto-rag-610433739351")
    )
    local_data_dir: Path = field(
        default_factory=lambda: _resolve(_env("LOCAL_DATA_DIR", "data"))
    )

    # Vector store
    vectorstore_driver: str = field(default_factory=lambda: _env("VECTORSTORE_DRIVER", "chroma"))
    chroma_persist_dir: Path = field(
        default_factory=lambda: _resolve(_env("CHROMA_PERSIST_DIR", ".chroma"))
    )

    # Chunking
    chunk_size: int = field(default_factory=lambda: _env_int("CHUNK_SIZE", 1200))
    chunk_overlap: int = field(default_factory=lambda: _env_int("CHUNK_OVERLAP", 150))

    # Retrieval (MMR)
    retrieval_k: int = field(default_factory=lambda: _env_int("RETRIEVAL_K", 6))
    mmr_fetch_k: int = field(default_factory=lambda: _env_int("MMR_FETCH_K", 20))
    mmr_lambda_mult: float = field(default_factory=lambda: _env_float("MMR_LAMBDA_MULT", 0.5))

    # Memoria de conversación
    memory_max_turns: int = field(default_factory=lambda: _env_int("MEMORY_MAX_TURNS", 6))

    # Telegram / general
    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN", ""))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))


def load_settings() -> Settings:
    """Carga ``.env`` (si existe, sin pisar el entorno) y devuelve los ajustes."""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings()


def get_storage(settings: Settings | None = None) -> StoragePort:
    """Devuelve el adaptador de storage indicado por ``STORAGE_DRIVER``."""
    cfg = settings if settings is not None else load_settings()
    if cfg.storage_driver == "local":
        return LocalStorage(cfg.local_data_dir)
    if cfg.storage_driver == "s3":
        return S3Storage(bucket=cfg.s3_bucket, region=cfg.aws_region)
    raise ValueError(
        f"STORAGE_DRIVER desconocido: {cfg.storage_driver!r} (esperado 'local' o 's3')"
    )
