"""Extracción del PDF: bloques de texto y tablas, cada uno con su número de página.

Modelo **híbrido** (D-09) — cada librería hace lo que hace bien en este PDF:

- **Texto → PyMuPDF**: agrupa por bloques y respeta el orden de lectura de las
  páginas a **dos columnas** del manual. (pdfplumber fusionaba líneas base de
  columna izquierda y derecha y producía texto entrelazado: ver test de p.116.)
- **Tablas → pdfplumber**: detecta las tablas reales (402/626 páginas; el
  ``find_tables`` de PyMuPDF 2.0 detecta 0 y cuesta 5–8 s/página → D-08).
- El texto de la página se extrae **sin** las palabras caídas dentro de las
  tablas detectadas, para no duplicar contenido. Ambas librerías comparten
  sistema de coordenadas —origen arriba-izquierda, unidades en puntos PDF—,
  así que los bboxes de pdfplumber se usan **tal cual** para filtrar las
  palabras de PyMuPDF (p. ej. en la p.130 la celda «Pieza a apretar» no se
  duplica en el texto). Con páginas rotadas habría que ajustar: los tests
  contra el PDF real lo blindan.
- Tablas → **Markdown** (D-04); todos los bloques conservan ``page_number``
  para las citas (RF-06).
- Normalización de símbolos Symbol: ``N·m`` (U+F0D7) y ``→`` (U+F046),
  construidos con ``chr()``: son caracteres PUA invisibles y al teclearlos
  literalmente es muy fácil confundirlos (lección: se escribió F057 por F0D7).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

import pdfplumber
import pymupdf

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


def _dentro(
    punto: tuple[float, float], bbox: tuple[float, float, float, float]
) -> bool:
    x, y = punto
    x0, y0, x1, y1 = bbox
    return x0 <= x <= x1 and y0 <= y <= y1


def _texto_sin_tablas(
    page: Any, bboxes: Sequence[tuple[float, float, float, float]]
) -> str:
    """Texto de una página PyMuPDF excluyendo las palabras dentro de ``bboxes``.

    Agrupa las palabras por (bloque, línea) preservando el orden de lectura
    que PyMuPDF asigna a las columnas de la página.
    """
    lineas: dict[tuple[int, int], list[str]] = {}
    for x0, y0, x1, y1, palabra, bloque, linea, _ in page.get_text("words"):
        centro = ((x0 + x1) / 2, (y0 + y1) / 2)
        if any(_dentro(centro, bbox) for bbox in bboxes):
            continue
        lineas.setdefault((bloque, linea), []).append(palabra)
    return "\n".join(" ".join(palabras) for palabras in lineas.values()).strip()


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

    with pdfplumber.open(pdf_path) as pdf, pymupdf.open(pdf_path) as doc:
        total = doc.page_count
        indices = [n - 1 for n in pages] if pages is not None else range(total)
        for indice in indices:
            if not 0 <= indice < total:
                raise ValueError(f"página fuera de rango: {indice + 1} (el PDF tiene {total})")
            pagina_pdf = pdf.pages[indice]
            pagina_mupdf = doc[indice]
            numero = indice + 1

            # Tablas (pdfplumber): sus bboxes valen tal cual en PyMuPDF
            # (mismo origen arriba-izquierda y mismas unidades en puntos)
            tablas = pagina_pdf.find_tables()
            bboxes = [tuple(tabla.bbox) for tabla in tablas]

            texto = _normalizar(_texto_sin_tablas(pagina_mupdf, bboxes)).strip()
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
