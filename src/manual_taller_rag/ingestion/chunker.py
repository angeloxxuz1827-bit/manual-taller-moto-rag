"""Chunking: conversión de bloques extraídos en chunks indexables (RF-03).

Reglas (D-01):

- **Texto** → ``RecursiveCharacterTextSplitter`` de LangChain con separadores
  adecuados para español (párrafos, frases).
- **Tablas → atómicas**: nunca se parten, para no romper las tablas de
  especificaciones; su tamaño cabe con holgura en el límite de Titan v2 (8192 tokens).
- Cada chunk lleva **metadata** para citar (``page``, ``source``, ``kind``,
  ``section`` si existe, ``chunk_index``) — nunca valores ``None`` (Chroma los rechaza).
- Cada chunk lleva un **ID estable**: sha256(fuente|página|tipo|índice|contenido).
  Re-ingerir con la misma versión de código y configuración devuelve exactamente
  los mismos IDs → ingesta idempotente (RNF-03). Si cambia ``CHUNK_SIZE`` u otra
  configuración, los IDs cambian y habrá que reconstruir el índice (Fase 4).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from manual_taller_rag.ingestion.extractor import ExtractedBlock

_SEPARADORES = ["\n\n", "\n", ". ", " ", ""]


def _id_estable(
    source: str, page: int, kind: str, ordinal: int, indice: int, contenido: str
) -> str:
    """ID determinista (32 hex) a partir de la identidad completa del chunk.

    ``ordinal`` es la posición del bloque dentro de su grupo (página, tipo):
    evita que dos bloques **hermanos idénticos** (p. ej. fragmentos de tabla
    repetidos en la misma página) colisionen en el mismo ID, lo que Chroma
    rechazaría al ingerir. Al depender sólo de (página, tipo) y del orden
    intra-página, sigue siendo determinista aunque se procese un subconjunto
    de páginas del mismo PDF.
    """
    clave = f"{source}|{page}|{kind}|{ordinal}|{indice}|{contenido}"
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()[:32]


def chunk_blocks(
    blocks: Sequence[ExtractedBlock],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """Convierte bloques extraídos en chunks de LangChain con metadata e ID.

    Args:
        blocks: bloques del extractor (texto o tabla), cada uno con su página.
        chunk_size: tamaño objetivo de los chunks de **texto** (caracteres).
        chunk_overlap: solape entre chunks de texto consecutivos.

    Raises:
        ValueError: si ``chunk_overlap`` no es menor que ``chunk_size``.

    Returns:
        Un :class:`~langchain_core.documents.Document` por chunk, en orden;
        ``document.id`` es estable entre ejecuciones con la misma configuración.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) debe ser menor que chunk_size ({chunk_size})"
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_SEPARADORES,
    )

    documentos: list[Document] = []
    ordinales: dict[tuple[int, str], int] = {}
    for bloque in blocks:
        clave_grupo = (bloque.page_number, bloque.kind)
        ordinal = ordinales.get(clave_grupo, 0)
        ordinales[clave_grupo] = ordinal + 1

        # Las tablas son atómicas: se conservan enteras aunque superen chunk_size
        fragmentos = (
            [bloque.content] if bloque.kind == "table" else splitter.split_text(bloque.content)
        )

        indice = 0
        for fragmento in fragmentos:
            if not fragmento.strip():
                continue
            metadata: dict[str, str | int] = {
                "page": bloque.page_number,
                "source": bloque.source,
                "kind": bloque.kind,
                "chunk_index": indice,
            }
            if bloque.section:
                metadata["section"] = bloque.section
            documentos.append(
                Document(
                    page_content=fragmento,
                    metadata=metadata,
                    id=_id_estable(
                        bloque.source, bloque.page_number, bloque.kind, ordinal, indice, fragmento
                    ),
                )
            )
            indice += 1

    return documentos
