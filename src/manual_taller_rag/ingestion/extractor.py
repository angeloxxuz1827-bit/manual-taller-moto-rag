"""Extracción del PDF: bloques de texto y tablas, cada uno con su número de página.

Estrategia (RF-02), decidida tras sondear el PDF real — ver D-08 en ``docs/SPECS.md``:

1. ``pdfplumber`` como extractor único: detecta las tablas del manual
   (402/626 páginas) a ~0,1 s/página. (PyMuPDF ``find_tables`` tardaba 5–8 s
   por página con su modelo de layout: inviable.)
2. El texto de la página se extrae **sin** las celdas de sus tablas (filtro por
   centro de los caracteres) para no duplicar contenido.
3. Las tablas se serializan a **Markdown** (D-04) y todos los bloques conservan
   ``page_number`` para las citas (RF-06).

Además se normalizan los símbolos de la fuente Symbol del PDF:
``N·m`` (U+F0D7) y la marca de referencia ``→`` (U+F046). Se construyen con
``chr()``: son caracteres PUA invisibles y al teclearlos literalmente es muy
fácil confundirlos (lección aprendida: se escribió F057 por F0D7).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

import pdfplumber

TipoBloque = Literal["text", "table"]

#: Símbolos PUA de la fuente Symbol usados en el manual → caracteres normales.
_MAPA_SIMBOLOS = str.maketrans(
    {
        chr(0xF0D7): "·",  # unidad "N·m" en las tablas de torque
        chr(0xF046): "→",  # marca de referencia "→ (Página 1C-2)"
    }
)


@dataclass(frozen=True)
class ExtractedBlock:
    """Un fragmento extraído del PDF listo para el chunking."""

    kind: TipoBloque
    content: str
    page_number: int  # numeración 1-based, igual que en el PDF
    source: str = ""
    section: str | None = None  # reservado para detección de secciones (Fase 3+)


def _normalizar(texto: str) -> str:
    """Sustituye los símbolos PUA de la fuente Symbol por caracteres legibles."""
    return texto.translate(_MAPA_SIMBOLOS)


def _tabla_a_markdown(filas: Sequence[Sequence[str | None]]) -> str:
    """Convierte las filas extraídas de una tabla en Markdown legible."""
    limpias: list[list[str]] = []
    for fila in filas:
        celdas = [
            "" if c is None else str(c).replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip()
            for c in fila
        ]
        limpias.append(celdas)

    # Descarta filas inicialmente vacías (algunos detectores añaden una)
    while limpias and not any(limpias[0]):
        limpias.pop(0)
    if not limpias:
        return ""

    n_cols = max(len(fila) for fila in limpias)
    filas_np = [fila + [""] * (n_cols - len(fila)) for fila in limpias]
    cabecera, cuerpo = filas_np[0], filas_np[1:]

    lineas = [
        "| " + " | ".join(cabecera) + " |",
        "| " + " | ".join(["---"] * n_cols) + " |",
    ]
    lineas += ["| " + " | ".join(fila) + " |" for fila in cuerpo]
    return "\n".join(lineas)


def _fuera_de_tabla(
    obj: dict[str, Any], bboxes: Sequence[tuple[float, float, float, float]]
) -> bool:
    """Indica si un objeto pdfplumber debe conservarse al filtrar las tablas.

    Los caracteres cuyo centro cae dentro de alguna tabla se descartan;
    el resto de objetos (líneas, etc.) se conservan tal cual.
    """
    if obj.get("object_type") != "char" or not bboxes:
        return True
    centro_x = (obj["x0"] + obj["x1"]) / 2
    centro_y = (obj["top"] + obj["bottom"]) / 2
    return not any(
        x0 <= centro_x <= x1 and y0 <= centro_y <= y1 for x0, y0, x1, y1 in bboxes
    )


def extract_blocks(pdf_path: Path, pages: Sequence[int] | None = None) -> list[ExtractedBlock]:
    """Extrae todos los bloques (texto y tablas) de ``pdf_path``.

    Args:
        pdf_path: ruta del PDF.
        pages: números de página 1-based a procesar; ``None`` = todas.

    Raises:
        ValueError: si alguna ``page`` está fuera del rango del documento.

    Returns:
        Bloques en orden de página; cada uno conserva ``page_number`` para citar.
    """
    pdf_path = Path(pdf_path)
    origen = pdf_path.name
    bloques: list[ExtractedBlock] = []

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        indices = [n - 1 for n in pages] if pages is not None else range(total)
        for indice in indices:
            if not 0 <= indice < total:
                raise ValueError(f"página fuera de rango: {indice + 1} (el PDF tiene {total})")
            page = pdf.pages[indice]
            numero = indice + 1

            tablas = page.find_tables()
            bboxes = [tuple(tabla.bbox) for tabla in tablas]

            if bboxes:
                filtrada = page.filter(lambda obj: _fuera_de_tabla(obj, bboxes))
                texto = filtrada.extract_text() or ""
            else:
                texto = page.extract_text() or ""
            texto = _normalizar(texto).strip()
            if texto:
                bloques.append(
                    ExtractedBlock(kind="text", content=texto, page_number=numero, source=origen)
                )

            for tabla in sorted(tablas, key=lambda t: t.bbox[1]):  # orden vertical
                markdown = _tabla_a_markdown(tabla.extract() or [])
                if markdown:
                    bloques.append(
                        ExtractedBlock(
                            kind="table",
                            content=_normalizar(markdown),
                            page_number=numero,
                            source=origen,
                        )
                    )

    return bloques
