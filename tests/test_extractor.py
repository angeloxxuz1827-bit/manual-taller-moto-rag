"""Tests del extractor de PDF: unidad rápida (PDF sintético) + PDF real (gated).

El test contra el PDF real se ejecuta sólo con ``RUN_PDF_TESTS=1``:

    $env:RUN_PDF_TESTS="1"; python -m pytest tests/test_extractor.py -q
"""

from __future__ import annotations

import os
from pathlib import Path

import pymupdf
import pytest

from manual_taller_rag.ingestion.extractor import (
    _fuera_de_tabla,
    _normalizar,
    _tabla_a_markdown,
    extract_blocks,
)

PDF_REAL = Path(__file__).resolve().parents[1] / "data" / "manual" / "GSX_GIXXER250.pdf"

# Caracteres PUA de la fuente Symbol, construidos con chr() (nunca literales)
_PUA_NM = chr(0xF0D7)  # "N·m"
_PUA_REF = chr(0xF046)  # "→ (Página ...)"


@pytest.fixture()
def pdf_sintetico(tmp_path: Path) -> Path:
    """PDF de 2 páginas generado en el propio test (sin ficheros externos)."""
    ruta = tmp_path / "prueba.pdf"
    with pymupdf.open() as doc:
        pagina1 = doc.new_page()
        pagina1.insert_text((72, 72), "Procedimiento de prueba de extraccion.", fontsize=12)
        pagina1.insert_text((72, 100), "El apriete es 6.7 N.m (0.68 kgf-m, 4.95 lbf-ft).", fontsize=12)
        pagina2 = doc.new_page()
        pagina2.insert_text((72, 72), "Pagina dos del documento de prueba.", fontsize=12)
        doc.save(ruta)
    return ruta


def test_extract_blocks_devuelve_paginas_con_metadatos(pdf_sintetico: Path) -> None:
    bloques = extract_blocks(pdf_sintetico)

    assert len(bloques) >= 2
    assert all(b.kind == "text" for b in bloques)
    assert all(b.content.strip() for b in bloques)  # sin bloques vacíos
    assert all(b.source == "prueba.pdf" for b in bloques)
    assert {b.page_number for b in bloques} == {1, 2}
    assert any("Procedimiento de prueba" in b.content for b in bloques)


def test_extract_blocks_por_paginas(pdf_sintetico: Path) -> None:
    bloques = extract_blocks(pdf_sintetico, pages=[2])
    assert bloques
    assert all(b.page_number == 2 for b in bloques)


def test_extract_blocks_rechaza_pagina_fuera_de_rango(pdf_sintetico: Path) -> None:
    with pytest.raises(ValueError, match="fuera de rango"):
        extract_blocks(pdf_sintetico, pages=[99])


def test_tabla_a_markdown_estructura() -> None:
    md = _tabla_a_markdown([["Componente", "Par (N.m)"], ["Tapa de valvulas", "23"]])
    lineas = md.splitlines()
    assert lineas[0] == "| Componente | Par (N.m) |"
    assert lineas[1] == "| --- | --- |"
    assert lineas[2] == "| Tapa de valvulas | 23 |"
    assert len(lineas) == 3


def test_tabla_a_markdown_escapa_y_rellena() -> None:
    md = _tabla_a_markdown([["a|b", None], ["único"]])
    lineas = md.splitlines()
    assert "a\\|b" in lineas[0]  # pipe escapado dentro de la celda
    assert lineas[1] == "| --- | --- |"  # 2 columnas (la cabecera se rellena)
    assert lineas[2] == "| único |  |"  # fila incompleta rellenada con ""


def test_tabla_a_markdown_vacia() -> None:
    assert _tabla_a_markdown([]) == ""
    assert _tabla_a_markdown([[], []]) == ""


def test_normalizar_simbolos_symbol() -> None:
    assert _normalizar("Apriete: 6.7 N" + _PUA_NM + "m (0.68 kgf-m)") == "Apriete: 6.7 N·m (0.68 kgf-m)"
    assert _normalizar(_PUA_REF + "(Página 1C-2)") == "→(Página 1C-2)"
    assert _normalizar("texto normal") == "texto normal"


def test_fuera_de_tabla_filtra_chars_dentro_del_bbox() -> None:
    bboxes = [(100.0, 200.0, 300.0, 400.0)]
    dentro = {"object_type": "char", "x0": 150.0, "x1": 160.0, "top": 250.0, "bottom": 260.0}
    fuera = {"object_type": "char", "x0": 10.0, "x1": 20.0, "top": 10.0, "bottom": 20.0}
    linea = {"object_type": "line", "x0": 150.0, "x1": 160.0, "top": 250.0, "bottom": 250.0}

    assert _fuera_de_tabla(dentro, bboxes) is False
    assert _fuera_de_tabla(fuera, bboxes) is True
    assert _fuera_de_tabla(linea, bboxes) is True  # sólo se filtran chars
    assert _fuera_de_tabla(dentro, []) is True  # sin tablas no se filtra nada


@pytest.mark.skipif(
    os.getenv("RUN_PDF_TESTS") != "1",
    reason="requiere RUN_PDF_TESTS=1 (PDF real de 626 páginas)",
)
def test_pdf_real_extrae_torque_con_pagina() -> None:
    """Texto de torque inline con su página (p. 116: '6.7 N·m (0.68 kgf-m...)')."""
    assert PDF_REAL.exists(), f"Falta el PDF real: {PDF_REAL}"
    bloques = extract_blocks(PDF_REAL, pages=[116])
    assert bloques, "la página 116 no devolvió bloques"
    assert all(b.page_number == 116 for b in bloques)
    assert any("N·m" in b.content for b in bloques)


@pytest.mark.skipif(
    os.getenv("RUN_PDF_TESTS") != "1",
    reason="requiere RUN_PDF_TESTS=1 (PDF real de 626 páginas)",
)
def test_pdf_real_extrae_tabla_de_par_legible() -> None:
    """Criterio Fase 2: tabla de torque real extraída como Markdown con su página."""
    assert PDF_REAL.exists(), f"Falta el PDF real: {PDF_REAL}"
    # p.130: 'Pieza a apretar | Par de apriete | N·m | kgf-m | lbf-ft' (p. ej. 5.5 N·m)
    bloques = extract_blocks(PDF_REAL, pages=[130])
    assert all(b.page_number == 130 for b in bloques)

    tablas = [b for b in bloques if b.kind == "table"]
    assert tablas, "la página 130 no devolvió ninguna tabla"
    md = "\n".join(b.content for b in tablas)
    assert "Par de apriete" in md
    assert "N·m" in md  # símbolo normalizado
    assert "5.5" in md  # valor de torque legible
    # El texto de la tabla no debe duplicarse en el bloque de texto de la página
    texto = "\n".join(b.content for b in bloques if b.kind == "text")
    assert "Pieza a apretar" not in texto
