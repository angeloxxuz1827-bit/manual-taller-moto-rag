"""Tests del chunking: metadata 100%, IDs estables y tablas atómicas (RF-03 / D-01).

Los tests gated (``RUN_PDF_TESTS=1``) usan el PDF real de la Fase 2.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from manual_taller_rag.ingestion.chunker import chunk_blocks
from manual_taller_rag.ingestion.extractor import ExtractedBlock, extract_blocks

PDF_REAL = Path(__file__).resolve().parents[1] / "data" / "manual" / "GSX_GIXXER250.pdf"

FRASE = "El apriete del perno principal debe realizarse en cruz con un par de 23 N.m. "


def _bloque_texto(n_chars: int = 2500, **kwargs) -> ExtractedBlock:
    contenido = (FRASE * (n_chars // len(FRASE) + 1))[:n_chars]
    return ExtractedBlock(
        kind="text", content=contenido, page_number=42, source="manual.pdf", **kwargs
    )


def _bloque_tabla(n_chars: int = 3000) -> ExtractedBlock:
    filas = ["| Componente | Par (N.m) |", "| --- | --- |"]
    while sum(len(f) for f in filas) < n_chars:
        filas.append("| Tornillo de la culata | 25 |")
    return ExtractedBlock(
        kind="table", content="\n".join(filas), page_number=42, source="manual.pdf"
    )


def test_chunks_con_metadata_completa() -> None:
    bloque = _bloque_texto()
    chunks = chunk_blocks([bloque], chunk_size=500, chunk_overlap=50)

    assert len(chunks) >= 4  # 2500 chars / 500
    for i, chunk in enumerate(chunks):
        assert chunk.metadata["page"] == 42
        assert chunk.metadata["source"] == "manual.pdf"
        assert chunk.metadata["kind"] == "text"
        assert chunk.metadata["chunk_index"] == i
        assert chunk.id  # ID presente
        assert all(valor is not None for valor in chunk.metadata.values())  # Chroma rechaza None


def test_texto_sin_perdida_y_dentro_del_limite() -> None:
    bloque = _bloque_texto()
    chunks = chunk_blocks([bloque], chunk_size=500, chunk_overlap=50)
    for chunk in chunks:
        assert len(chunk.page_content) <= 500
        assert chunk.page_content.strip() in bloque.content  # sin contenido inventado/pérdida


def test_ids_estables_y_unicos() -> None:
    bloque = _bloque_texto()
    primero = chunk_blocks([bloque], chunk_size=500, chunk_overlap=50)
    segundo = chunk_blocks([bloque], chunk_size=500, chunk_overlap=50)

    ids_1 = [c.id for c in primero]
    assert ids_1 == [c.id for c in segundo]  # determinista entre ejecuciones
    assert len(ids_1) == len(set(ids_1))  # únicos

    # Misma página + mismo contenido = mismo ID (idempotencia deseada: re-ingerir
    # tras editar el final del documento no duplica los chunks compartidos).
    # Para exigir IDs distintos, cambiamos la página:
    otro = ExtractedBlock(
        kind="text", content=bloque.content, page_number=43, source="manual.pdf"
    )
    chunks_otro = chunk_blocks([otro], chunk_size=500, chunk_overlap=50)
    assert set(ids_1).isdisjoint(c.id for c in chunks_otro)  # página distinta → ID distinto


def test_ids_distintos_para_bloques_hermanos_identicos() -> None:
    """Regresión: bloques idénticos en la misma página deben tener IDs distintos.

    Sin el ordinal de bloque en el hash, los fragmentos de tabla repetidos de
    una misma página chocaban y Chroma rechazaría la ingesta (IDs duplicados).
    """
    bloque_a = _bloque_texto(n_chars=300)
    bloque_b = _bloque_texto(n_chars=300)  # idéntico: misma página y kind

    chunks = chunk_blocks([bloque_a, bloque_b], chunk_size=500, chunk_overlap=50)

    ids = [c.id for c in chunks]
    assert len(ids) == 2  # un chunk por bloque
    assert len(set(ids)) == 2  # ...y con IDs distintos


def test_tabla_atomica_aunque_supere_chunk_size() -> None:
    bloque = _bloque_tabla(n_chars=3000)
    chunks = chunk_blocks([bloque], chunk_size=500, chunk_overlap=50)

    assert len(chunks) == 1  # la tabla no se parte
    assert chunks[0].page_content == bloque.content
    assert chunks[0].metadata["kind"] == "table"


def test_seccion_incluida_en_metadata_si_existe() -> None:
    bloque = _bloque_texto(n_chars=300, section="Sistema de refrigeración")
    chunks = chunk_blocks([bloque], chunk_size=500, chunk_overlap=50)
    assert chunks[0].metadata["section"] == "Sistema de refrigeración"

    sin_seccion = chunk_blocks([_bloque_texto(n_chars=300)], chunk_size=500, chunk_overlap=50)
    assert "section" not in sin_seccion[0].metadata  # ausente, nunca None


def test_configuracion_invalida() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_blocks([_bloque_texto()], chunk_size=100, chunk_overlap=100)


@pytest.mark.skipif(
    os.getenv("RUN_PDF_TESTS") != "1",
    reason="requiere RUN_PDF_TESTS=1 (PDF real de 626 páginas)",
)
def test_pdf_real_pagina_de_torque_chunkeada() -> None:
    """Criterio Fase 3 sobre el PDF real: metadata 100% y tabla intacta."""
    assert PDF_REAL.exists(), f"Falta el PDF real: {PDF_REAL}"
    bloques = extract_blocks(PDF_REAL, pages=[130])
    chunks = chunk_blocks(bloques, chunk_size=1200, chunk_overlap=150)

    assert chunks
    for chunk in chunks:
        assert chunk.metadata["page"] == 130
        assert chunk.metadata["source"] == "GSX_GIXXER250.pdf"
        assert chunk.id

    tablas = [c for c in chunks if c.metadata["kind"] == "table"]
    assert tablas, "la p.130 debe producir chunks de tabla"
    assert any("Par de apriete" in c.page_content for c in tablas)
